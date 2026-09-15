import asyncio
import time

import pytest

from app.agents.orchestrator import AgentOrchestrator
from app.agents.protocol import AgentResponse
from app.agents.registry import AgentRegistry
from app.agents.health_advisor.agent import HealthAdvisorAgent
from app.agents.health_advisor.nodes.plan_tasks import plan_tasks
from app.agents.health_advisor.state import HealthAdvisorState
from app.core import deadline as deadline_module
from app.core.deadline import (
    DeadlineExceeded,
    create_deadline,
    deadline_before_reserve,
    remaining_seconds,
    require_remaining,
    stage_timeout,
)
from app.tools.executor import ToolExecutionContext, ToolExecutor
from app.tools.registry import ToolRegistry


def test_stage_timeout_is_limited_by_stage_budget(monkeypatch):
    monkeypatch.setattr(deadline_module.time, "monotonic", lambda: 100.0)
    deadline = create_deadline(60)

    assert stage_timeout(deadline, 5) == 5


def test_stage_timeout_is_limited_by_request_remainder(monkeypatch):
    monkeypatch.setattr(deadline_module.time, "monotonic", lambda: 100.0)
    deadline = create_deadline(0.05)

    assert stage_timeout(deadline, 20) == pytest.approx(0.05)


def test_expired_deadline_returns_zero(monkeypatch):
    monkeypatch.setattr(deadline_module.time, "monotonic", lambda: 100.0)
    deadline = create_deadline(0)

    assert remaining_seconds(deadline) == 0
    assert stage_timeout(deadline, 5) == 0


def test_require_remaining_rejects_expired_request(monkeypatch):
    monkeypatch.setattr(deadline_module.time, "monotonic", lambda: 100.0)
    deadline = create_deadline(0)

    with pytest.raises(DeadlineExceeded) as exc_info:
        require_remaining(deadline, 5)

    assert exc_info.value.code == "deadline_exceeded"


def test_missing_deadline_uses_stage_budget():
    assert stage_timeout(None, 3) == 3


def test_deadline_reserves_time_for_final_generation(monkeypatch):
    monkeypatch.setattr(deadline_module.time, "monotonic", lambda: 100.0)
    request_deadline = create_deadline(60)

    dispatch_deadline = deadline_before_reserve(request_deadline, 20)

    assert dispatch_deadline == 140.0
    assert remaining_seconds(dispatch_deadline) == 40.0


def test_reserve_never_returns_a_past_deadline(monkeypatch):
    monkeypatch.setattr(deadline_module.time, "monotonic", lambda: 100.0)

    assert deadline_before_reserve(110.0, 20) == 100.0


@pytest.mark.asyncio
async def test_tool_retries_share_one_operation_budget(monkeypatch):
    executor_module = __import__("app.tools.executor", fromlist=["tool_registry"])
    registry = ToolRegistry()
    attempts = 0

    async def slow_failure():
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0.03)
        raise RuntimeError("temporary failure")

    registry.register("slow_tool", "test tool", slow_failure)
    monkeypatch.setattr(executor_module, "tool_registry", registry)
    executor = ToolExecutor(whitelist={"test": {"slow_tool"}})

    started_at = time.perf_counter()
    result = await executor.execute(
        "slow_tool",
        context=ToolExecutionContext(
            agent_name="test",
            timeout_seconds=0.05,
            retry=1,
        ),
    )
    elapsed = time.perf_counter() - started_at

    assert result.status == "timeout"
    assert attempts == 2
    assert elapsed < 0.09


@pytest.mark.asyncio
async def test_sync_network_tool_can_be_timed_out(monkeypatch):
    executor_module = __import__("app.tools.executor", fromlist=["tool_registry"])
    registry = ToolRegistry()

    def slow_sync_tool():
        time.sleep(0.2)
        return {"ok": True}

    registry.register("slow_sync_tool", "test sync tool", slow_sync_tool)
    monkeypatch.setattr(executor_module, "tool_registry", registry)
    executor = ToolExecutor(whitelist={"test": {"slow_sync_tool"}})

    started_at = time.perf_counter()
    result = await executor.execute(
        "slow_sync_tool",
        context=ToolExecutionContext(
            agent_name="test",
            timeout_seconds=0.02,
        ),
    )
    elapsed = time.perf_counter() - started_at

    assert result.status == "timeout"
    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_orchestrator_retries_share_parent_deadline(monkeypatch):
    orchestrator_module = __import__(
        "app.agents.orchestrator",
        fromlist=["agent_registry"],
    )
    registry = AgentRegistry()

    class SlowFailingAgent:
        def __init__(self):
            self.attempts = 0

        async def handle(self, request):
            self.attempts += 1
            await asyncio.sleep(0.03)
            raise RuntimeError("temporary agent failure")

    agent = SlowFailingAgent()
    registry.register("slow", agent)
    monkeypatch.setattr(orchestrator_module, "agent_registry", registry)

    result = await AgentOrchestrator(timeout_seconds=1).dispatch(
        tasks=[
            {
                "task_id": "slow-task",
                "agent_name": "slow",
                "timeout_seconds": 1,
                "retry": 1,
            }
        ],
        user_profile={},
        deadline_monotonic=create_deadline(0.05),
    )

    response = AgentResponse(**result["responses"]["slow-task"])
    assert response.status == "timeout"
    assert response.error["code"] == "deadline_exceeded"
    assert agent.attempts == 2


@pytest.mark.asyncio
async def test_agent_retry_gets_fresh_attempt_budget(monkeypatch):
    orchestrator_module = __import__(
        "app.agents.orchestrator",
        fromlist=["agent_registry"],
    )
    registry = AgentRegistry()

    class SlowThenSuccessfulAgent:
        def __init__(self):
            self.deadlines = []

        async def handle(self, request):
            self.deadlines.append(request.deadline_monotonic)
            if len(self.deadlines) == 1:
                await asyncio.sleep(0.03)
            return AgentResponse(
                agent_name="retrying",
                task_type="test",
                result={"ok": True},
            )

    agent = SlowThenSuccessfulAgent()
    registry.register("retrying", agent)
    monkeypatch.setattr(orchestrator_module, "agent_registry", registry)

    result = await AgentOrchestrator(timeout_seconds=1).dispatch(
        tasks=[
            {
                "task_id": "retrying-task",
                "agent_name": "retrying",
                "task_type": "test",
                "timeout_seconds": 0.05,
                "attempt_timeout_seconds": 0.02,
                "retry": 1,
            }
        ],
        user_profile={},
        deadline_monotonic=create_deadline(0.1),
    )

    response = AgentResponse(**result["responses"]["retrying-task"])
    assert response.status == "success"
    assert response.metadata["attempt"] == 2
    assert len(agent.deadlines) == 2
    assert agent.deadlines[1] > agent.deadlines[0]


@pytest.mark.asyncio
async def test_specialist_plan_reserves_one_retry_per_agent():
    result = await plan_tasks(
        HealthAdvisorState(
            user_message="请做饮食分析，并安排一个30分钟运动计划",
            intent="general_health",
            context={"profile": {}},
        )
    )
    tasks = {task["task_id"]: task for task in result["sub_tasks"]}

    nutrition = tasks["nutrition_analysis"]
    assert nutrition["attempt_timeout_seconds"] == 25
    assert nutrition["timeout_seconds"] == 50
    assert nutrition["retry"] == 1

    exercise = tasks["exercise_plan"]
    assert exercise["attempt_timeout_seconds"] == 25
    assert exercise["timeout_seconds"] == 50
    assert exercise["retry"] == 1


@pytest.mark.asyncio
async def test_slow_chat_persistence_continues_after_response_budget(monkeypatch):
    chat_module = __import__(
        "app.api.v1.chat_routes",
        fromlist=["_persist_normal_chat_turn"],
    )
    finished = asyncio.Event()

    async def slow_persistence(*args, **kwargs):
        await asyncio.sleep(0.03)
        finished.set()
        return "测试会话"

    monkeypatch.setattr(chat_module, "_persist_chat_turn_and_title", slow_persistence)
    monkeypatch.setattr(chat_module.settings, "chat_persistence_timeout_seconds", 0.01)

    message_id, title, scheduled = await chat_module._persist_normal_chat_turn(
        "session-id",
        "测试问题",
        HealthAdvisorState(response="测试回答", trace_id="trace-id"),
        create_deadline(0.1),
    )

    assert message_id
    assert title == "测试问题"
    assert scheduled is True
    assert chat_module._CHAT_PERSISTENCE_TASKS
    await asyncio.wait_for(finished.wait(), timeout=0.1)
    await asyncio.sleep(0)
    assert not chat_module._CHAT_PERSISTENCE_TASKS


@pytest.mark.asyncio
async def test_chat_persistence_timeout_error_is_not_reported_as_pending(monkeypatch):
    chat_module = __import__(
        "app.api.v1.chat_routes",
        fromlist=["_persist_normal_chat_turn"],
    )

    async def failed_persistence(*args, **kwargs):
        raise asyncio.TimeoutError("database timeout")

    monkeypatch.setattr(chat_module, "_persist_chat_turn_and_title", failed_persistence)

    with pytest.raises(asyncio.TimeoutError, match="database timeout"):
        await chat_module._persist_normal_chat_turn(
            "session-id",
            "测试问题",
            HealthAdvisorState(response="测试回答", trace_id="trace-id"),
            create_deadline(0.1),
        )


@pytest.mark.asyncio
async def test_health_advisor_returns_explainable_timeout_result():
    class SlowGraph:
        async def ainvoke(self, state):
            await asyncio.sleep(0.1)
            return state

    agent = HealthAdvisorAgent()
    agent._graph = SlowGraph()
    state = HealthAdvisorState(user_message="请分析我的健康情况")
    state["deadline_monotonic"] = create_deadline(0.01)

    result = await agent.process(state)

    assert result["status"] == "timeout"
    assert result["response"].strip()
    assert result["degraded"] is True
    assert result["degradation_reason"] == "deadline_exceeded"


@pytest.mark.asyncio
async def test_chat_pipeline_continues_after_optional_stage_timeout(monkeypatch):
    chat_module = __import__(
        "app.api.v1.chat_routes",
        fromlist=["_process_state"],
    )
    monkeypatch.setattr(chat_module.settings, "context_timeout_seconds", 0.01)

    async def safe(state):
        state["safety_flag"] = {"is_urgent": False}
        return state

    async def slow_context(state, db):
        await asyncio.sleep(0.1)
        return state

    async def classify(state):
        state["intent"] = "general_health"
        return state

    async def memory_route(state):
        state["memory_policy"] = {"needs_rag": False}
        return state

    async def retrieve(state, db):
        return state

    async def plan(state):
        state["sub_tasks"] = []
        return state

    async def generate(state):
        state["response"] = "这是未依赖上下文生成的本地降级回答。"
        return state

    async def finish(state, db):
        return state

    monkeypatch.setattr(chat_module, "check_safety", safe)
    monkeypatch.setattr(chat_module, "load_context", slow_context)
    monkeypatch.setattr(chat_module, "classify_intent", classify)
    monkeypatch.setattr(chat_module, "memory_route", memory_route)
    monkeypatch.setattr(chat_module, "retrieve_memory", retrieve)
    monkeypatch.setattr(chat_module, "plan_tasks", plan)
    monkeypatch.setattr(chat_module, "generate_response", generate)
    monkeypatch.setattr(chat_module, "post_process", finish)

    result = await chat_module._process_state(
        HealthAdvisorState(user_message="如何保持健康？")
    )

    assert result["agent_trace"]["load_context"]["status"] == "timeout"
    assert result["degraded"] is True
    assert result["response"].strip()
