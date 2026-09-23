import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("OSRM_URL", "http://localhost:5000")
    monkeypatch.setenv("APP_MODE", "demo")

    settings = Settings()

    assert settings.database_url == "postgresql://user:pass@localhost/db"
    assert settings.osrm_url == "http://localhost:5000"
    assert settings.app_mode == "demo"


def test_settings_rejects_unknown_app_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("OSRM_URL", "http://localhost:5000")
    monkeypatch.setenv("APP_MODE", "production")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_missing_required_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OSRM_URL", "http://localhost:5000")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_rejects_unknown_log_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("OSRM_URL", "http://localhost:5000")
    monkeypatch.setenv("LOG_FORMAT", "xml")

    with pytest.raises(ValidationError):
        Settings()
