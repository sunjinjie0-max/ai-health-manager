from app.config import Settings


def test_settings_loads_defaults(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    s = Settings(
        _env_file=None,
        deepseek_api_key="k",
        jwt_secret_key="s",
    )
    assert s.deepseek_base_url == "https://api.deepseek.com"
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_expire_hours == 24
    assert s.rate_limit_enabled is True
    assert s.rate_limit_general == 100
    assert s.max_request_body_bytes == 5 * 1024 * 1024
    assert s.max_upload_body_bytes == 50 * 1024 * 1024
    assert s.max_knowledge_pdf_bytes == 30 * 1024 * 1024
    assert s.agent_request_timeout_seconds == 60
    assert s.nutrition_agent_timeout_seconds == 25
    assert s.environment_agent_timeout_seconds == 15
    assert s.exercise_agent_timeout_seconds == 25
    assert s.final_generation_timeout_seconds == 20
    assert s.chat_persistence_timeout_seconds == 3


def test_settings_override():
    s = Settings(
        deepseek_api_key="k",
        jwt_secret_key="s",
        jwt_expire_hours=48,
    )
    assert s.jwt_expire_hours == 48
