"""Safety check node for Health Advisor Agent."""

import logging

from app.agents.health_advisor.prompts import SAFETY_CHECK_PROMPT
from app.agents.health_advisor.state import HealthAdvisorState
from app.config import settings
from app.core.prompt_security import assess_prompt_injection
from app.llm.deepseek import deepseek_client, mark_llm_degraded

logger = logging.getLogger(__name__)


# Urgent keywords that trigger immediate escalation
URGENT_KEYWORDS = [
    "胸痛", "胸口痛", "心脏痛",
    "呼吸困难", "呼吸急促", "喘不过气",
    "昏迷", "晕倒", "意识丧失",
    "大出血", "流血不止",
    "严重过敏", "呼吸困难",
    "中风", "面瘫", "肢体无力",
    "自杀", "想死", "不想活",
    "120", "急救", "急诊",
]

CLAUSE_BOUNDARIES = ("。", "！", "!", "？", "?", "；", ";", "，", ",", "但是", "但")
NEGATION_CUES = (
    "没有明显",
    "没有",
    "没出现",
    "未出现",
    "未见明显",
    "未见",
    "未发现",
    "并无",
    "否认存在",
    "否认有",
    "否认",
    "不存在",
    "不伴有",
    "不伴",
    "不再",
    "无明显",
    "无",
)
NEGATION_REVERSAL_CUES = (
    "不是没有",
    "不是无",
    "并非没有",
    "并非无",
    "不能说没有",
    "没有否认",
    "未否认",
    "不能排除",
    "不排除",
)
HISTORICAL_CUES = ("以前", "曾经", "既往", "去年", "前年", "小时候", "过去", "有过")
RESOLVED_CUES = ("已经好了", "已好转", "已缓解", "已消失", "现在没有")
HYPOTHETICAL_CUES = ("如果", "假如", "假设", "若出现", "万一", "什么情况下", "如何判断")
CURRENT_CUES = ("现在", "目前", "此刻", "正在", "突然", "刚刚", "刚才")


def _clause_prefix(message: str, keyword_start: int, max_chars: int = 20) -> str:
    start = 0
    for boundary in CLAUSE_BOUNDARIES:
        position = message.rfind(boundary, 0, keyword_start)
        if position >= 0:
            start = max(start, position + len(boundary))
    return message[start:keyword_start][-max_chars:].strip()


def _clause_suffix(message: str, keyword_end: int, max_chars: int = 16) -> str:
    end = len(message)
    for boundary in CLAUSE_BOUNDARIES:
        position = message.find(boundary, keyword_end)
        if position >= 0:
            end = min(end, position)
    return message[keyword_end:end][:max_chars].strip()


def _describes_current_symptom(message: str, keyword_start: int, keyword_end: int) -> bool:
    prefix = _clause_prefix(message, keyword_start)
    suffix = _clause_suffix(message, keyword_end)

    if any(cue in prefix for cue in NEGATION_REVERSAL_CUES):
        return True
    if any(prefix.endswith(cue) for cue in NEGATION_CUES):
        return False

    has_current_cue = any(cue in prefix for cue in CURRENT_CUES)
    if not has_current_cue and any(cue in prefix for cue in HYPOTHETICAL_CUES):
        return False
    if not has_current_cue and any(cue in prefix for cue in HISTORICAL_CUES):
        return False
    if suffix.startswith("史") or any(cue in suffix for cue in RESOLVED_CUES):
        return False
    return True


def _check_urgent_keywords(message: str) -> tuple[bool, str]:
    """Check if message contains urgent keywords.

    Returns:
        (is_urgent, reason)
    """
    message_lower = message.lower()
    for keyword in URGENT_KEYWORDS:
        search_start = 0
        while True:
            keyword_start = message_lower.find(keyword, search_start)
            if keyword_start < 0:
                break
            keyword_end = keyword_start + len(keyword)
            if _describes_current_symptom(message_lower, keyword_start, keyword_end):
                return True, f"检测到当前紧急症状: {keyword}"
            search_start = keyword_end
    return False, ""


async def check_safety(state: HealthAdvisorState) -> HealthAdvisorState:
    """Check user message for safety concerns.

    Performs two-level safety check:
    1. Keyword-based detection for urgent symptoms
    2. LLM-based analysis for nuanced safety concerns

    Args:
        state: Current state with user message

    Returns:
        Updated state with safety assessment
    """
    user_message = state.get("user_message", "")

    logger.info(f"Checking safety for message: {user_message[:100]}...")

    prompt_security = assess_prompt_injection(user_message)
    state["prompt_security"] = prompt_security.model_dump()
    if prompt_security.is_suspicious:
        logger.warning(
            "Prompt injection suspected categories=%s risk=%s",
            prompt_security.categories,
            prompt_security.risk_level,
        )
        state.setdefault("agent_warnings", []).append(prompt_security.warning)

    # Level 1: Keyword check
    is_urgent_keyword, keyword_reason = _check_urgent_keywords(user_message)

    if is_urgent_keyword:
        logger.warning(f"Urgent keyword detected: {keyword_reason}")
        state["safety_flag"] = {
            "is_urgent": True,
            "risk_level": "high",
            "warning_message": "您的描述可能涉及紧急医疗情况，请立即拨打120或前往最近的医院急诊室。不要等待在线回复。",
            "recommendations": ["立即拨打120", "前往最近的医院急诊室", "不要延误"],
            "reason": keyword_reason,
        }
        state["next_node"] = "urgent_reply"
        return state

    # Level 2: LLM-based safety check (for non-obvious cases)
    try:
        prompt = SAFETY_CHECK_PROMPT + user_message

        result = await deepseek_client.json_chat(
            system_prompt="你是一个专门分析健康咨询安全性的AI助手。",
            user_message=prompt,
            deadline_monotonic=state.get("deadline_monotonic"),
            timeout_seconds=settings.safety_llm_timeout_seconds,
        )

        is_urgent = result.get("is_urgent", False)
        risk_level = result.get("risk_level", "low")

        if is_urgent and risk_level in ["high", "medium"]:
            logger.warning(f"LLM detected urgent safety concern: {result}")
            state["safety_flag"] = {
                "is_urgent": True,
                "risk_level": risk_level,
                "warning_message": result.get("warning_message", "您的描述可能涉及紧急医疗情况，请立即拨打120或前往最近的医院急诊室。"),
                "recommendations": result.get("recommendations", ["立即拨打120", "前往医院急诊"]),
                "reason": "LLM safety check detected urgent concern",
            }
            state["next_node"] = "urgent_reply"
        else:
            state["safety_flag"] = {
                "is_urgent": False,
                "risk_level": "low",
                "warning_message": None,
                "recommendations": [],
            }
            state["next_node"] = "classify_intent"

    except Exception as e:
        logger.error(f"Safety check failed: {e}")
        mark_llm_degraded(state, stage="health_advisor.check_safety", error=e)
        # Fail safe - assume not urgent
        state["safety_flag"] = {
            "is_urgent": False,
            "risk_level": "low",
            "warning_message": None,
            "recommendations": [],
        }
        state["next_node"] = "classify_intent"

    return state
