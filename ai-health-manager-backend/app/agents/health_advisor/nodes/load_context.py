"""Load context node for Health Advisor Agent.

Loads user profile, short-term conversation history, and other base context.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.health_advisor.state import HealthAdvisorState
from app.memory.profile import profile_manager
from app.memory.short_term import short_term_memory
from app.services.health_service import HealthService

logger = logging.getLogger(__name__)


async def load_context(
    state: HealthAdvisorState,
    db: AsyncSession,
) -> HealthAdvisorState:
    """Load context for the current conversation.

    Loads:
    - User profile from database
    - Recent conversation history (short-term memory)
    - Health data context

    Note:
    - Long-term memory retrieval is handled later by the memory routing stage.

    Args:
        state: Current state
        db: Database session

    Returns:
        Updated state with loaded context
    """
    user_id = state["user_id"]
    session_id = state["session_id"]

    logger.info(f"Loading context for user {user_id}, session {session_id}")

    existing_context = state.get("context", {}) or {}

    # Initialize context
    context = {
        "profile": existing_context.get("profile", {}),
        "short_term_history": existing_context.get("short_term_history", []),
        "long_term_memories": existing_context.get("long_term_memories", []),
        "health_data": existing_context.get("health_data", {}),
    }

    try:
        # Load user profile
        profile = await profile_manager.load_profile(db, user_id)
        if profile:
            context["profile"] = profile
        logger.debug(f"Loaded profile for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to load profile for user {user_id}: {e}")

    try:
        # Load short-term memory (recent conversation)
        short_history = short_term_memory.get_history(session_id)
        context["short_term_history"] = short_history
        logger.debug(f"Loaded {len(short_history)} messages from short-term memory")
    except Exception as e:
        logger.warning(f"Failed to load short-term memory: {e}")

    try:
        health_data = await HealthService(db).get_agent_context(user_id, days=30)
        context["health_data"] = health_data
        logger.debug(
            "Loaded health context for user %s with %d latest record groups",
            user_id,
            len(health_data.get("latest_records", {})),
        )
    except Exception as e:
        logger.warning(f"Failed to load health data context: {e}")

    # Update state with loaded context
    state["context"] = context
    state["next_node"] = "classify_intent"

    return state
