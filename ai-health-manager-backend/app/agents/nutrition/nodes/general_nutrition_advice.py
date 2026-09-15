"""General nutrition advice node."""

import logging

from app.config import settings
from app.llm.deepseek import deepseek_client, mark_llm_degraded

logger = logging.getLogger(__name__)


def _fallback_response(query_intent: str) -> str:
    """Return a usable response when the LLM is unavailable."""
    if query_intent == "nutrition_knowledge":
        return (
            "这个问题属于一般营养知识，不需要先分析具体食物。"
            "你可以补充想了解的营养素、适用人群或健康目标，"
            "我会继续说明它的作用、常见食物来源和注意事项。"
        )

    return (
        "一般可以从规律进餐、食物多样化和控制总量开始。"
        "每餐尽量搭配主食、优质蛋白和蔬菜，"
        "减少高油、高盐和高糖食物，并结合自己的健康目标逐步调整。"
    )


async def general_nutrition_advice(state: dict) -> dict:
    """Answer requests that do not require extracting specific foods."""
    user_message = state.get("user_message", "")
    query_intent = state.get("query_intent", "general_advice")

    if query_intent == "nutrition_knowledge":
        system_prompt = (
            "你是专业营养健康助手。"
            "请回答用户的一般营养知识问题，解释概念、作用、"
            "常见食物来源和注意事项。"
            "不要虚构用户吃过的食物或具体营养数据。"
        )
    else:
        system_prompt = (
            "你是专业营养健康助手。"
            "请根据用户的健康目标提供一般饮食建议。"
            "用户没有提供具体餐食时，不要虚构食物、份量、"
            "热量或健康评分。建议应简洁、具体、可以执行。"
        )

    try:
        response = await deepseek_client.chat(
            system_prompt=system_prompt,
            user_message=user_message,
            stage="nutrition.general_advice",
            deadline_monotonic=state.get("deadline_monotonic"),
            timeout_seconds=settings.specialist_llm_timeout_seconds,
        )
        response = str(response or "").strip()

        if not response:
            raise ValueError("LLM returned an empty response")

    except Exception as exc:
        logger.warning(
            "[general_nutrition_advice] LLM failed, using fallback: %s",
            exc,
        )
        mark_llm_degraded(state, stage="nutrition.general_advice", error=exc)
        response = _fallback_response(query_intent)

    return {
        **state,
        "response": response,
        "nutrition_analysis": response,
        "recommendations": [],
    }
