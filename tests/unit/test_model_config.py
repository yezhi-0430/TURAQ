from app.config import Settings


def test_default_model_wait_fits_research_deadline(monkeypatch):
    monkeypatch.delenv("MODEL_HTTP_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("MODEL_TOTAL_TIMEOUT_SECONDS", raising=False)
    settings = Settings(
        _env_file=None,
        database_host="localhost",
        database_port=5432,
        database_name="test",
        database_user="test",
        database_password="test",
    )
    assert settings.model_http_timeout_seconds == 30
    assert settings.model_total_timeout_seconds == 60


def test_settings_reads_model_key_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-key")

    settings = Settings(
        _env_file=None,
        database_host="localhost",
        database_port=5432,
        database_name="test_db",
        database_user="test_user",
        database_password="test-password",
    )

    assert settings.dashscope_api_key.get_secret_value() == "test-only-key"
