"""Tests for Elasticsearch-backed long-term memory."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.memory.long_term import LongTermMemory


def test_extract_memories_from_user_message():
    manager = LongTermMemory()

    docs = manager.extract_memories(
        user_id="user-1",
        session_id="session-1",
        user_message="我习惯周末运动，而且对花生过敏，最近在减脂。",
    )

    contents = {doc["content"] for doc in docs}
    assert "用户习惯周末运动。" in contents
    assert "用户对花生过敏。" not in contents
    assert "用户当前健康目标包含减脂。" not in contents


def test_extract_memories_supports_specific_weekday():
    manager = LongTermMemory()

    docs = manager.extract_memories(
        user_id="user-1",
        session_id="session-1",
        user_message="我习惯在周六进行锻炼和运动，经常跑步。",
    )

    assert any(doc["content"] == "用户习惯周六运动。" for doc in docs)


def test_extract_memories_supports_exercise_activity_type():
    manager = LongTermMemory()

    docs = manager.extract_memories(
        user_id="user-1",
        session_id="session-1",
        user_message="我一般进行的锻炼运动的项目类型是跑步。",
    )

    assert any(doc["content"] == "用户常进行的运动项目是跑步。" for doc in docs)


def test_extract_memories_supports_diet_sleep_and_lifestyle_domains():
    manager = LongTermMemory()

    docs = manager.extract_memories(
        user_id="user-1",
        session_id="session-1",
        user_message="我喜欢吃燕麦，平时不吃香菜，经常不吃早餐，一般12点睡，而且工作日没时间运动。",
    )

    contents = {doc["content"] for doc in docs}
    assert "用户偏好燕麦。" in contents
    assert "用户饮食上不吃香菜。" in contents
    assert "用户的饮食模式表现为经常不吃早餐。" in contents
    assert "用户一般12点睡。" in contents
    assert "用户的生活方式约束包括工作日可用于运动的时间较少。" in contents


@pytest.mark.asyncio
async def test_search_relevant_messages_prefers_es_semantic_memory(monkeypatch):
    monkeypatch.setattr(settings, "elasticsearch_url", "http://memory-es:9200")
    manager = LongTermMemory()

    async def fake_search_memories(user_id: str, query: str, *, limit: int | None = None):
        assert user_id == "user-1"
        assert "运动" in query
        return [{"role": "memory", "content": "用户习惯周末运动。"}]

    async def fail_fallback(*args, **kwargs):
        raise AssertionError("should not fall back when ES returns semantic memories")

    monkeypatch.setattr(manager, "search_memories", fake_search_memories)
    monkeypatch.setattr(manager, "_fallback_keyword_search", fail_fallback)

    result = await manager.search_relevant_messages(
        db=MagicMock(),
        user_id="user-1",
        query="我平时一般什么时候运动？",
        limit=4,
    )

    assert result == [{"role": "memory", "content": "用户习惯周末运动。"}]


@pytest.mark.asyncio
async def test_store_user_message_memories_indexes_extracted_docs(monkeypatch):
    monkeypatch.setattr(settings, "elasticsearch_url", "http://memory-es:9200")
    manager = LongTermMemory()
    captured_docs = []

    async def fake_add_memory_documents(memory_docs):
        captured_docs.extend(memory_docs)
        return [doc["id"] for doc in memory_docs]

    monkeypatch.setattr(manager, "add_memory_documents", fake_add_memory_documents)

    stored_ids = await manager.store_user_message_memories(
        user_id="user-1",
        session_id="session-1",
        user_message="我平时习惯晚上跑步。",
    )

    assert stored_ids
    assert any(doc["content"] == "用户习惯晚上运动。" for doc in captured_docs)


def test_denoise_memories_removes_duplicate_noise():
    manager = LongTermMemory()
    memories = [
        {
            "id": "1",
            "content": "用户习惯周六运动。",
            "score": 0.02,
            "metadata": {"memory_type": "habit", "topic": "exercise", "salience": 0.88},
        },
        {
            "id": "2",
            "content": "用户习惯周六运动。",
            "score": 0.01,
            "metadata": {"memory_type": "habit", "topic": "exercise", "salience": 0.5},
        },
        {
            "id": "3",
            "content": "用户偏好苹果。",
            "score": 0.03,
            "metadata": {"memory_type": "preference", "topic": "nutrition", "salience": 0.7},
        },
    ]

    result = manager._denoise_memories(memories, limit=5)

    assert len(result) == 2
    assert sum(1 for item in result if item["content"] == "用户习惯周六运动。") == 1


@pytest.mark.asyncio
async def test_vector_memory_search_skips_dimension_mismatch():
    manager = LongTermMemory()
    manager._client = AsyncMock()
    manager._client.search.side_effect = RuntimeError(
        "failed to create query: the query vector has a different dimension [1024] than the index vectors [768]"
    )

    results = await manager._vector_search_memories("user-1", [0.1] * 1024, 5)

    assert results == []


def test_should_call_llm_supplement_for_complex_multi_domain_message(monkeypatch):
    monkeypatch.setattr(settings, "memory_use_llm_supplement", True)
    manager = LongTermMemory()

    should_call = manager._should_call_llm_supplement(
        "我工作日基本没空运动，最近晚上喝牛奶容易肚子不舒服。",
        existing_docs=[{"slot": "lifestyle_constraint", "value": "工作日可用于运动的时间较少"}],
    )

    assert should_call is True


@pytest.mark.asyncio
async def test_store_user_message_memories_merges_llm_supplement(monkeypatch):
    monkeypatch.setattr(settings, "elasticsearch_url", "http://memory-es:9200")
    monkeypatch.setattr(settings, "memory_use_llm_supplement", True)
    manager = LongTermMemory()
    captured_docs = []

    monkeypatch.setattr(
        "app.memory.long_term.deepseek_client.json_chat",
        AsyncMock(
            return_value={
                "memories": [
                    {
                        "domain": "nutrition",
                        "topic": "intolerance",
                        "memory_type": "constraint",
                        "slot": "diet_constraint",
                        "value": "乳糖不耐受",
                        "content": "用户可能存在乳糖不耐受。",
                        "confidence": 0.84,
                        "salience": 0.86,
                        "evidence": "晚上喝牛奶容易肚子不舒服",
                        "tags": ["nutrition", "constraint", "乳糖不耐受"],
                    }
                ]
            }
        ),
    )

    async def fake_add_memory_documents(memory_docs):
        captured_docs.extend(memory_docs)
        return [doc["id"] for doc in memory_docs]

    monkeypatch.setattr(manager, "add_memory_documents", fake_add_memory_documents)

    stored_ids = await manager.store_user_message_memories(
        user_id="user-1",
        session_id="session-1",
        user_message="我工作日基本没空运动，最近晚上喝牛奶容易肚子不舒服。",
    )

    assert stored_ids
    assert any(doc["slot"] == "diet_constraint" and doc["value"] == "乳糖不耐受" for doc in captured_docs)
