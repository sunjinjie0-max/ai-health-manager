"""Guarded extraction pipeline for structured user-profile updates."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import settings
from app.llm.deepseek import deepseek_client

logger = logging.getLogger(__name__)


ProfileSection = Literal[
    "basic_info",
    "health_status",
    "lifestyle",
    "health_goals",
    "diet_preferences",
]

ALLOWED_PROFILE_FIELDS: dict[str, set[str]] = {
    "basic_info": {"age", "gender", "height_cm", "weight_kg"},
    "health_status": {
        "allergies",
        "conditions",
        "chronic_diseases",
        "medications",
        "pregnancy_status",
        "exercise_restrictions",
    },
    "lifestyle": {
        "sleep_pattern",
        "exercise_frequency",
        "exercise_types",
        "smoking",
        "alcohol",
    },
    "health_goals": {"items"},
    "diet_preferences": {"avoid", "likes", "restrictions", "meal_pattern"},
}

HIGH_RISK_FIELDS = {
    ("health_status", "allergies"),
    ("health_status", "conditions"),
    ("health_status", "chronic_diseases"),
    ("health_status", "medications"),
    ("health_status", "pregnancy_status"),
    ("health_status", "exercise_restrictions"),
}

CONDITION_WORDS = ("高血压", "糖尿病", "高血脂", "脂肪肝", "痛风", "哮喘", "冠心病", "胃病")
GOAL_WORDS = ("减脂", "减肥", "增肌", "控糖", "降压", "改善睡眠", "提高体能", "增强体质")
IMPLICIT_PROFILE_CUES = ("通常", "一般", "经常", "习惯", "总是", "一忙", "不太", "比较")
CONFIRMATION_WORDS = {"确认", "确认记录", "是的", "对", "没错", "可以记录", "记录吧", "同意记录"}
REJECTION_WORDS = {"不是", "不对", "不要记录", "别记录", "取消", "不同意", "否认"}


class ProfileCandidate(BaseModel):
    """One auditable candidate emitted by a rule or the LLM."""

    section: ProfileSection
    field: str = Field(min_length=1, max_length=64)
    value: Any
    source: Literal["rule", "llm"] = "llm"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1, max_length=300)
    requires_confirmation: bool = False

    @field_validator("field")
    @classmethod
    def field_must_be_allowed(cls, value: str, info):
        section = info.data.get("section")
        if section and value not in ALLOWED_PROFILE_FIELDS.get(str(section), set()):
            raise ValueError(f"unsupported profile field: {section}.{value}")
        return value


class ProfileExtractionOutcome(BaseModel):
    """Validated output of the hybrid extraction pipeline."""

    accepted_updates: dict[str, Any] = Field(default_factory=dict)
    pending_confirmations: list[ProfileCandidate] = Field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)


def extract_rule_profile_candidates(user_message: str) -> list[ProfileCandidate]:
    """Extract deterministic profile candidates from explicit user statements."""
    message = _normalize_text(user_message)
    if not message:
        return []

    candidates: list[ProfileCandidate] = []

    def add(section: ProfileSection, field: str, value: Any, evidence: str, confidence: float = 0.95) -> None:
        candidates.append(
            ProfileCandidate(
                section=section,
                field=field,
                value=value,
                source="rule",
                confidence=confidence,
                evidence=evidence,
                requires_confirmation=(section, field) in HIGH_RISK_FIELDS,
            )
        )

    age_match = re.search(r"(\d{1,3})\s*岁", message)
    if age_match:
        age = int(age_match.group(1))
        if 0 < age <= 120:
            add("basic_info", "age", age, age_match.group(0), 0.99)

    height_match = re.search(r"(?:身高)?\s*(\d{2,3}(?:\.\d+)?)\s*(?:厘米|cm|CM)", message)
    if height_match:
        height = float(height_match.group(1))
        if 50 <= height <= 250:
            add("basic_info", "height_cm", height, height_match.group(0), 0.98)

    weight_match = re.search(r"(?:体重)?\s*(\d{1,3}(?:\.\d+)?)\s*(?:公斤|千克|kg|KG)", message)
    if weight_match:
        weight = float(weight_match.group(1))
        if 2 <= weight <= 400:
            add("basic_info", "weight_kg", weight, weight_match.group(0), 0.98)

    if any(keyword in message for keyword in ("我是男", "男性", "男生")):
        add("basic_info", "gender", "male", "男性", 0.98)
    elif any(keyword in message for keyword in ("我是女", "女性", "女生")):
        add("basic_info", "gender", "female", "女性", 0.98)

    allergy_pattern = r"(?:我)?(?:对|吃)?([\u4e00-\u9fa5A-Za-z0-9]{1,12})过敏"
    for match in re.finditer(allergy_pattern, message):
        if _is_negated(message, match.start()):
            continue
        allergen = match.group(1)
        if allergen not in {"我", "自己", "有点", "严重"}:
            add("health_status", "allergies", allergen, match.group(0), 0.97)

    for condition in CONDITION_WORDS:
        condition_match = re.search(rf"我(?:有|得了|患有|被诊断为){re.escape(condition)}", message)
        if condition_match and not _is_negated(message, condition_match.start()):
            add("health_status", "conditions", condition, condition_match.group(0), 0.97)

    goals = [goal for goal in GOAL_WORDS if goal in message and "我" in message]
    for goal in goals:
        add("health_goals", "items", goal, goal, 0.9)

    for match in re.finditer(r"(?:不吃|忌口|避免吃)([\u4e00-\u9fa5A-Za-z0-9]{1,12})", message):
        add("diet_preferences", "avoid", match.group(1), match.group(0), 0.92)

    for match in re.finditer(r"(?:喜欢吃|爱吃)([\u4e00-\u9fa5A-Za-z0-9]{1,12})", message):
        add("diet_preferences", "likes", match.group(1), match.group(0), 0.9)

    exercise_frequency = re.search(r"每周(?:大概|大约|通常|一般)?(\d+)次(?:运动|锻炼|跑步|健身)", message)
    if exercise_frequency:
        add(
            "lifestyle",
            "exercise_frequency",
            f"每周{exercise_frequency.group(1)}次",
            exercise_frequency.group(0),
            0.94,
        )

    sleep_pattern = re.search(r"(?:我)?(?:一般|通常|平时)?(?:在)?(\d{1,2})点(?:半)?睡", message)
    if sleep_pattern:
        add("lifestyle", "sleep_pattern", f"{sleep_pattern.group(1)}点睡", sleep_pattern.group(0), 0.92)

    return _dedupe_candidates(candidates)


async def extract_profile_updates(user_message: str) -> ProfileExtractionOutcome:
    """Run rule extraction, optional LLM supplementation, and guarded validation."""
    message = _normalize_text(user_message)
    rule_candidates = extract_rule_profile_candidates(message)
    llm_candidates: list[ProfileCandidate] = []
    rejected: list[dict[str, Any]] = []

    if _should_call_profile_llm(message, rule_candidates):
        llm_candidates, rejected = await _extract_llm_profile_candidates(message, rule_candidates)

    merged = _dedupe_candidates([*rule_candidates, *llm_candidates])
    if settings.profile_high_risk_confirmation:
        accepted = [candidate for candidate in merged if not candidate.requires_confirmation]
        pending = [candidate for candidate in merged if candidate.requires_confirmation]
    else:
        accepted = merged
        pending = []

    return ProfileExtractionOutcome(
        accepted_updates=candidates_to_profile_updates(accepted),
        pending_confirmations=pending,
        rejected_candidates=rejected,
        trace={
            "rule_candidates": len(rule_candidates),
            "llm_candidates": len(llm_candidates),
            "accepted_candidates": len(accepted),
            "pending_confirmations": len(pending),
            "rejected_candidates": len(rejected),
        },
    )


def candidates_to_profile_updates(
    candidates: list[ProfileCandidate] | list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert validated candidates into the nested UserProfile update shape."""
    updates: dict[str, Any] = {}
    for raw_candidate in candidates:
        candidate = (
            raw_candidate
            if isinstance(raw_candidate, ProfileCandidate)
            else ProfileCandidate.model_validate(raw_candidate)
        )
        if candidate.section == "health_goals":
            goals = updates.setdefault("health_goals", [])
            values = candidate.value if isinstance(candidate.value, list) else [candidate.value]
            for value in values:
                if value not in goals:
                    goals.append(value)
            continue

        section = updates.setdefault(candidate.section, {})
        if _is_list_field(candidate.section, candidate.field):
            values = candidate.value if isinstance(candidate.value, list) else [candidate.value]
            existing = section.setdefault(candidate.field, [])
            for value in values:
                if value not in existing:
                    existing.append(value)
        else:
            section[candidate.field] = candidate.value
    return updates


def merge_profile_updates(*updates: dict[str, Any]) -> dict[str, Any]:
    """Merge update payloads without mutating their inputs."""
    candidates: list[ProfileCandidate] = []
    for payload in updates:
        for section, fields in (payload or {}).items():
            if section == "health_goals":
                for value in fields if isinstance(fields, list) else [fields]:
                    candidates.append(
                        ProfileCandidate(
                            section="health_goals",
                            field="items",
                            value=value,
                            source="rule",
                            confidence=1.0,
                            evidence="confirmed",
                        )
                    )
                continue
            if not isinstance(fields, dict):
                continue
            for field, value in fields.items():
                if field not in ALLOWED_PROFILE_FIELDS.get(section, set()):
                    continue
                candidates.append(
                    ProfileCandidate(
                        section=section,
                        field=field,
                        value=value,
                        source="rule",
                        confidence=1.0,
                        evidence="confirmed",
                    )
                )
    return candidates_to_profile_updates(candidates)


def resolve_confirmation_intent(user_message: str) -> Literal["confirm", "reject"] | None:
    normalized = _normalize_text(user_message).strip("。！？!?，, ")
    if normalized in CONFIRMATION_WORDS:
        return "confirm"
    if normalized in REJECTION_WORDS:
        return "reject"
    return None


def format_confirmation_prompt(candidates: list[ProfileCandidate] | list[dict[str, Any]]) -> str:
    labels = {
        "allergies": "过敏信息",
        "conditions": "疾病史",
        "chronic_diseases": "慢性病史",
        "medications": "用药信息",
        "pregnancy_status": "妊娠状态",
        "exercise_restrictions": "运动禁忌",
    }
    items: list[str] = []
    for raw_candidate in candidates:
        candidate = raw_candidate if isinstance(raw_candidate, ProfileCandidate) else ProfileCandidate.model_validate(raw_candidate)
        value = candidate.value
        if isinstance(value, list):
            value = "、".join(str(item) for item in value)
        items.append(f"{labels.get(candidate.field, candidate.field)}：{value}")
    unique_items = list(dict.fromkeys(items))
    return "；".join(unique_items)


async def _extract_llm_profile_candidates(
    user_message: str,
    rule_candidates: list[ProfileCandidate],
) -> tuple[list[ProfileCandidate], list[dict[str, Any]]]:
    rule_summary = [
        {"section": item.section, "field": item.field, "value": item.value}
        for item in rule_candidates
    ]
    prompt = f"""
请从用户原话中补充抽取规则未覆盖的结构化健康画像候选。

用户原话：
{user_message}

规则已抽取：
{rule_summary}

只允许以下字段：
- basic_info: age, gender, height_cm, weight_kg
- health_status: allergies, conditions, chronic_diseases, medications, pregnancy_status, exercise_restrictions
- lifestyle: sleep_pattern, exercise_frequency, exercise_types, smoking, alcohol
- health_goals: items
- diet_preferences: avoid, likes, restrictions, meal_pattern

要求：
1. 只抽取用户明确陈述的事实，不做诊断或因果推断
2. evidence必须逐字来自用户原话
3. 不抽取“今天、这周、最近一次”等一次性状态
4. 每个候选返回0到1的confidence
5. 返回严格JSON：
{{
  "candidates": [
    {{
      "section": "lifestyle",
      "field": "exercise_frequency",
      "value": "每周3次",
      "confidence": 0.88,
      "evidence": "我一般每周跑三次"
    }}
  ]
}}
没有候选时返回 {{"candidates": []}}。
""".strip()

    try:
        result = await deepseek_client.json_chat(
            system_prompt=(
                "你是健康画像候选抽取器。你只能抽取用户明确表达且有原文证据的事实，"
                "不能推断疾病，不能直接写数据库。"
            ),
            user_message=prompt,
            stage="memory.profile_extraction",
        )
    except Exception:
        logger.exception("[profile_extraction] LLM supplement failed")
        return [], [{"reason": "llm_call_failed"}]

    raw_candidates = result.get("candidates") if isinstance(result, dict) else None
    if not isinstance(raw_candidates, list):
        return [], [{"reason": "invalid_llm_payload"}]

    accepted: list[ProfileCandidate] = []
    rejected: list[dict[str, Any]] = []
    for raw in raw_candidates:
        try:
            item = dict(raw)
            item["source"] = "llm"
            section = str(item.get("section") or "")
            field = str(item.get("field") or "")
            item["requires_confirmation"] = (section, field) in HIGH_RISK_FIELDS
            candidate = ProfileCandidate.model_validate(item)
        except (TypeError, ValueError, ValidationError) as exc:
            rejected.append({"candidate": raw, "reason": f"schema_validation: {exc}"})
            continue

        reason = _validate_llm_candidate(candidate, user_message)
        if reason:
            rejected.append({"candidate": raw, "reason": reason})
            continue
        accepted.append(candidate)
    return accepted, rejected


def _validate_llm_candidate(candidate: ProfileCandidate, user_message: str) -> str | None:
    if candidate.confidence < settings.profile_llm_min_confidence:
        return "confidence_below_threshold"
    if candidate.evidence not in user_message:
        return "evidence_not_found_in_source"
    if any(marker in candidate.evidence for marker in ("今天", "这周", "本周", "最近一次", "暂时")):
        return "transient_state"

    values = candidate.value if isinstance(candidate.value, list) else [candidate.value]
    if candidate.section == "health_status":
        if _is_negated(candidate.evidence, 0):
            return "negated_high_risk_fact"
        for value in values:
            if isinstance(value, str) and value not in candidate.evidence:
                return "high_risk_value_not_explicit_in_evidence"

    if candidate.section == "basic_info" and candidate.field == "age":
        try:
            if not 0 < int(candidate.value) <= 120:
                return "age_out_of_range"
        except (TypeError, ValueError):
            return "invalid_age"
    if candidate.section == "basic_info" and candidate.field == "height_cm":
        try:
            if not 50 <= float(candidate.value) <= 250:
                return "height_out_of_range"
        except (TypeError, ValueError):
            return "invalid_height"
    if candidate.section == "basic_info" and candidate.field == "weight_kg":
        try:
            if not 2 <= float(candidate.value) <= 400:
                return "weight_out_of_range"
        except (TypeError, ValueError):
            return "invalid_weight"
    return None


def _should_call_profile_llm(message: str, rule_candidates: list[ProfileCandidate]) -> bool:
    if not settings.profile_use_llm_supplement or not settings.deepseek_api_key:
        return False
    if len(message) < 10 or "我" not in message:
        return False
    return (
        not rule_candidates
        or (
            len(rule_candidates) <= 1
            and (
                len(message) >= 24
                or any(cue in message for cue in IMPLICIT_PROFILE_CUES)
            )
        )
    )


def _dedupe_candidates(candidates: list[ProfileCandidate]) -> list[ProfileCandidate]:
    deduped: dict[str, ProfileCandidate] = {}
    for candidate in candidates:
        key = f"{candidate.section}::{candidate.field}::{candidate.value}"
        previous = deduped.get(key)
        if previous is None or candidate.confidence > previous.confidence:
            deduped[key] = candidate
    return list(deduped.values())


def _is_list_field(section: str, field: str) -> bool:
    return (section, field) in {
        ("health_status", "allergies"),
        ("health_status", "conditions"),
        ("health_status", "chronic_diseases"),
        ("health_status", "medications"),
        ("health_status", "exercise_restrictions"),
        ("lifestyle", "exercise_types"),
        ("diet_preferences", "avoid"),
        ("diet_preferences", "likes"),
        ("diet_preferences", "restrictions"),
    }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_negated(text: str, start: int) -> bool:
    prefix = str(text or "")[max(0, start - 6):start]
    local = str(text or "")[start:start + 8]
    return any(marker in f"{prefix}{local}" for marker in ("没有", "并非", "不是", "否认", "不再", "不过敏"))
