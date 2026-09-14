import json

import pytest

from app.evaluation.cases import load_cases
from app.evaluation.failure_feedback import build_regression_dataset, enrich_failure_feedback, write_json
from app.evaluation.health_advisor import (
    DEFAULT_DATASET,
    SUITE_DATASETS,
    evaluate_case,
    run_evaluation,
    run_evaluation_suite,
)


def test_load_default_evaluation_dataset():
    cases = load_cases(DEFAULT_DATASET)

    assert len(cases) >= 5
    assert cases[0].id
    assert cases[0].query
    assert cases[0].expected.intent


@pytest.mark.asyncio
async def test_evaluate_prompt_injection_case():
    case = next(case for case in load_cases(DEFAULT_DATASET) if case.id == "prompt_injection_001")

    result = await evaluate_case(case)

    assert result["predictions"]["prompt_security"]["is_suspicious"] is True
    assert result["metric_scores"]["prompt_injection"] == 1.0


@pytest.mark.asyncio
async def test_default_offline_evaluation_passes():
    report = await run_evaluation(DEFAULT_DATASET, min_score=0.85)

    assert report["summary"]["passed"] is True
    assert report["summary"]["overall_score"] >= 0.85
    assert report["summary"]["case_count"] >= 5
    assert report["llm_usage"]["call_count"] == 0
    assert all("llm_usage" in case for case in report["cases"])
    assert report["failure_feedback"]["summary"]["failed_case_count"] == 0


def test_builtin_evaluation_datasets_load():
    expected_case_counts = {
        "health_advisor": 40,
        "safety": 40,
        "routing": 40,
        "memory": 40,
        "rag": 50,
        "e2e_agent": 30,
    }
    all_case_ids = []
    for dataset in SUITE_DATASETS.values():
        cases = load_cases(dataset)
        assert cases
        assert all(case.id for case in cases)
        assert all(case.query.strip() for case in cases)
        assert all(case.tags for case in cases)
        suite_name = next(name for name, path in SUITE_DATASETS.items() if path == dataset)
        assert len(cases) == expected_case_counts[suite_name]
        all_case_ids.extend(case.id for case in cases)

    assert sum(expected_case_counts.values()) == 240
    assert len(all_case_ids) == 240
    assert len(set(all_case_ids)) == 240


@pytest.mark.asyncio
async def test_memory_suite_evaluates_memory_policy():
    report = await run_evaluation_suite("memory", min_score=0.85)

    assert report["summary"]["passed"] is True
    assert report["summary"]["metrics"]["memory_scope"] == 1.0
    assert report["summary"]["metrics"]["needs_long_term"] == 1.0


@pytest.mark.asyncio
async def test_rag_suite_evaluates_context_hits():
    report = await run_evaluation_suite("rag", min_score=0.85)

    assert report["summary"]["passed"] is True
    assert report["summary"]["metrics"]["rag_doc_hit"] == 1.0
    assert report["summary"]["metrics"]["rag_topic_hit"] == 1.0
    assert report["summary"]["metrics"]["rag_context_terms"] == 1.0


@pytest.mark.asyncio
async def test_live_rag_option_uses_retrieved_documents(monkeypatch):
    case = next(case for case in load_cases(SUITE_DATASETS["rag"]) if case.id == "rag_sleep_guideline")

    async def fake_retrieve_live_rag(query):
        assert query == case.query
        return case.retrieved_docs, {"elapsed_ms": 1.2}

    monkeypatch.setattr(
        "app.evaluation.health_advisor.retrieve_live_rag",
        fake_retrieve_live_rag,
    )

    result = await evaluate_case(case, live_rag=True)

    assert result["metric_scores"]["rag_doc_hit"] == 1.0
    assert result["predictions"]["live_rag"]["elapsed_ms"] == 1.2


@pytest.mark.asyncio
async def test_llm_judge_option_adds_quality_metrics(monkeypatch):
    case = next(case for case in load_cases(DEFAULT_DATASET) if case.id == "sleep_lifestyle_001")

    async def fake_judge_answer(**kwargs):
        assert kwargs["query"] == case.query
        assert kwargs["answer"] == case.reference_response
        return {
            "judge_status": "ok",
            "attempts": 1,
            "answer_relevancy": 0.95,
            "faithfulness": 0.9,
            "safety": 1.0,
            "citation_correctness": 0.85,
            "overall": 0.92,
            "reason": "回答相关且安全",
        }

    monkeypatch.setattr("app.evaluation.health_advisor.judge_answer", fake_judge_answer)

    result = await evaluate_case(case, llm_judge=True, judge_threshold=0.8)

    assert result["metric_scores"]["judge_overall"] == 0.92
    assert all(
        metric["passed"]
        for metric in result["metrics"]
        if metric["name"].startswith("judge_")
    )


@pytest.mark.asyncio
async def test_judge_failure_is_reported_as_evaluation_error(tmp_path, monkeypatch):
    dataset_path = tmp_path / "judge_infrastructure_failure.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "id": "judge_infrastructure_failure_001",
                    "query": "如何保持健康？",
                    "expected": {
                        "intent": "general_health",
                        "urgent": False,
                        "prompt_injection": False,
                        "task_agents": [],
                    },
                    "reference_response": "保持规律作息、均衡饮食和适量活动。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    async def fake_judge_answer(**kwargs):
        return {
            "judge_status": "evaluation_error",
            "attempts": 2,
            "error": {"code": "timeout", "message": "timed out"},
        }

    monkeypatch.setattr("app.evaluation.health_advisor.judge_answer", fake_judge_answer)

    report = await run_evaluation(dataset_path, llm_judge=True, min_score=0.85)

    assert report["summary"]["overall_score"] == 1.0
    assert report["summary"]["product_failed_cases"] == []
    assert report["summary"]["product_passed"] is True
    assert report["summary"]["evaluation_error_cases"] == [
        "judge_infrastructure_failure_001"
    ]
    assert report["summary"]["evaluation_infrastructure_passed"] is False
    assert report["summary"]["passed"] is False
    assert not any(
        metric["name"].startswith("judge_") for metric in report["cases"][0]["metrics"]
    )


@pytest.mark.asyncio
async def test_e2e_agent_option_uses_full_replay_result(monkeypatch):
    case = next(
        case
        for case in load_cases(SUITE_DATASETS["e2e_agent"])
        if case.id == "e2e_nutrition_meal_analysis"
    )

    async def fake_replay(case_arg):
        assert case_arg.id == case.id
        return {
            "elapsed_ms": 1000,
            "status": "ok",
            "response": "这顿饮食整体偏油偏甜，建议减少炸鸡和奶茶，增加蔬菜和优质蛋白。",
            "intent": "nutrition",
            "safety_flag": {"is_urgent": False},
            "prompt_security": {"is_suspicious": False, "risk_level": "low", "categories": []},
            "memory_policy": {
                "scope": "rag_only",
                "needs_short_term": False,
                "needs_long_term": False,
                "needs_rag": True,
            },
            "retrieved_docs": [],
            "task_agents": ["nutrition"],
            "sub_tasks": [],
            "orchestration_status": "success",
            "completed_agents": ["nutrition"],
            "agent_trace": {"completed": ["nutrition"]},
            "citations": [],
        }

    monkeypatch.setattr(
        "app.evaluation.health_advisor.run_health_advisor_replay",
        fake_replay,
    )

    result = await evaluate_case(case, e2e_agent=True)

    assert result["answer"].startswith("这顿饮食")
    assert result["metric_scores"]["completed_agents"] == 1.0
    assert result["metric_scores"]["orchestration_status"] == 1.0
    assert result["metric_scores"]["latency"] == 1.0


@pytest.mark.asyncio
async def test_all_evaluation_suites_pass():
    report = await run_evaluation_suite("all", min_score=0.85)

    assert report["summary"]["passed"] is True
    assert set(report["reports"]) == set(SUITE_DATASETS)
    assert "llm_usage" in report["summary"]
    assert report["failure_feedback"]["summary"]["failed_case_count"] == 0


@pytest.mark.asyncio
async def test_failure_feedback_and_regression_dataset_export(tmp_path):
    dataset_path = tmp_path / "failing_cases.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "id": "intent_failure_001",
                    "query": "我早餐吃了炸鸡和奶茶，怎么调整饮食？",
                    "tags": ["nutrition"],
                    "expected": {
                        "intent": "exercise",
                        "urgent": False,
                        "prompt_injection": False,
                        "task_agents": ["exercise"],
                    },
                    "reference_response": "建议减少油炸食物和含糖饮料，增加蔬菜和优质蛋白。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = await run_evaluation(dataset_path, min_score=0.85)
    feedback = report["failure_feedback"]

    assert report["summary"]["passed"] is False
    assert feedback["summary"]["failed_case_count"] == 1
    assert feedback["items"][0]["failure_type"] == "intent_routing"
    assert feedback["items"][0]["regression_candidate"] is True

    regression_cases = build_regression_dataset(report, feedback)
    assert regression_cases[0]["id"] == "intent_failure_001"
    assert "failure_feedback" in regression_cases[0]["tags"]
    assert regression_cases[0]["feedback"]["failed_metrics"]

    output_path = tmp_path / "regression_failed_cases.json"
    write_json(regression_cases, output_path)
    loaded_cases = load_cases(output_path)
    assert loaded_cases[0].id == "intent_failure_001"


@pytest.mark.asyncio
async def test_llm_failure_analysis_enriches_failed_cases(tmp_path, monkeypatch):
    dataset_path = tmp_path / "failing_cases.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "id": "rag_failure_001",
                    "query": "成年人每周需要多大的身体活动量？",
                    "tags": ["rag", "exercise"],
                    "expected": {
                        "intent": "exercise",
                        "urgent": False,
                        "prompt_injection": False,
                        "task_agents": ["exercise"],
                        "rag_doc_ids": ["missing_doc"],
                    },
                    "reference_response": "成年人每周建议保持中等强度身体活动。",
                    "retrieved_docs": [
                        {
                            "id": "other_doc",
                            "title": "其他指南",
                            "content": "保持规律运动有益健康。",
                            "metadata": {"topic": "exercise"},
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    async def fake_json_chat(system_prompt, user_message, *, stage=""):
        assert stage == "evaluation.failure_analysis"
        assert "rag_failure_001" in user_message
        return {
            "root_cause": "预期文档未被召回，可能是知识库入库或 doc_id 配置不一致。",
            "evidence": "失败指标包含 rag_doc_hit，expected 中存在 missing_doc。",
            "fix_priority": "P2",
            "recommended_fix": "检查测试集期望文档和 ES 知识库入库结果。",
            "should_update_dataset": False,
            "dataset_update_reason": "",
            "knowledge_gap": True,
            "prompt_or_code_area": "rag",
            "confidence": 0.86,
        }

    monkeypatch.setattr(
        "app.evaluation.failure_feedback.deepseek_client.json_chat",
        fake_json_chat,
    )

    report = await run_evaluation(
        dataset_path,
        min_score=0.85,
        llm_failure_analysis=True,
        failure_analysis_limit=1,
    )
    item = report["failure_feedback"]["items"][0]

    assert item["llm_analysis"]["prompt_or_code_area"] == "rag"
    assert item["llm_analysis"]["knowledge_gap"] is True
    assert item["llm_analysis"]["confidence"] == 0.86
    assert report["failure_feedback"]["summary"]["llm_analysis"]["analyzed_count"] == 1

    regression_cases = build_regression_dataset(report, report["failure_feedback"])
    assert regression_cases[0]["feedback"]["llm_analysis"]["prompt_or_code_area"] == "rag"

    enriched = await enrich_failure_feedback(report["failure_feedback"], max_cases=0)
    assert enriched["summary"]["llm_analysis"]["skipped_count"] == 1
