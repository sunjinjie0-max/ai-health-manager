import asyncio
from importlib import import_module
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.base import BaseAgent, AgentState
from app.agents.environment.nodes.llm_generate_advice import llm_generate_advice
from app.agents.environment.nodes.fetch_air_quality import fetch_air_quality
from app.agents.environment.nodes.format_response import format_response as format_environment_response
from app.agents.exercise.agent import ExerciseAgent
from app.agents.exercise.nodes.safety_validate import safety_validate
from app.agents.nutrition.agent import NutritionAgent
from app.agents.orchestrator import AgentOrchestrator
from app.agents.protocol import AgentRequest, AgentResponse
from app.agents.registry import AgentRegistry
from app.config import settings
from app.tools.executor import ToolExecutionContext, ToolExecutor
from app.tools.registry import tool_registry


class DummyAgentState(AgentState):
    """Dummy state for testing."""
    pass


class DummyAgent(BaseAgent):
    """Dummy agent implementation for testing."""

    def __init__(self):
        super().__init__(
            name="dummy",
            description="A dummy agent for testing",
            version="1.0.0",
        )

    def _compile_graph(self):
        """Compile the StateGraph."""
        # For testing, just return a mock
        from unittest.mock import MagicMock
        return MagicMock()

    async def process(self, state: DummyAgentState) -> DummyAgentState:
        """Process the state."""
        # Add a test marker to the state
        state["processed"] = True
        state["response"] = "Test response"
        return state


def test_base_agent_info():
    """Test that agent info is returned correctly."""
    agent = DummyAgent()
    info = agent.get_info()

    assert info["name"] == "dummy"
    assert info["description"] == "A dummy agent for testing"
    assert info["version"] == "1.0.0"


def test_agent_registry_register():
    """Test registering an agent instance."""
    registry = AgentRegistry()
    agent = DummyAgent()

    registry.register("dummy", agent)

    retrieved = registry.get("dummy")
    assert retrieved is agent


def test_agent_registry_get_nonexistent():
    """Test getting a non-existent agent returns None."""
    registry = AgentRegistry()

    result = registry.get("nonexistent")
    assert result is None


def test_agent_registry_list():
    """Test listing registered agents."""
    registry = AgentRegistry()
    agent = DummyAgent()

    registry.register("dummy", agent)

    agents = registry.list_agents()
    assert "dummy" in agents


def test_agent_registry_get_info():
    """Test getting info for all agents."""
    registry = AgentRegistry()
    agent = DummyAgent()

    registry.register("dummy", agent)

    info = registry.get_info()
    assert len(info) == 1
    assert info[0]["name"] == "dummy"


@pytest.mark.asyncio
async def test_agent_process():
    """Test agent processing."""
    agent = DummyAgent()
    state = DummyAgentState()

    result = await agent.process(state)

    assert result["processed"] is True
    assert result["response"] == "Test response"


class ProtocolDummyAgent(DummyAgent):
    """Dummy agent that speaks the production AgentRequest protocol."""

    async def handle(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            trace_id=request.trace_id,
            agent_name=request.agent_name,
            task_type=request.task_type,
            status="success",
            result={
                "message": request.user_message,
                "prior_keys": sorted(request.prior_results.keys()),
            },
            summary=f"{request.agent_name} done",
        )


@pytest.mark.asyncio
async def test_orchestrator_runs_dependency_batches(monkeypatch):
    """Test that dependent tasks receive previous task results."""
    registry = AgentRegistry()
    registry.register("first", ProtocolDummyAgent())
    registry.register("second", ProtocolDummyAgent())

    import app.agents.orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "agent_registry", registry)
    orchestrator = AgentOrchestrator(timeout_seconds=2)

    result = await orchestrator.dispatch(
        tasks=[
            {
                "task_id": "task_a",
                "agent_name": "first",
                "task_type": "analysis",
            },
            {
                "task_id": "task_b",
                "agent_name": "second",
                "task_type": "follow_up",
                "depends_on": ["task_a"],
            },
        ],
        user_profile={},
        user_id="user123",
        session_id="session123",
        user_message="hello",
    )

    assert result["success"] is True
    assert "task_a" in result["completed"]
    assert "task_b" in result["completed"]
    assert "task_a" in result["responses"]["task_b"]["result"]["prior_keys"]


@pytest.mark.asyncio
async def test_orchestrator_skips_unsatisfied_dependencies(monkeypatch):
    """Test that impossible DAG dependencies fail safely instead of hanging."""
    registry = AgentRegistry()
    registry.register("first", ProtocolDummyAgent())

    import app.agents.orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "agent_registry", registry)
    orchestrator = AgentOrchestrator(timeout_seconds=2)

    result = await orchestrator.dispatch(
        tasks=[
            {
                "task_id": "task_b",
                "agent_name": "first",
                "task_type": "follow_up",
                "depends_on": ["missing_task"],
            }
        ],
        user_profile={},
    )

    assert result["success"] is False
    assert result["responses"]["task_b"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_orchestrator_optional_timeout_does_not_block_dependency(monkeypatch):
    registry = AgentRegistry()

    class TimeoutAgent(ProtocolDummyAgent):
        async def handle(self, request):
            raise asyncio.TimeoutError

    registry.register("optional", TimeoutAgent())
    registry.register("dependent", ProtocolDummyAgent())

    import app.agents.orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "agent_registry", registry)
    result = await AgentOrchestrator(timeout_seconds=2).dispatch(
        tasks=[
            {
                "task_id": "optional_task",
                "agent_name": "optional",
                "required": False,
            },
            {
                "task_id": "dependent_task",
                "agent_name": "dependent",
                "depends_on": ["optional_task"],
            },
        ],
        user_profile={},
    )

    assert result["degraded"] is True
    assert result["responses"]["optional_task"]["status"] == "timeout"
    assert result["responses"]["dependent_task"]["status"] == "success"


@pytest.mark.asyncio
async def test_orchestrator_required_timeout_blocks_dependency(monkeypatch):
    registry = AgentRegistry()

    class TimeoutAgent(ProtocolDummyAgent):
        async def handle(self, request):
            raise asyncio.TimeoutError

    registry.register("required", TimeoutAgent())
    registry.register("dependent", ProtocolDummyAgent())

    import app.agents.orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "agent_registry", registry)
    result = await AgentOrchestrator(timeout_seconds=2).dispatch(
        tasks=[
            {
                "task_id": "required_task",
                "agent_name": "required",
                "required": True,
            },
            {
                "task_id": "dependent_task",
                "agent_name": "dependent",
                "depends_on": ["required_task"],
            },
        ],
        user_profile={},
    )

    assert result["success"] is False
    assert result["responses"]["required_task"]["status"] == "timeout"
    assert result["responses"]["dependent_task"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_nutrition_agent_handles_empty_food_extraction(monkeypatch):
    """Test the nutrition flow degrades gracefully when no foods are extracted."""
    agent = NutritionAgent()

    async def fake_ainvoke(_state):
        return {
            "extracted_foods": [],
            "nutrition_data": {"items": [], "count": 0},
            "total_nutrition": {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0},
            "health_score": 0,
            "recommendations": [],
            "response": "这次我还没有成功识别出您具体吃了哪些食物。",
        }

    class FakeWorkflow:
        async def ainvoke(self, state):
            return await fake_ainvoke(state)

    agent._workflow = FakeWorkflow()
    result = await agent.analyze_meal("帮我分析一下这个午饭", user_id="user123")

    assert "识别出" in result["response"]
    assert result["health_score"] == 0
    assert result["extracted_foods"] == []


@pytest.mark.asyncio
async def test_exercise_agent_handles_none_workflow_result():
    """Test the exercise flow degrades gracefully when workflow returns None."""
    agent = ExerciseAgent()

    class FakeWorkflow:
        async def ainvoke(self, state):
            return None

    agent._workflow = FakeWorkflow()
    result = await agent.create_plan("健康", "beginner", 30, user_id="user123")

    assert "制定运动计划时遇到了技术问题" not in result["response"]
    assert result["workout_plan"] == {}
    assert result["exercises"] == []


@pytest.mark.asyncio
async def test_environment_air_quality_initializes_missing_state_fields():
    """Environment nodes should recover when LangGraph passes a sparse dict."""
    state = await fetch_air_quality(
        {"user_message": "结合杭州5月19日的天气，给出我运动的计划"}
    )

    assert state["location"]["city"] == "杭州市"
    assert "api_errors" in state
    assert state["air_quality"]["aqi"] > 0
    assert state["air_quality"]["data_source"] == "mock_air_quality_tool"


def test_specialist_agent_tools_are_registered():
    """Specialist agents should call external/domain capabilities through ToolRegistry."""
    import app.tools.environment  # noqa: F401
    import app.tools.exercise  # noqa: F401
    import app.tools.nutrition  # noqa: F401

    for name in (
        "resolve_location",
        "fetch_air_quality",
        "fetch_weather",
        "query_nutrition",
        "generate_exercise_plan",
    ):
        assert tool_registry.get(name) is not None


def test_tool_executor_enforces_agent_whitelist():
    """ToolExecutor should block tools outside an agent's whitelist."""
    import app.tools.environment  # noqa: F401

    executor = ToolExecutor()
    result = executor.execute_sync(
        "fetch_weather",
        context=ToolExecutionContext(agent_name="nutrition", trace_id="trace-test"),
        location={"city": "杭州市", "lat": 30.2741, "lon": 120.1551},
    )

    assert result.status == "skipped"
    assert result.trace_id == "trace-test"
    assert "not allowed" in result.error["message"]


def test_target_date_parses_dot_format():
    """_target_date_from_message should parse M.D日 format like '6.11日'."""
    from app.tools.environment import _target_date_from_message
    from app.core.time import utc_now
    from datetime import timedelta

    today = utc_now().date()
    expected = today + timedelta(days=1)
    target = _target_date_from_message(
        f"{expected.month}.{expected.day}日在杭州，根据天气推荐运动计划"
    )
    assert target == expected, f"Expected {expected}, got {target}"


def test_target_date_parses_dot_format_without_ri():
    """_target_date_from_message should parse M.D format without 日 suffix."""
    from app.tools.environment import _target_date_from_message
    from app.core.time import utc_now
    from datetime import timedelta

    today = utc_now().date()
    expected = today + timedelta(days=1)
    target = _target_date_from_message(f"{expected.month}.{expected.day} 杭州 跑步")
    assert target == expected, f"Expected {expected}, got {target}"


def test_target_date_parses_chinese_format():
    """_target_date_from_message should parse 月日 format like '6月11日'."""
    from app.tools.environment import _target_date_from_message
    from app.core.time import utc_now
    from datetime import timedelta

    today = utc_now().date()
    expected = today + timedelta(days=1)
    target = _target_date_from_message(f"{expected.month}月{expected.day}日在杭州")
    assert target == expected, f"Expected {expected}, got {target}"


def test_environment_format_response_handles_sensitive_group_set():
    """Regression test for set slicing in environment response formatting."""
    state = format_environment_response(
        {
            "location": {"city": "杭州市"},
            "health_risk": {
                "overall_risk": "moderate",
                "warnings": [],
                "sensitive_groups": ["儿童", "老年人", "儿童"],
            },
            "weather": {
                "temperature": 26,
                "feels_like": 27,
                "humidity": 65,
                "wind_speed": 3,
                "wind_direction": "南",
                "visibility": 10000,
                "uv_index": 5,
                "weather_description": "多云",
                "target_date": "2026-05-19",
                "temp_low": 22,
                "temp_high": 30,
            },
        }
    )

    assert "杭州市 环境健康报告" in state["response"]
    assert "敏感人群" in state["response"]


@pytest.mark.asyncio
async def test_exercise_llm_refine_plan_is_optional_and_uses_rag(monkeypatch):
    """Exercise LLM refinement should enhance baseline only when enabled."""
    refine_module = import_module("app.agents.exercise.nodes.llm_refine_plan")
    monkeypatch.setattr(settings, "exercise_llm_refine_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")

    async def fake_retrieve(query):
        assert "运动计划" in query
        return [
            {
                "id": "guideline-1",
                "title": "身体活动指南",
                "content": "成年人每周建议进行150-300分钟中等强度有氧身体活动。",
                "source": "eval",
                "metadata": {"topic": "physical_activity"},
            }
        ]

    async def fake_json_chat(system_prompt, user_message, **kwargs):
        assert "baseline计划" in user_message
        assert "RAG运动指南片段" in user_message
        assert kwargs["timeout_seconds"] == settings.specialist_llm_timeout_seconds
        return {
            "workout_plan": {"plan_type": "cardio", "total_duration": 30},
            "exercises": [
                {
                    "name": "慢跑",
                    "duration": 25,
                    "intensity": "高",
                    "description": "结合用户目标调整",
                    "type": "cardio",
                }
            ],
            "additional_safety_notes": ["运动前后注意热身和拉伸。"],
            "rationale": "结合指南和目标微调。",
        }

    monkeypatch.setattr(refine_module.rag_retriever, "retrieve", fake_retrieve)
    monkeypatch.setattr(refine_module.deepseek_client, "json_chat", fake_json_chat)

    state = {
        "user_message": "我想减脂，帮我做30分钟运动计划",
        "fitness_level": "beginner",
        "fitness_goals": ["减脂"],
        "time_available": 30,
        "workout_plan": {"plan_type": "cardio", "total_duration": 30},
        "exercises": [{"name": "快走", "duration": 20, "intensity": "低", "type": "cardio"}],
        "safety_notes": ["初学者应循序渐进。"],
        "user_profile": {"exercise": {"habit": "周末跑步"}},
    }

    refined = await refine_module.llm_refine_plan(state)
    validated = safety_validate(refined)

    assert refined["llm_refine_status"] == "success"
    assert refined["rag_guidelines"][0]["id"] == "guideline-1"
    assert validated["exercises"][0]["intensity"] == "中"
    assert "初学者计划已限制为中低强度" in "\n".join(validated["safety_notes"])


@pytest.mark.asyncio
async def test_environment_llm_generate_advice_adds_personalized_text(monkeypatch):
    """Environment LLM node should add wording without changing risk fields."""
    monkeypatch.setattr(settings, "environment_llm_advice_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")

    async def fake_chat(system_prompt, user_message, **kwargs):
        assert "只能解释和组织已有数据" in user_message
        assert kwargs["timeout_seconds"] == settings.specialist_llm_timeout_seconds
        return "今天更适合低强度户外活动，跑步建议缩短时长并注意补水。"

    advice_module = import_module("app.agents.environment.nodes.llm_generate_advice")
    monkeypatch.setattr(advice_module.deepseek_client, "chat", fake_chat)

    state = {
        "user_message": "今天适合跑步吗？",
        "location": {"city": "杭州市"},
        "air_quality": {"aqi": 90, "level": "moderate"},
        "weather": {"temperature": 29, "humidity": 70},
        "health_risk": {"overall_risk": "moderate", "warnings": []},
        "recommendations": [{"title": "适度户外活动", "priority": "medium"}],
    }

    result = await llm_generate_advice(state)

    assert result["llm_advice_status"] == "success"
    assert "低强度户外活动" in result["llm_advice"]
    assert result["health_risk"]["overall_risk"] == "moderate"
