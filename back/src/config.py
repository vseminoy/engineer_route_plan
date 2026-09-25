from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingSettings(BaseSettings):
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"


class Settings(LoggingSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    database_url: str
    osrm_url: str
    app_mode: Literal["demo", "full"] = "demo"
    # Largest accepted request body, bytes; the upload of a data file is the biggest request.
    max_request_body_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    # Fallback geocoder for addresses missing from the geocache; empty switches it off.
    nominatim_url: str = ""
    nominatim_user_agent: str = "engineer-route-plan/0.1"
    # Cache misses of one load sent to Nominatim; the rest stay without a point.
    nominatim_max_lookups: int = Field(default=50, ge=0)


class MigrationSettings(LoggingSettings):
    """Settings of the process that applies migrations.

    Read from the process environment only, never from `.env`: the schema owner's
    address stays out of the application's configuration.
    """

    model_config = SettingsConfigDict(env_file=None)

    migration_database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
