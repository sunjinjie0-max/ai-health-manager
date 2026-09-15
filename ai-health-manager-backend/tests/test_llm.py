import pytest
from unittest.mock import AsyncMock, MagicMock

from app.llm.deepseek import DeepSeekClient, LLMResponseError
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
    first_response = MagicMock()
    first_response.content = '{"intent":'
    second_response = MagicMock()
    second_response.content = '{"intent":'
    client.llm.ainvoke = AsyncMock(side_effect=[first_response, second_response])

    with pytest.raises(LLMResponseError, match="invalid JSON") as exc_info:
        await client.json_chat("分类意图", "你好")

    assert exc_info.value.code == "invalid_json"
    assert client.llm.ainvoke.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["", "   ", "```json\n```"])
async def test_chat_rejects_empty_content_after_one_retry(client, content):
    mock_response = MagicMock()
    mock_response.content = content
    client.llm.ainvoke = AsyncMock(return_value=mock_response)

    with pytest.raises(LLMResponseError) as exc_info:
        await client.chat("健康顾问", "你好")

    assert exc_info.value.code == "empty_response"
    assert client.llm.ainvoke.await_count == 2


@pytest.mark.asyncio
async def test_chat_can_disable_inner_retry(client):
    mock_response = MagicMock()
    mock_response.content = ""
    client.llm.ainvoke = AsyncMock(return_value=mock_response)

    with pytest.raises(LLMResponseError):
        await client.chat("健康顾问", "你好", max_attempts=1)

    assert client.llm.ainvoke.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("finish_reason", "error_code"),
    [("length", "truncated_response"), ("content_filter", "content_filtered")],
)
async def test_chat_rejects_unusable_finish_reason(client, finish_reason, error_code):
    mock_response = MagicMock()
    mock_response.content = "这是一段看起来存在内容但不可使用的回答。"
    mock_response.response_metadata = {"finish_reason": finish_reason}
    client.llm.ainvoke = AsyncMock(return_value=mock_response)

    with pytest.raises(LLMResponseError) as exc_info:
        await client.chat("健康顾问", "你好")

    assert exc_info.value.code == error_code
    assert client.llm.ainvoke.await_count == 2


@pytest.mark.asyncio
async def test_chat_retries_network_timeout_once_then_succeeds(client):
    valid_response = MagicMock()
    valid_response.content = "这是重试后返回的有效健康建议。"
    client.llm.ainvoke = AsyncMock(
        side_effect=[TimeoutError("provider timeout"), valid_response]
    )

    result = await client.chat("健康顾问", "你好")

    assert result == "这是重试后返回的有效健康建议。"
    assert client.llm.ainvoke.await_count == 2


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
