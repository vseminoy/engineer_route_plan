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


def _required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("OSRM_URL", "http://localhost:5000")


def test_settings_max_request_body_bytes_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.delenv("MAX_REQUEST_BODY_BYTES", raising=False)

    assert Settings(_env_file=None).max_request_body_bytes == 10485760


def test_settings_max_request_body_bytes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "2048")

    assert Settings().max_request_body_bytes == 2048


@pytest.mark.parametrize("value", ["0", "-1"])
def test_settings_rejects_non_positive_body_limit(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", value)

    with pytest.raises(ValidationError):
        Settings()
