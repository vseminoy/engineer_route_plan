from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    database_url: str
    osrm_url: str
    app_mode: Literal["demo", "full"] = "demo"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    # Largest accepted request body, bytes; the upload of a data file is the biggest request.
    max_request_body_bytes: int = Field(default=10 * 1024 * 1024, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
