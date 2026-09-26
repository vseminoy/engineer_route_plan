from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import MigrationSettings, Settings


def test_settings_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("OSRM_URL_CAR", "http://osrm-car:5000")
    monkeypatch.setenv("OSRM_URL_FOOT", "http://osrm-foot:5000")
    monkeypatch.setenv("OSRM_URL_BIKE", "http://osrm-bike:5000")
    monkeypatch.setenv("APP_MODE", "demo")

    settings = Settings()

    assert settings.database_url == "postgresql://user:pass@localhost/db"
    assert settings.osrm_url_car == "http://osrm-car:5000"
    assert settings.osrm_url_foot == "http://osrm-foot:5000"
    assert settings.osrm_url_bike == "http://osrm-bike:5000"
    assert settings.app_mode == "demo"


def test_settings_rejects_unknown_app_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("OSRM_URL_CAR", "http://osrm-car:5000")
    monkeypatch.setenv("OSRM_URL_FOOT", "http://osrm-foot:5000")
    monkeypatch.setenv("OSRM_URL_BIKE", "http://osrm-bike:5000")
    monkeypatch.setenv("APP_MODE", "production")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_missing_required_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OSRM_URL_CAR", "http://osrm-car:5000")
    monkeypatch.setenv("OSRM_URL_FOOT", "http://osrm-foot:5000")
    monkeypatch.setenv("OSRM_URL_BIKE", "http://osrm-bike:5000")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_rejects_unknown_log_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("OSRM_URL_CAR", "http://osrm-car:5000")
    monkeypatch.setenv("OSRM_URL_FOOT", "http://osrm-foot:5000")
    monkeypatch.setenv("OSRM_URL_BIKE", "http://osrm-bike:5000")
    monkeypatch.setenv("LOG_FORMAT", "xml")

    with pytest.raises(ValidationError):
        Settings()


def _required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("OSRM_URL_CAR", "http://osrm-car:5000")
    monkeypatch.setenv("OSRM_URL_FOOT", "http://osrm-foot:5000")
    monkeypatch.setenv("OSRM_URL_BIKE", "http://osrm-bike:5000")


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


@pytest.mark.parametrize("name", ["OSRM_URL_CAR", "OSRM_URL_FOOT", "OSRM_URL_BIKE"])
def test_settings_missing_osrm_url(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    _required_env(monkeypatch)
    monkeypatch.delenv(name)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_osrm_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.delenv("PUBLIC_TRANSPORT_FACTOR", raising=False)
    monkeypatch.delenv("OSRM_MAX_TABLE_SIZE", raising=False)

    settings = Settings(_env_file=None)

    assert settings.public_transport_factor == 1.5
    assert settings.osrm_max_table_size == 1000
    assert settings.osrm_timeout_s == 60


@pytest.mark.parametrize("value", ["0.9", "0", "-1", "inf", "nan"])
def test_settings_rejects_public_transport_factor_below_one(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("PUBLIC_TRANSPORT_FACTOR", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["0", "-1", "inf"])
def test_settings_rejects_bad_osrm_timeout(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("OSRM_TIMEOUT_S", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["0", "-1"])
def test_settings_rejects_non_positive_max_table_size(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("OSRM_MAX_TABLE_SIZE", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_migration_settings_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for name in ("OSRM_URL_CAR", "OSRM_URL_FOOT", "OSRM_URL_BIKE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://owner:pw@db:5432/plan")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FORMAT", "console")

    settings = MigrationSettings()

    assert settings.migration_database_url == "postgresql://owner:pw@db:5432/plan"
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "console"


def test_migration_settings_missing_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        MigrationSettings()


def test_migration_settings_ignore_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text("MIGRATION_DATABASE_URL=postgresql://owner:pw@db/plan\n")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError):
        MigrationSettings()


def test_settings_ignore_migration_vars_in_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://owner:pw@db/plan")
    monkeypatch.setenv("APP_RW_PASSWORD", "rw")
    monkeypatch.setenv("APP_RO_PASSWORD", "ro")

    settings = Settings(_env_file=None)

    assert not hasattr(settings, "migration_database_url")
    assert settings.database_url == "postgresql://user:pass@localhost/db"
