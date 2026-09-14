import asyncio

import pytest

from app.evaluation.llm_judge import JUDGE_METRIC_KEYS, judge_answer, judge_metrics


VALID_JUDGE_RESULT = {
    "answer_relevancy": 0.95,
    "faithfulness": 0.9,
    "safety": 1.0,
    "citation_correctness": 0.85,
    "overall": 0.92,
    "reason": "回答相关且安全",
}


async def _run_judge() -> dict:
    return await judge_answer(
        query="成年人睡眠多久合适？",
        answer="一般建议保持稳定且充足的睡眠。",
        reference_response="成年人通常需要比较稳定的睡眠。",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("effects", "expected_error_code"),
    [
        ([{"raw_response": ""}, {"raw_response": ""}], "empty_response"),
        (
            [{"raw_response": "not-json"}, {"raw_response": "still-not-json"}],
            "invalid_json",
        ),
        (
            [
                {key: value for key, value in VALID_JUDGE_RESULT.items() if key != "overall"},
                {key: value for key, value in VALID_JUDGE_RESULT.items() if key != "overall"},
            ],
            "missing_fields",
        ),
        (
            [
                {**VALID_JUDGE_RESULT, "safety": 1.2},
                {**VALID_JUDGE_RESULT, "safety": 1.2},
            ],
            "score_out_of_range",
        ),
        ([asyncio.TimeoutError(), asyncio.TimeoutError()], "timeout"),
    ],
    ids=["empty", "invalid-json", "missing-field", "out-of-range", "timeout"],
)
async def test_judge_failure_retries_once_then_reports_evaluation_error(
    monkeypatch,
    effects,
    expected_error_code,
):
    calls = 0

    async def fake_json_chat(*args, **kwargs):
        nonlocal calls
        effect = effects[calls]
        calls += 1
        if isinstance(effect, BaseException):
            raise effect
        return effect

    monkeypatch.setattr(
        "app.evaluation.llm_judge.deepseek_client.json_chat",
        fake_json_chat,
    )

    result = await _run_judge()

    assert calls == 2
    assert result["judge_status"] == "evaluation_error"
    assert result["attempts"] == 2
    assert result["error"]["code"] == expected_error_code
    assert all(key not in result for key in JUDGE_METRIC_KEYS)


@pytest.mark.asyncio
async def test_judge_failure_can_recover_on_the_single_retry(monkeypatch):
    effects = [{"raw_response": ""}, VALID_JUDGE_RESULT]
    calls = 0

    async def fake_json_chat(*args, **kwargs):
        nonlocal calls
        effect = effects[calls]
        calls += 1
        return effect

    monkeypatch.setattr(
        "app.evaluation.llm_judge.deepseek_client.json_chat",
        fake_json_chat,
    )

    result = await _run_judge()

    assert calls == 2
    assert result["judge_status"] == "ok"
    assert result["attempts"] == 2
    assert {key: result[key] for key in JUDGE_METRIC_KEYS} == {
        key: VALID_JUDGE_RESULT[key] for key in JUDGE_METRIC_KEYS
    }


def test_evaluation_error_does_not_create_product_score_metrics():
    result = {
        "judge_status": "evaluation_error",
        "attempts": 2,
        "error": {"code": "timeout", "message": "timed out"},
    }

    assert judge_metrics(result) == []
