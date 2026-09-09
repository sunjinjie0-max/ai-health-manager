import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.database import Base, engine


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def auth_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/register", json={"username": "admin", "password": "secret123"})
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_import_pdf_to_knowledge_base(client, monkeypatch):
    from app.api.v1 import knowledge

    monkeypatch.setattr(
        knowledge,
        "extract_pdf_text",
        lambda data: ("成年人每晚推荐睡眠7-9小时。每周建议进行至少150分钟中等强度有氧运动。", {"page_count": 2}),
    )

    async def fake_add_documents(documents):
        return [doc["id"] for doc in documents]

    monkeypatch.setattr(knowledge.rag_retriever, "add_documents", fake_add_documents)

    headers = await auth_headers(client)
    resp = await client.post(
        "/api/v1/knowledge/import-pdf",
        headers=headers,
        data={"category": "lifestyle", "topic": "sleep", "chunk_size": "30", "chunk_overlap": "5"},
        files={"file": ("sleep-guide.pdf", b"%PDF-1.4 test", "application/pdf")},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "completed"
    assert payload["filename"] == "sleep-guide.pdf"
    assert payload["source_type"] == "pdf"
    assert payload["category"] == "lifestyle"
    assert payload["topic"] == "sleep"
    assert payload["chunk_count"] >= 1
    assert payload["imported_count"] == payload["chunk_count"]
    assert payload["preview_ids"]


@pytest.mark.asyncio
async def test_import_markdown_to_knowledge_base(client, monkeypatch):
    from app.api.v1 import knowledge

    captured_documents = []

    async def fake_add_documents(documents):
        captured_documents.extend(documents)
        return [doc["id"] for doc in documents]

    monkeypatch.setattr(knowledge.rag_retriever, "add_documents", fake_add_documents)

    headers = await auth_headers(client)
    resp = await client.post(
        "/api/v1/knowledge/import-file",
        headers=headers,
        data={"category": "exercise", "topic": "aerobic", "chunk_size": "40", "chunk_overlap": "5"},
        files={
            "file": (
                "exercise-guide.md",
                "# 运动指南\n\n成年人每周建议进行至少150分钟中等强度有氧运动。",
                "text/markdown",
            )
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "completed"
    assert payload["filename"] == "exercise-guide.md"
    assert payload["title"] == "exercise-guide"
    assert payload["source_type"] == "markdown"
    assert payload["category"] == "exercise"
    assert payload["topic"] == "aerobic"
    assert payload["chunk_count"] >= 1
    assert payload["imported_count"] == payload["chunk_count"]
    assert captured_documents[0]["metadata"]["source_type"] == "markdown"


@pytest.mark.asyncio
async def test_import_file_rejects_unsupported_file(client):
    headers = await auth_headers(client)
    resp = await client.post(
        "/api/v1/knowledge/import-file",
        headers=headers,
        files={"file": ("guide.txt", b"hello", "text/plain")},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "只支持上传 PDF 或 Markdown 文件"


@pytest.mark.asyncio
async def test_import_pdf_endpoint_still_rejects_non_pdf(client):
    headers = await auth_headers(client)
    resp = await client.post(
        "/api/v1/knowledge/import-pdf",
        headers=headers,
        files={"file": ("guide.md", b"# hello", "text/markdown")},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "只支持上传 PDF 文件"
