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
    # One `osrm-routed` per profile: a server answers only for the graph it loaded.
    osrm_url_car: str
    osrm_url_foot: str
    osrm_url_bike: str
    # Public transport travel time = car travel time × this factor: an averaged allowance
    # for transfers, waiting and walking, not a transit route.
    public_transport_factor: float = Field(default=1.5, ge=1, allow_inf_nan=False)
    # The `--max-table-size` of the OSRM servers; larger tables are requested in strips.
    osrm_max_table_size: int = Field(default=1000, gt=0)
    # Seconds, for each phase of an OSRM request (connect, send, each wait for data): a table
    # of a region's day (up to ~530 points) takes up to ~26 s on the bike graph.
    osrm_timeout_s: float = Field(default=60, gt=0, allow_inf_nan=False)
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
