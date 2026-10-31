"""CORS origins come from the environment (FRONTEND_ORIGINS); no database needed."""
from app.config import DEFAULT_ORIGINS, Settings


def settings(**kwargs) -> Settings:
    return Settings(_env_file=None, database_url="postgresql://u:p@h/db", jwt_secret="x", **kwargs)


def test_defaults_to_local_development_origins():
    assert settings().cors_origin_list == DEFAULT_ORIGINS.split(",")


def test_frontend_origins_are_split_trimmed_and_lose_trailing_slashes():
    s = settings(frontend_origins=" https://billing.example.com/ , https://admin.example.com,, ")
    assert s.cors_origin_list == ["https://billing.example.com", "https://admin.example.com"]


def test_frontend_origins_win_over_the_legacy_cors_origins_name():
    assert settings(frontend_origins="https://new.example.com", cors_origins="https://old.example.com").cors_origin_list == [
        "https://new.example.com"
    ]
    assert settings(cors_origins="https://old.example.com").cors_origin_list == ["https://old.example.com"]


def test_environment_variable_is_read(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://env.example.com/")
    assert Settings(_env_file=None, database_url="postgresql://u:p@h/db", jwt_secret="x").cors_origin_list == [
        "https://env.example.com"
    ]


def test_cors_headers_follow_the_setting(monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.example.com")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        ok = client.get("/api/v1/health", headers={"Origin": "https://app.example.com"})
        assert ok.headers.get("access-control-allow-origin") == "https://app.example.com"
        other = client.get("/api/v1/health", headers={"Origin": "https://evil.example.com"})
        assert "access-control-allow-origin" not in other.headers
    finally:
        get_settings.cache_clear()
