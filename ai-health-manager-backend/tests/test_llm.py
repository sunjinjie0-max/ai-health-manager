import pytest
from unittest.mock import AsyncMock, MagicMock

from app.llm.deepseek import DeepSeekClient
from app.llm.usage import track_llm_usage


@pytest.fixture
def client():
    c = DeepSeekClient()
    c.llm = MagicMock()
    return c


@pytest.mark.asyncio
async def test_chat(client):
    mock_response = MagicMock()
    mock_response.content = "你好，我是AI健康管家"
    client.llm.ainvoke = AsyncMock(return_value=mock_response)
    result = await client.chat("你是健康顾问", "你好")
    assert "AI健康管家" in result


@pytest.mark.asyncio
async def test_json_chat_valid(client):
    mock_response = MagicMock()
    mock_response.content = '{"intent": "general_health", "safety_flag": null}'
    client.llm.ainvoke = AsyncMock(return_value=mock_response)
    result = await client.json_chat("分类意图", "我头疼")
    assert result["intent"] == "general_health"


@pytest.mark.asyncio
async def test_json_chat_with_code_fence(client):
    mock_response = MagicMock()
    mock_response.content = '```json\n{"intent": "nutrition"}\n```'
    client.llm.ainvoke = AsyncMock(return_value=mock_response)
    result = await client.json_chat("分类意图", "分析食物")
    assert result["intent"] == "nutrition"


@pytest.mark.asyncio
async def test_json_chat_invalid_json(client):
    mock_response = MagicMock()
    mock_response.content = "这不是JSON"
    client.llm.ainvoke = AsyncMock(return_value=mock_response)
    result = await client.json_chat("分类意图", "你好")
    assert "raw_response" in result


@pytest.mark.asyncio
async def test_chat_records_token_usage(client):
    mock_response = MagicMock()
    mock_response.content = "建议每周保持规律运动。"
    mock_response.usage_metadata = {
        "input_tokens": 12,
        "output_tokens": 8,
        "total_tokens": 20,
    }
    client.llm.ainvoke = AsyncMock(return_value=mock_response)

    with track_llm_usage() as tracker:
        result = await client.chat("你是健康顾问", "怎么运动？", stage="test.chat")

    summary = tracker.summary()
    assert result.startswith("建议")
    assert summary["call_count"] == 1
    assert summary["prompt_tokens"] == 12
    assert summary["completion_tokens"] == 8
    assert summary["total_tokens"] == 20
    assert summary["estimated"] is False
    assert summary["calls"][0]["stage"] == "test.chat"
