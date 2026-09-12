"""Post-processing node for Health Advisor Agent."""

import asyncio
import logging

from app.agents.health_advisor.prompts import FOLLOWUP_QUESTIONS_PROMPT
from app.agents.health_advisor.state import HealthAdvisorState
from app.llm.deepseek import deepseek_client
from app.memory.extraction import (
    candidates_to_profile_updates,
    extract_profile_updates,
    extract_rule_profile_candidates,
    format_confirmation_prompt,
    merge_profile_updates,
    resolve_confirmation_intent,
)
from app.memory.long_term import long_term_memory
from app.memory.profile import profile_manager
from app.memory.short_term import short_term_memory
from app.models.database import async_session
from app.services.suggested_questions import filter_suggested_questions

logger = logging.getLogger(__name__)

def _extract_profile_from_response(response: str, user_message: str) -> dict:
    """Backward-compatible rule-only view used by existing callers/tests."""
    del response
    candidates = extract_rule_profile_candidates(user_message)
    return candidates_to_profile_updates(
        [candidate for candidate in candidates if not candidate.requires_confirmation]
    )


async def _generate_followup_questions(
    user_message: str,
    response: str,
    profile: dict,
) -> list[str]:
    """Generate follow-up questions.

    Args:
        user_message: Original user message
        response: Generated response
        profile: User profile

    Returns:
        List of follow-up questions
    """
    try:
        prompt = FOLLOWUP_QUESTIONS_PROMPT.format(
            user_message=user_message,
            response=response,
            user_profile=str(profile),
        )

        result = await deepseek_client.json_chat(
            system_prompt="你是一个帮助生成健康咨询后续问题的AI助手。",
            user_message=prompt,
        )

        # Handle different result formats
        questions = []
        if isinstance(result, dict):
            questions = result.get("questions", [])
        elif isinstance(result, list):
            questions = result

        filtered = filter_suggested_questions(
            questions if isinstance(questions, list) else [],
            current_question=user_message,
            fallback=_fallback_followup_questions(user_message, response),
        )
        if filtered:
            return filtered

        # Fallback questions
        return _fallback_followup_questions(user_message, response)

    except Exception as e:
        logger.error(f"Follow-up question generation failed: {e}")
        return _fallback_followup_questions(user_message, response)


def _fallback_followup_questions(user_message: str, response: str = "") -> list[str]:
    """Build topic-aware fallback follow-up questions."""
    text = f"{user_message} {response}"
    if any(keyword in text for keyword in ("运动", "跑步", "锻炼", "健身", "活动量")):
        return [
            "结合我的情况安排一周运动计划？",
            "怎么判断运动强度是否合适？",
            "运动后需要注意哪些恢复事项？",
        ]
    if any(keyword in text for keyword in ("饮食", "早餐", "晚餐", "营养", "蛋白", "减脂", "控糖")):
        return [
            "帮我制定一天的饮食搭配？",
            "哪些食物更适合我的目标？",
            "这类饮食有什么注意事项？",
        ]
    if any(keyword in text for keyword in ("睡眠", "作息", "熬夜", "失眠", "早醒")):
        return [
            "怎么制定可执行的作息计划？",
            "睡前有哪些习惯需要调整？",
            "如何判断睡眠是否改善？",
        ]
    if any(keyword in text for keyword in ("天气", "空气", "温度", "湿度", "户外")):
        return [
            "今天适合安排什么运动？",
            "户外运动需要注意什么？",
            "空气不好时如何替代训练？",
        ]
    return [
        "结合我的情况下一步怎么做？",
        "有哪些需要重点注意的风险？",
        "可以帮我制定一个执行计划吗？",
    ]


def _update_short_term_memory(
    user_id: str,
    session_id: str,
    user_message: str,
    response: str,
    extracted_profile: dict,
):
    """Update in-process short-term memory before the next user turn."""
    try:
        # Update short-term memory
        short_term_memory.add_message(session_id, "user", user_message)
        short_term_memory.add_message(session_id, "assistant", response)

        logger.info(f"Updated short-term memory for session {session_id}")

    except Exception as e:
        logger.error(f"Failed to update memory: {e}")


async def _persist_profile_update(
    user_id: str,
    extracted_profile: dict,
    db=None,
) -> bool:
    """Persist structured profile fields to PostgreSQL."""
    if not user_id or not extracted_profile:
        return False

    if db is not None:
        return await profile_manager.update_profile(db, user_id, extracted_profile)

    async with async_session() as session:
        return await profile_manager.update_profile(session, user_id, extracted_profile)


async def _profile_update_background_task(
    user_id: str,
    extracted_profile: dict,
) -> None:
    try:
        updated = await _persist_profile_update(user_id, extracted_profile)
        logger.info(
            "Structured profile background update %s for user %s",
            "finished" if updated else "skipped",
            user_id,
        )
    except Exception:
        logger.exception("Structured profile background update failed for user %s", user_id)


def _trigger_profile_update(user_id: str, extracted_profile: dict) -> bool:
    """Schedule structured profile persistence without blocking the response."""
    if not user_id or not extracted_profile:
        return False

    try:
        asyncio.create_task(_profile_update_background_task(user_id, extracted_profile))
        return True
    except RuntimeError:
        logger.exception("Failed to schedule structured profile update for user %s", user_id)
        return False


def _append_response_note(state: HealthAdvisorState, note: str) -> None:
    note = str(note or "").strip()
    if not note:
        return
    response = str(state.get("response") or "").rstrip()
    state["response"] = f"{response}\n\n{note}" if response else note


def _resolve_pending_profile_confirmation(
    session_id: str,
    user_message: str,
) -> tuple[str | None, dict]:
    pending = short_term_memory.get_pending_profile_confirmations(session_id)
    if not pending:
        return None, {}

    intent = resolve_confirmation_intent(user_message)
    if intent == "confirm":
        confirmed = short_term_memory.pop_pending_profile_confirmations(session_id)
        return "confirmed", candidates_to_profile_updates(confirmed)
    if intent == "reject":
        short_term_memory.pop_pending_profile_confirmations(session_id)
        return "rejected", {}
    return "awaiting", {}


async def post_process(
    state: HealthAdvisorState,
    db=None,  # Optional db session for background tasks
) -> HealthAdvisorState:
    """Post-process the response.

    Performs:
    1. Generate follow-up questions
    2. Extract structured profile updates and trigger async persistence
    3. Update short-term memory
    4. Extract and persist long-term semantic memories

    Args:
        state: Current state with generated response
        db: Optional database session for background tasks

    Returns:
        Updated state with post-processing results
    """
    user_message = state.get("user_message", "")
    response = state.get("response", "")
    profile = state.get("context", {}).get("profile", {})
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")

    logger.info("Post-processing response")

    # 1. Generate follow-up questions
    try:
        suggested_questions = await _generate_followup_questions(
            user_message, response, profile
        )
        state["suggested_questions"] = suggested_questions
        logger.info(f"Generated {len(suggested_questions)} follow-up questions")
    except Exception as e:
        logger.error(f"Failed to generate follow-up questions: {e}")
        state["suggested_questions"] = [
            "您还有其他健康方面的问题吗？",
            "您想了解更多关于这方面的信息吗？",
        ]

    # 2. Resolve prior confirmations, then run guarded rule + LLM extraction.
    try:
        confirmation_status, confirmed_profile = _resolve_pending_profile_confirmation(
            session_id,
            user_message,
        )
        state["profile_confirmation_status"] = confirmation_status

        if confirmation_status == "confirmed":
            _append_response_note(state, "已按你的确认更新健康档案。")
        elif confirmation_status == "rejected":
            _append_response_note(state, "好的，本次候选健康信息不会写入健康档案。")

        # A pure confirmation/rejection message should not trigger another LLM extraction pass.
        if confirmation_status in {"confirmed", "rejected"}:
            extraction_outcome = None
            extracted_profile = confirmed_profile
        else:
            extraction_outcome = await extract_profile_updates(user_message)
            extracted_profile = merge_profile_updates(
                confirmed_profile,
                extraction_outcome.accepted_updates,
            )
            state["profile_extraction_trace"] = extraction_outcome.trace
            state["profile_rejected_candidates"] = extraction_outcome.rejected_candidates

            if extraction_outcome.pending_confirmations:
                pending_payload = [
                    candidate.model_dump() for candidate in extraction_outcome.pending_confirmations
                ]
                short_term_memory.set_pending_profile_confirmations(session_id, pending_payload)
                state["pending_profile_confirmations"] = pending_payload
                state["profile_confirmation_required"] = True
                state["suggested_questions"] = ["确认记录", "不要记录"]
                pending_summary = format_confirmation_prompt(extraction_outcome.pending_confirmations)
                _append_response_note(
                    state,
                    "为了避免错误写入敏感健康信息，请确认是否记录："
                    f"{pending_summary}。请回复“确认记录”或“不要记录”。",
                )

        if extracted_profile:
            logger.info(
                "Validated profile update sections=%s",
                sorted(extracted_profile.keys()),
            )
            state["extracted_profile"] = extracted_profile
            state["profile_update_scheduled"] = _trigger_profile_update(user_id, extracted_profile)
            state["profile_updated"] = False
    except Exception as e:
        logger.exception("Profile extraction failed: %s", e)

    # 3. Update short-term memory synchronously so immediate follow-ups can use it.
    try:
        _update_short_term_memory(
            user_id,
            session_id,
            user_message,
            state.get("response", response),
            state.get("extracted_profile", {}),
        )
        logger.info("Short-term memory updated")

    except Exception as e:
        logger.error(f"Failed to update short-term memory: {e}")

    # 4. Extract and persist long-term semantic memories into Elasticsearch.
    try:
        stored_memory_ids = await long_term_memory.store_user_message_memories(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            assistant_response=state.get("response", response),
            extracted_profile=state.get("extracted_profile", {}),
        )
        state["stored_memory_ids"] = stored_memory_ids
        if stored_memory_ids:
            logger.info("Stored %d long-term memory facts", len(stored_memory_ids))
    except Exception as e:
        logger.error(f"Failed to update long-term memory: {e}")

    # Mark as complete
    state["next_node"] = "end"

    return state
