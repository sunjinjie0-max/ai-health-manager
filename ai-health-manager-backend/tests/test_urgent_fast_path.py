"""Regression tests for the deterministic emergency response path."""

import asyncio
import math
import time
from importlib import import_module
from unittest.mock import AsyncMock

import pytest

from app.agents.health_advisor.agent import HealthAdvisorAgent
from app.agents.health_advisor.nodes.urgent_reply import urgent_reply
from app.agents.health_advisor.state import HealthAdvisorState
from app.api.v1.chat_routes import _process_state


def _urgent_state() -> HealthAdvisorState:
    return HealthAdvisorState(
        user_id="user-urgent",
        session_id="session-urgent",
        user_message="我现在胸痛而且呼吸困难。",
        trace_id="trace-urgent",
    )


@pytest.mark.asyncio
async def test_urgent_template_is_focused_and_ends_the_sync_path(monkeypatch):
    post_process_module = import_module(
        "app.agents.health_advisor.nodes.post_process"
    )
    monkeypatch.setattr(
        post_process_module,
        "schedule_urgent_post_process",
        lambda state: True,
    )

    state = _urgent_state()
    state["safety_flag"] = {
        "is_urgent": True,
        "risk_level": "high",
        "warning_message": "可能存在危及生命的紧急情况。",
        "recommendations": ["立即拨打120", "立即前往急诊"],
    }

    result = await urgent_reply(state)

    assert result["next_node"] == "end"
    assert result["suggested_questions"] == []
    assert result["post_process_scheduled"] is True
    assert "立即拨打120" in result["response"]
    assert "急诊" in result["response"]
    assert "不要自行等待" in result["response"]
    assert "doubt" not in result["response"]
    assert "如果您的情况不是紧急情况" not in result["response"]


@pytest.mark.asyncio
async def test_agent_urgent_path_skips_slow_external_dependencies(monkeypatch):
    agent_module = import_module("app.agents.health_advisor.agent")
    safety_module = import_module("app.agents.health_advisor.nodes.check_safety")
    post_process_module = import_module(
        "app.agents.health_advisor.nodes.post_process"
    )

    unavailable_db_or_redis = AsyncMock(
        side_effect=AssertionError("context dependencies must not be called")
    )
    unavailable_es_or_llm_post_process = AsyncMock(
        side_effect=AssertionError("post-processing dependencies must not be called")
    )
    unavailable_safety_llm = AsyncMock(
        side_effect=AssertionError("deterministic emergency must not call the LLM")
    )
    monkeypatch.setattr(agent_module, "load_context", unavailable_db_or_redis)
    monkeypatch.setattr(
        agent_module,
        "post_process",
        unavailable_es_or_llm_post_process,
    )
    monkeypatch.setattr(
        safety_module.deepseek_client,
        "json_chat",
        unavailable_safety_llm,
    )
    monkeypatch.setattr(
        post_process_module,
        "schedule_urgent_post_process",
        lambda state: True,
    )

    started_at = time.perf_counter()
    result = await asyncio.wait_for(
        HealthAdvisorAgent().process(_urgent_state()),
        timeout=0.5,
    )
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.5
    assert result["safety_flag"]["is_urgent"] is True
    assert "立即拨打120" in result["response"]
    unavailable_db_or_redis.assert_not_awaited()
    unavailable_es_or_llm_post_process.assert_not_awaited()
    unavailable_safety_llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_urgent_path_p95_is_below_three_seconds(monkeypatch):
    post_process_module = import_module(
        "app.agents.health_advisor.nodes.post_process"
    )
    safety_module = import_module("app.agents.health_advisor.nodes.check_safety")
    unavailable_safety_llm = AsyncMock(
        side_effect=AssertionError("deterministic emergency must not call the LLM")
    )
    monkeypatch.setattr(
        safety_module.deepseek_client,
        "json_chat",
        unavailable_safety_llm,
    )
    monkeypatch.setattr(
        post_process_module,
        "schedule_urgent_post_process",
        lambda state: True,
    )

    agent = HealthAdvisorAgent()
    durations = []
    for _ in range(30):
        started_at = time.perf_counter()
        result = await agent.process(_urgent_state())
        durations.append(time.perf_counter() - started_at)
        assert result["safety_flag"]["is_urgent"] is True

    p95_index = math.ceil(len(durations) * 0.95) - 1
    assert sorted(durations)[p95_index] < 3
    unavailable_safety_llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_pipeline_urgent_path_skips_slow_external_dependencies(monkeypatch):
    chat_module = import_module("app.api.v1.chat_routes")
    safety_module = import_module("app.agents.health_advisor.nodes.check_safety")
    post_process_module = import_module(
        "app.agents.health_advisor.nodes.post_process"
    )

    unavailable_db_or_redis = AsyncMock(
        side_effect=AssertionError("context dependencies must not be called")
    )
    unavailable_es_or_llm_post_process = AsyncMock(
        side_effect=AssertionError("post-processing dependencies must not be called")
    )
    unavailable_safety_llm = AsyncMock(
        side_effect=AssertionError("deterministic emergency must not call the LLM")
    )
    monkeypatch.setattr(chat_module, "load_context", unavailable_db_or_redis)
    monkeypatch.setattr(
        chat_module,
        "post_process",
        unavailable_es_or_llm_post_process,
    )
    monkeypatch.setattr(
        safety_module.deepseek_client,
        "json_chat",
        unavailable_safety_llm,
    )
    monkeypatch.setattr(
        post_process_module,
        "schedule_urgent_post_process",
        lambda state: True,
    )

    result = await asyncio.wait_for(_process_state(_urgent_state()), timeout=0.5)

    assert result["safety_flag"]["is_urgent"] is True
    assert set(result["agent_trace"]) == {"check_safety", "urgent_reply"}
    unavailable_db_or_redis.assert_not_awaited()
    unavailable_es_or_llm_post_process.assert_not_awaited()
    unavailable_safety_llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_slow_elasticsearch_memory_write_runs_after_urgent_reply(monkeypatch):
    post_process_module = import_module(
        "app.agents.health_advisor.nodes.post_process"
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_memory_write(**kwargs):
        started.set()
        await release.wait()
        return []

    monkeypatch.setattr(
        post_process_module.long_term_memory,
        "store_user_message_memories",
        slow_memory_write,
    )

    state = _urgent_state()
    state["safety_flag"] = {
        "is_urgent": True,
        "risk_level": "high",
        "warning_message": "可能存在危及生命的紧急情况。",
        "recommendations": ["立即拨打120", "立即前往急诊"],
    }
    result = await asyncio.wait_for(urgent_reply(state), timeout=0.5)

    assert result["post_process_scheduled"] is True
    await asyncio.wait_for(started.wait(), timeout=0.5)
    assert post_process_module._BACKGROUND_TASKS

    release.set()
    await asyncio.gather(*tuple(post_process_module._BACKGROUND_TASKS))
