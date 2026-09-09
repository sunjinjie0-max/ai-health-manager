import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.chat import ChatMessage, ChatSession
from app.models.database import Base
from app.models.profile import UserProfile
from app.models.user import User
from app.services.suggested_questions import (
    filter_suggested_questions,
    suggested_question_service,
)

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
async def test_home_suggestions_use_profile_and_recent_messages(db_session, monkeypatch):
    user = User(username="suggestion-user", password_hash="hashed")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserProfile(
            user_id=user.id,
            health_goals=["减脂"],
            diet_preferences={"avoid": ["香菜"]},
        )
    )
    session = ChatSession(user_id=user.id)
    db_session.add(session)
    await db_session.flush()
    db_session.add(ChatMessage(session_id=session.id, role="user", content="我周末经常跑步和锻炼"))
    await db_session.commit()

    async def fake_search_memories(*args, **kwargs):
        return [{"content": "用户习惯周末跑步。"}]

    monkeypatch.setattr(
        "app.services.suggested_questions.long_term_memory.search_memories",
        fake_search_memories,
    )

    suggestions = await suggested_question_service.get_home_suggestions(db_session, user.id)

    assert len(suggestions) == 3
    assert any("饮食" in item or "目标" in item for item in suggestions)
    assert any("运动" in item or "强度" in item for item in suggestions)


def test_filter_suggested_questions_removes_generic_duplicate_and_unsafe_items():
    questions = [
        "建议多大的身体活动量？",
        "您还有其他健康方面的问题吗？",
        "我该吃什么药？",
        "怎么判断运动强度是否合适？",
        "怎么判断运动强度是否合适？",
    ]

    filtered = filter_suggested_questions(
        questions,
        current_question="建议多大的身体活动量？",
        fallback=["结合我的情况安排一周运动计划"],
    )

    assert filtered == [
        "怎么判断运动强度是否合适？",
        "结合我的情况安排一周运动计划？",
        "分析一下我最近的睡眠状态？",
    ]
