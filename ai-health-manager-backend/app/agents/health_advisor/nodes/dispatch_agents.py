"""Sub-agent dispatch node for Health Advisor Agent."""

import logging

from app.agents.health_advisor.state import HealthAdvisorState
from app.agents.orchestrator import orchestrator
from app.config import settings
from app.core.deadline import deadline_before_reserve

logger = logging.getLogger(__name__)


async def dispatch_agents(state: HealthAdvisorState) -> HealthAdvisorState:
    """Dispatch planned specialist tasks through the orchestrator."""
    tasks = state.get("sub_tasks", [])
    if not tasks:
        state["orchestration_status"] = "not_required"
        state["next_node"] = "rag_retrieve"
        return state

    context = state.get("context", {})
    profile = context.get("profile", {})

    try:
        dispatch_deadline = deadline_before_reserve(
            state.get("deadline_monotonic"),
            settings.final_generation_timeout_seconds,
        )
        dispatch_result = await orchestrator.dispatch(
            tasks=tasks,
            user_profile=profile,
            user_id=state.get("user_id", "anonymous"),
            session_id=state.get("session_id", ""),
            user_message=state.get("user_message", ""),
            deadline_monotonic=dispatch_deadline,
        )
        state["sub_agent_results"] = dispatch_result.get("responses", {})
        state["agent_trace"] = {
            "trace_id": dispatch_result.get("trace_id"),
            "completed": list(dispatch_result.get("completed", {}).keys()),
            "failed": list(dispatch_result.get("failed", {}).keys()),
        }
        state["orchestration_status"] = "success" if dispatch_result.get("success") else "partial"
        if dispatch_result.get("degraded"):
            state["orchestration_status"] = "partial"
            state["degraded"] = True
            state.setdefault("degradation_events", []).append(
                {
                    "stage": "dispatch_agents",
                    "code": "optional_task_timeout",
                }
            )
        logger.info(
            "Sub-agent dispatch finished with status=%s trace=%s",
            state["orchestration_status"],
            state["agent_trace"].get("trace_id"),
        )
    except Exception as exc:
        logger.exception("Sub-agent dispatch failed")
        state["sub_agent_results"] = {}
        state["agent_trace"] = {"error": str(exc)}
        state["orchestration_status"] = "failed"

    state["next_node"] = "aggregate_results"
    return state
