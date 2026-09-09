"""Tests for Chat API."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.v1.chat_routes import _compact_session_title
from app.models.database import Base, engine


@pytest.fixture(autouse=True)
async def setup_db():
    """Set up test database."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def auth_token(client):
    """Get auth token for test user."""
    # Register user
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "testpass123"},
    )
    if resp.status_code != 200:
        # Try login if registration fails (user might exist)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "testpass123"},
        )

    assert resp.status_code == 200
    data = resp.json()
    return data["token"]


class TestChatAPI:
    """Test Chat API endpoints."""

    def test_compact_session_title_prefers_health_topic(self):
        assert _compact_session_title("请帮我分析一下最近一周睡眠状态以及怎么调整作息") == "睡眠作息调整"
        assert _compact_session_title("今天早餐营养搭配怎么样？") == "饮食营养分析"
        assert _compact_session_title("你好") == "你好"

    @pytest.mark.asyncio
    @patch("app.api.v1.chat_routes.check_safety")
    @patch("app.api.v1.chat_routes.classify_intent")
    @patch("app.api.v1.chat_routes.rag_retrieve")
    @patch("app.api.v1.chat_routes.generate_response")
    @patch("app.api.v1.chat_routes.post_process")
    async def test_send_message(
        self,
        mock_post_process,
        mock_generate_response,
        mock_rag_retrieve,
        mock_classify_intent,
        mock_check_safety,
        client,
        auth_token,
    ):
        """Test sending a chat message."""
        # Mock the node functions
        from app.agents.health_advisor.state import HealthAdvisorState

        def create_state():
            state = HealthAdvisorState(
                user_id="test_user",
                session_id="test_session",
                user_message="你好",
            )
            state["response"] = "你好！我是AI健康管家，有什么可以帮助您的吗？"
            state["suggested_questions"] = ["如何保持健康？", "每天应该喝多少水？"]
            state["citations"] = []
            return state

        mock_check_safety.return_value = create_state()
        mock_classify_intent.return_value = create_state()
        mock_rag_retrieve.return_value = create_state()
        mock_generate_response.return_value = create_state()
        mock_post_process.return_value = create_state()

        # Send message
        resp = await client.post(
            "/api/v1/chat/send",
            json={"message": "你好"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "session_id" in data
        assert data["session_title"] == "你好"
        assert "message_id" in data
        assert "trace_id" in data
        assert resp.headers.get("x-trace-id") == data["trace_id"]
        assert "suggested_questions" in data

    @pytest.mark.asyncio
    @patch("app.api.v1.chat_routes.check_safety")
    @patch("app.api.v1.chat_routes.classify_intent")
    @patch("app.api.v1.chat_routes.rag_retrieve")
    @patch("app.api.v1.chat_routes.generate_response")
    @patch("app.api.v1.chat_routes.post_process")
    async def test_send_message_persists_history(
        self,
        mock_post_process,
        mock_generate_response,
        mock_rag_retrieve,
        mock_classify_intent,
        mock_check_safety,
        client,
        auth_token,
    ):
        from app.agents.health_advisor.state import HealthAdvisorState

        def create_state():
            state = HealthAdvisorState(user_id="test_user", session_id="test_session", user_message="你好")
            state["response"] = "你好，我已记录这次对话。"
            state["suggested_questions"] = []
            state["citations"] = []
            return state

        mock_check_safety.return_value = create_state()
        mock_classify_intent.return_value = create_state()
        mock_rag_retrieve.return_value = create_state()
        mock_generate_response.return_value = create_state()
        mock_post_process.return_value = create_state()

        resp = await client.post(
            "/api/v1/chat/send",
            json={"message": "你好"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        history_resp = await client.get(
            f"/api/v1/chat/history/{session_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert history_resp.status_code == 200
        messages = history_resp.json()["messages"]
        assert [msg["role"] for msg in messages] == ["user", "assistant"]
        assert messages[0]["content"] == "你好"

    @pytest.mark.asyncio
    async def test_send_message_requires_auth(self, client):
        resp = await client.post("/api/v1/chat/send", json={"message": "你好"})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_get_suggestions(self, client, auth_token):
        """Test getting suggestions."""
        resp = await client.post(
            "/api/v1/chat/suggestions",
            json={"message": "我想了解"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
        assert len(data["suggestions"]) <= 3

    @pytest.mark.asyncio
    async def test_record_suggestion_feedback(self, client, auth_token):
        resp = await client.post(
            "/api/v1/chat/suggestions/feedback",
            json={
                "question": "结合我的运动习惯安排本周计划？",
                "action": "clicked",
                "source": "memory_exercise",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["id"]

    @pytest.mark.asyncio
    async def test_chat_history(self, client, auth_token):
        """Test getting chat history."""
        # First create a session by sending a message
        # Then get history

        # For now, just test with a fake session ID
        # This will 404 but tests the endpoint
        resp = await client.get(
            "/api/v1/chat/history/nonexistent",
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        # Should be 404 for non-existent session
        assert resp.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
