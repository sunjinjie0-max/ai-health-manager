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


@pytest.fixture
async def auth_headers(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "healthuser", "password": "testpass123"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.mark.asyncio
async def test_health_import_query_and_stats(client, auth_headers):
    csv_content = "date,steps,distance,calories\n2026-05-15,8000,5.6,320\n2026-05-16,9200,6.2,370\n"
    files = {"file": ("steps.csv", csv_content.encode("utf-8"), "text/csv")}
    data = {"format": "csv", "dataType": "steps"}

    import_resp = await client.post(
        "/api/v1/health/import",
        data=data,
        files=files,
        headers=auth_headers,
    )

    assert import_resp.status_code == 200
    assert import_resp.json()["imported_count"] == 2
    assert import_resp.json()["failed_count"] == 0

    profile_resp = await client.get(
        "/api/v1/health/profile?type=steps&startDate=2026-05-01&endDate=2026-05-31",
        headers=auth_headers,
    )
    assert profile_resp.status_code == 200
    records = profile_resp.json()["records"]["steps"]
    assert len(records) == 2
    assert records[0]["steps"] == 8000

    stats_resp = await client.get(
        "/api/v1/health/stats?data_type=steps&period=3650d",
        headers=auth_headers,
    )
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["count"] == 2
    assert stats["total"] == 17200


@pytest.mark.asyncio
async def test_health_profile_requires_auth(client):
    resp = await client.get("/api/v1/health/profile")
    assert resp.status_code in (401, 403)
