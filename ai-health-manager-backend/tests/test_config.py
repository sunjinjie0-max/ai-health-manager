from app.config import Settings


def test_settings_loads_defaults():
    s = Settings(deepseek_api_key="k", jwt_secret_key="s")
    assert s.deepseek_base_url == "https://ws-96cemtqnd0ne67ij.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_expire_hours == 24
    assert s.rate_limit_enabled is True
    assert s.rate_limit_general == 100
    assert s.max_request_body_bytes == 5 * 1024 * 1024
    assert s.max_upload_body_bytes == 50 * 1024 * 1024
    assert s.max_knowledge_pdf_bytes == 30 * 1024 * 1024


def test_settings_override():
    s = Settings(
        deepseek_api_key="k",
        jwt_secret_key="s",
        jwt_expire_hours=48,
    )
    assert s.jwt_expire_hours == 48
