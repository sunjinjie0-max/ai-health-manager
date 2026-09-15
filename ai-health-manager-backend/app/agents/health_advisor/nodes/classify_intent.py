"""Intent classification node for Health Advisor Agent."""

import inspect
import json
import logging

from app.agents.health_advisor.prompts import INTENT_CLASSIFICATION_PROMPT
from app.agents.health_advisor.state import HealthAdvisorState
from app.config import settings
from app.llm.deepseek import deepseek_client, mark_llm_degraded

logger = logging.getLogger(__name__)


async def classify_intent(state: HealthAdvisorState) -> HealthAdvisorState:
    """Classify user intent and detect urgency.

    Analyzes the user message to determine:
    - Intent category (general_health, symptom_check, urgent_concern, etc.)
    - Urgency level (low, medium, high)
    - Whether medical attention is required

    Args:
        state: Current state with user message

    Returns:
        Updated state with intent classification
    """
    user_message = state.get("user_message", "")

    logger.info(f"Classifying intent for message: {user_message[:100]}...")

    # Build prompt
    prompt = INTENT_CLASSIFICATION_PROMPT + user_message

    try:
        # Call LLM for intent classification
        result = deepseek_client.json_chat(
            system_prompt="你是一个专门分析健康咨询意图的AI助手。",
            user_message=prompt,
            deadline_monotonic=state.get("deadline_monotonic"),
            timeout_seconds=settings.classification_timeout_seconds,
        )
        if inspect.isawaitable(result):
            result = await result

        # Parse result
        intent = result.get("intent", "general_health")
        confidence = result.get("confidence", 0.5)
        urgency = result.get("urgency", "low")
        requires_medical = result.get("requires_medical", False)

        logger.info(f"Intent classified: {intent}, urgency: {urgency}, confidence: {confidence}")

        # Update state
        state["intent"] = intent
        state["intent_confidence"] = confidence
        state["urgency"] = urgency
        state["requires_medical"] = requires_medical

        # Determine next node based on urgency and intent
        if urgency == "high":
            state["next_node"] = "urgent_reply"
        elif intent == "general_health":
            state["next_node"] = "rag_retrieve"
        else:
            state["next_node"] = "rag_retrieve"

    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        mark_llm_degraded(state, stage="health_advisor.classify_intent", error=e)
        # Fallback to general health
        state["intent"] = "general_health"
        state["intent_confidence"] = 0.0
        state["urgency"] = "low"
        state["requires_medical"] = False
        state["next_node"] = "rag_retrieve"

    return state
