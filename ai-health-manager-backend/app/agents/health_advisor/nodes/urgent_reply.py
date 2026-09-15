"""Urgent reply node for Health Advisor Agent.

Handles emergency situations with immediate warnings.
"""

import logging

from app.agents.health_advisor.state import HealthAdvisorState

logger = logging.getLogger(__name__)


# Urgent reply template
URGENT_REPLY_TEMPLATE = """🚨 **紧急医疗警告** 🚨

{warning_message}

**请立即采取以下行动：**

{recommendations}

---

**请记住：**
- 在线健康咨询不能替代紧急医疗服务
- 在紧急情况下，每一分钟都很重要
- 如有疑问，请优先选择立即就医，不要自行等待症状缓解
"""


async def urgent_reply(state: HealthAdvisorState) -> HealthAdvisorState:
    """Generate urgent reply for emergency situations.

    Args:
        state: Current state with safety flag

    Returns:
        Updated state with urgent reply
    """
    safety_flag = state.get("safety_flag", {})

    logger.warning("Generating urgent reply for safety concern")

    if not safety_flag or not safety_flag.get("is_urgent"):
        logger.error("urgent_reply called without urgent safety flag")
        state["response"] = "系统出现错误，请稍后再试。"
        state["next_node"] = "end"
        return state

    # Build recommendations list
    recommendations = safety_flag.get("recommendations", [])
    if recommendations:
        recommendations_text = "\n".join([f"{i+1}. {rec}" for i, rec in enumerate(recommendations)])
    else:
        recommendations_text = "1. 立即拨打120\n2. 前往最近的医院急诊室"

    # Build urgent reply
    warning_message = safety_flag.get(
        "warning_message",
        "您的描述可能涉及紧急医疗情况，请立即拨打120或前往最近的医院急诊室。"
    )

    response = URGENT_REPLY_TEMPLATE.format(
        warning_message=warning_message,
        recommendations=recommendations_text,
    )

    logger.info("Urgent reply generated")

    # Update state
    state["response"] = response
    state["safety_flag"] = safety_flag  # Ensure safety flag is preserved
    state["suggested_questions"] = []
    state["next_node"] = "end"

    # Memory persistence is useful for later context, but must never delay an
    # emergency instruction. Import locally to keep this node's dependency
    # surface small and schedule the work without awaiting it.
    from app.agents.health_advisor.nodes.post_process import schedule_urgent_post_process

    state["post_process_scheduled"] = schedule_urgent_post_process(state)

    return state
