"""Tests for intent-aware local fallbacks after unusable LLM responses."""

from importlib import import_module
from unittest.mock import AsyncMock

import pytest

from app.agents.health_advisor.nodes.generate_response import generate_response
from app.agents.health_advisor.state import HealthAdvisorState
from app.agents.nutrition.nodes.general_nutrition_advice import (
    general_nutrition_advice,
)
from app.agents.nutrition.nodes.generate_recommendations import (
    generate_recommendations,
)
from app.config import settings
from app.llm.deepseek import LLMResponseError


def _empty_response_error() -> LLMResponseError:
    return LLMResponseError("empty_response", "LLM returned no usable content")


@pytest.mark.asyncio
async def test_health_advisor_uses_intent_fallback_and_marks_degraded(monkeypatch):
    generation_module = import_module(
        "app.agents.health_advisor.nodes.generate_response"
    )
    monkeypatch.setattr(
        generation_module.deepseek_client,
        "chat",
        AsyncMock(side_effect=_empty_response_error()),
    )
    state = HealthAdvisorState(user_message="素食饮食如何补充蛋白质？")
    state["intent"] = "nutrition"

    result = await generate_response(state)

    assert result["response"].strip()
    assert "饮食" in result["response"]
    assert "优质蛋白" in result["response"]
    assert result["degraded"] is True
    assert result["degradation_reason"] == "empty_response"
    assert result["degradation_events"] == [
        {
            "stage": "health_advisor.generate_response",
            "code": "empty_response",
        }
    ]


@pytest.mark.asyncio
async def test_health_advisor_preserves_specialist_result_when_final_llm_fails(
    monkeypatch,
):
    generation_module = import_module(
        "app.agents.health_advisor.nodes.generate_response"
    )
    monkeypatch.setattr(
        generation_module.deepseek_client,
        "chat",
        AsyncMock(side_effect=TimeoutError("provider timeout")),
    )
    state = HealthAdvisorState(user_message="想减脂，帮我安排30分钟居家运动。")
    state["intent"] = "exercise"
    state["aggregated_agent_context"] = {
        "exercise": {
            "summary": "",
            "data": {
                "response": "## 30分钟居家运动\n热身5分钟，主体训练20分钟，拉伸5分钟。"
            },
        }
    }

    result = await generate_response(state)

    assert "30分钟居家运动" in result["response"]
    assert "热身5分钟" in result["response"]
    assert result["degraded"] is True
    assert result["degradation_reason"] == "timeout"


@pytest.mark.asyncio
async def test_general_nutrition_fallback_is_usable_and_marked(monkeypatch):
    module = import_module("app.agents.nutrition.nodes.general_nutrition_advice")
    monkeypatch.setattr(
        module.deepseek_client,
        "chat",
        AsyncMock(side_effect=_empty_response_error()),
    )

    result = await general_nutrition_advice(
        {
            "user_message": "素食饮食如何补充蛋白质？",
            "query_intent": "nutrition_knowledge",
        }
    )

    assert result["response"].strip()
    assert result["degraded"] is True
    assert result["degradation_reason"] == "empty_response"


@pytest.mark.asyncio
async def test_nutrition_recommendations_use_rules_after_invalid_json(monkeypatch):
    module = import_module(
        "app.agents.nutrition.nodes.generate_recommendations"
    )
    fake_client = AsyncMock()
    fake_client.json_chat.side_effect = LLMResponseError(
        "invalid_json",
        "LLM returned invalid JSON",
    )
    monkeypatch.setattr(module, "DeepSeekClient", lambda: fake_client)

    result = await generate_recommendations(
        {
            "user_id": "user-1",
            "extracted_foods": [{"name": "豆腐"}],
            "total_nutrition": {
                "calories": 400,
                "protein": 10,
                "carbs": 50,
                "fat": 15,
                "fiber": 3,
            },
            "nutrition_analysis": "已有规则分析。",
            "health_score": 70,
        }
    )

    assert result["recommendations"]
    assert result["nutrition_recommendation_status"] == "fallback"
    assert result["degraded"] is True
    assert result["degradation_reason"] == "invalid_json"


@pytest.mark.asyncio
async def test_optional_environment_llm_failure_keeps_rule_result(monkeypatch):
    module = import_module(
        "app.agents.environment.nodes.llm_generate_advice"
    )
    monkeypatch.setattr(settings, "environment_llm_advice_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(
        module.deepseek_client,
        "chat",
        AsyncMock(side_effect=LLMResponseError("content_filtered", "filtered")),
    )
    state = {
        "user_message": "今天适合跑步吗？",
        "location": {"city": "杭州"},
        "health_risk": {"overall_risk": "moderate"},
        "recommendations": [{"title": "降低强度"}],
    }

    result = await module.llm_generate_advice(state)

    assert result["recommendations"] == [{"title": "降低强度"}]
    assert result["llm_advice_status"] == "failed"
    assert result["degraded"] is True
    assert result["degradation_reason"] == "content_filtered"


@pytest.mark.asyncio
async def test_optional_exercise_llm_failure_keeps_baseline_plan(monkeypatch):
    module = import_module("app.agents.exercise.nodes.llm_refine_plan")
    monkeypatch.setattr(settings, "exercise_llm_refine_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(module, "_retrieve_exercise_guidelines", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        module.deepseek_client,
        "json_chat",
        AsyncMock(side_effect=LLMResponseError("truncated_response", "truncated")),
    )
    state = {
        "user_message": "安排30分钟居家运动",
        "fitness_level": "beginner",
        "fitness_goals": ["减脂"],
        "time_available": 30,
        "workout_plan": {"total_duration": 30},
        "exercises": [{"name": "快走", "duration": 20}],
        "safety_notes": ["循序渐进"],
    }

    result = await module.llm_refine_plan(state)

    assert result["workout_plan"]["total_duration"] == 30
    assert result["exercises"][0]["name"] == "快走"
    assert result["llm_refine_status"] == "failed"
    assert result["degraded"] is True
    assert result["degradation_reason"] == "truncated_response"
