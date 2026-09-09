import pytest
from importlib import import_module
from unittest.mock import AsyncMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.agents.health_advisor.nodes.post_process import _persist_profile_update, post_process
from app.agents.health_advisor.state import HealthAdvisorState
from app.models.database import Base
from app.models.user import User
from app.models.profile import UserProfile
from app.models.chat import ChatSession, ChatMessage
from app.models.health import HealthRecord
from app.services.health_service import HealthService
from app.core.time import utc_now_naive

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_user(db_session):
    user = User(username="testuser", password_hash="hashed")
    db_session.add(user)
    await db_session.commit()
    result = await db_session.execute(select(User).where(User.username == "testuser"))
    found = result.scalar_one()
    assert found.username == "testuser"
    assert found.id is not None


@pytest.mark.asyncio
async def test_create_profile(db_session):
    user = User(username="testuser2", password_hash="hashed")
    db_session.add(user)
    await db_session.commit()
    profile = UserProfile(
        user_id=user.id,
        basic_info={"age": 28, "gender": "male"},
        health_status={"chronic_diseases": ["高血压"]},
    )
    db_session.add(profile)
    await db_session.commit()
    result = await db_session.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    found = result.scalar_one()
    assert found.basic_info["age"] == 28
    assert "高血压" in found.health_status["chronic_diseases"]


@pytest.mark.asyncio
async def test_profile_update_persists_structured_profile(db_session):
    user = User(username="profile-update-user", password_hash="hashed")
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserProfile(user_id=user.id))
    await db_session.commit()

    extracted_profile = {
        "basic_info": {"age": 30, "gender": "male"},
        "health_status": {"allergies": ["芒果"]},
        "health_goals": ["减脂"],
        "diet_preferences": {"avoid": ["香菜"]},
    }

    updated = await _persist_profile_update(user.id, extracted_profile, db_session)

    profile_result = await db_session.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    profile = profile_result.scalar_one()
    assert updated is True
    assert profile.basic_info["age"] == 30
    assert profile.basic_info["gender"] == "male"
    assert "芒果" in profile.health_status["allergies"]
    assert "减脂" in profile.health_goals
    assert "香菜" in profile.diet_preferences["avoid"]


@pytest.mark.asyncio
async def test_post_process_schedules_structured_profile_update(monkeypatch):
    post_process_module = import_module("app.agents.health_advisor.nodes.post_process")
    monkeypatch.setattr(post_process_module, "_generate_followup_questions", AsyncMock(return_value=["还有其他问题吗？"]))
    monkeypatch.setattr(post_process_module.long_term_memory, "store_user_message_memories", AsyncMock(return_value=[]))

    scheduled = []

    async def fake_background_update(user_id, extracted_profile):
        scheduled.append((user_id, extracted_profile))

    def fake_create_task(coro):
        coro.close()
        scheduled.append(("scheduled", None))

    monkeypatch.setattr(post_process_module, "_profile_update_background_task", fake_background_update)
    monkeypatch.setattr(post_process_module.asyncio, "create_task", fake_create_task)

    state = HealthAdvisorState(
        user_id="profile-update-user",
        session_id="session-profile-update",
        user_message="我30岁，男性，对芒果过敏，我想减脂，平时不吃香菜。",
    )
    state["response"] = "我会结合你的情况给出建议。"

    result = await post_process(state)

    assert result["profile_update_scheduled"] is True
    assert result["profile_updated"] is False
    assert scheduled == [("scheduled", None)]


@pytest.mark.asyncio
async def test_create_chat_session_and_message(db_session):
    user = User(username="testuser3", password_hash="hashed")
    db_session.add(user)
    await db_session.commit()
    session = ChatSession(user_id=user.id)
    db_session.add(session)
    await db_session.commit()
    msg = ChatMessage(session_id=session.id, role="user", content="你好")
    db_session.add(msg)
    await db_session.commit()
    result = await db_session.execute(select(ChatMessage).where(ChatMessage.session_id == session.id))
    found = result.scalar_one()
    assert found.content == "你好"
    assert found.role == "user"


@pytest.mark.asyncio
async def test_health_service_agent_context(db_session):
    user = User(username="health-context-user", password_hash="hashed")
    db_session.add(user)
    await db_session.commit()

    db_session.add_all(
        [
            HealthRecord(
                user_id=user.id,
                data_type="steps",
                record_date=utc_now_naive().date(),
                data={"steps": 4200, "date": utc_now_naive().date().isoformat()},
            ),
            HealthRecord(
                user_id=user.id,
                data_type="sleep",
                record_date=utc_now_naive().date(),
                data={"duration": 5.5, "date": utc_now_naive().date().isoformat()},
            ),
        ]
    )
    await db_session.commit()

    context = await HealthService(db_session).get_agent_context(user.id, days=30)

    assert context["stats"]["steps"]["count"] == 1
    assert context["stats"]["sleep"]["average"] == 5.5
    assert "steps" in context["latest_records"]
    assert context["insights"]
