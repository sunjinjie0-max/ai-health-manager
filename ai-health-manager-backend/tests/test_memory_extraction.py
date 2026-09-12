"""Tests for the guarded rule + LLM profile extraction pipeline."""

from importlib import import_module
from unittest.mock import AsyncMock

import pytest

from app.agents.health_advisor.state import HealthAdvisorState
from app.config import settings
from app.memory.extraction import extract_profile_updates
from app.memory.short_term import short_term_memory


@pytest.mark.asyncio
async def test_rule_extraction_separates_high_risk_confirmation(monkeypatch):
    monkeypatch.setattr(settings, "profile_use_llm_supplement", False)

    outcome = await extract_profile_updates(
        "我30岁，男性，对芒果过敏，我想减脂，平时不吃香菜。"
    )

    assert outcome.accepted_updates["basic_info"] == {"age": 30, "gender": "male"}
    assert "减脂" in outcome.accepted_updates["health_goals"]
    assert "香菜" in outcome.accepted_updates["diet_preferences"]["avoid"]
    assert "health_status" not in outcome.accepted_updates
    assert any(
        candidate.field == "allergies" and candidate.value == "芒果"
        for candidate in outcome.pending_confirmations
    )


@pytest.mark.asyncio
async def test_rule_extraction_does_not_turn_negation_into_high_risk_fact(monkeypatch):
    monkeypatch.setattr(settings, "profile_use_llm_supplement", False)

    outcome = await extract_profile_updates("我并不是对芒果过敏，也没有高血压。")

    assert not outcome.pending_confirmations
    assert "health_status" not in outcome.accepted_updates


@pytest.mark.asyncio
async def test_llm_supplement_requires_source_evidence(monkeypatch):
    monkeypatch.setattr(settings, "profile_use_llm_supplement", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(
        "app.memory.extraction.deepseek_client.json_chat",
        AsyncMock(
            return_value={
                "candidates": [
                    {
                        "section": "lifestyle",
                        "field": "exercise_frequency",
                        "value": "工作日很少运动",
                        "confidence": 0.88,
                        "evidence": "工作一忙我就很少运动",
                    },
                    {
                        "section": "health_status",
                        "field": "conditions",
                        "value": "糖尿病",
                        "confidence": 0.95,
                        "evidence": "并不存在于原文",
                    },
                ]
            }
        ),
    )

    outcome = await extract_profile_updates("工作一忙我就很少运动，而且经常忘记安排锻炼。")

    assert outcome.accepted_updates["lifestyle"]["exercise_frequency"] == "工作日很少运动"
    assert not outcome.pending_confirmations
    assert any(item["reason"] == "evidence_not_found_in_source" for item in outcome.rejected_candidates)


@pytest.mark.asyncio
async def test_high_risk_profile_is_written_only_after_confirmation(monkeypatch):
    module = import_module("app.agents.health_advisor.nodes.post_process")
    session_id = "confirmation-session"
    short_term_memory.clear(session_id)
    monkeypatch.setattr(settings, "profile_use_llm_supplement", False)
    monkeypatch.setattr(module, "_generate_followup_questions", AsyncMock(return_value=[]))
    monkeypatch.setattr(module.long_term_memory, "store_user_message_memories", AsyncMock(return_value=[]))

    persisted: list[dict] = []

    def fake_trigger(user_id: str, updates: dict) -> bool:
        persisted.append({"user_id": user_id, "updates": updates})
        return True

    monkeypatch.setattr(module, "_trigger_profile_update", fake_trigger)

    first = HealthAdvisorState(
        user_id="user-1",
        session_id=session_id,
        user_message="我对芒果过敏。",
    )
    first["response"] = "我会注意饮食安全。"
    first_result = await module.post_process(first)

    assert not persisted
    assert first_result["profile_confirmation_required"] is True
    assert first_result["suggested_questions"] == ["确认记录", "不要记录"]
    assert "确认是否记录" in first_result["response"]
    assert short_term_memory.get_pending_profile_confirmations(session_id)

    second = HealthAdvisorState(
        user_id="user-1",
        session_id=session_id,
        user_message="确认记录",
    )
    second["response"] = "好的。"
    second_result = await module.post_process(second)

    assert persisted[0]["updates"]["health_status"]["allergies"] == ["芒果"]
    assert second_result["profile_confirmation_status"] == "confirmed"
    assert "已按你的确认更新健康档案" in second_result["response"]
    assert not short_term_memory.get_pending_profile_confirmations(session_id)
    short_term_memory.clear(session_id)


@pytest.mark.asyncio
async def test_high_risk_profile_can_be_rejected(monkeypatch):
    module = import_module("app.agents.health_advisor.nodes.post_process")
    session_id = "rejection-session"
    short_term_memory.clear(session_id)
    monkeypatch.setattr(settings, "profile_use_llm_supplement", False)
    monkeypatch.setattr(module, "_generate_followup_questions", AsyncMock(return_value=[]))
    monkeypatch.setattr(module.long_term_memory, "store_user_message_memories", AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "_trigger_profile_update", lambda *_: True)

    first = HealthAdvisorState(user_id="user-1", session_id=session_id, user_message="我有高血压。")
    first["response"] = "我会考虑你的健康情况。"
    await module.post_process(first)

    second = HealthAdvisorState(user_id="user-1", session_id=session_id, user_message="不要记录")
    second["response"] = "好的。"
    result = await module.post_process(second)

    assert result["profile_confirmation_status"] == "rejected"
    assert "不会写入健康档案" in result["response"]
    assert not short_term_memory.get_pending_profile_confirmations(session_id)
    short_term_memory.clear(session_id)
