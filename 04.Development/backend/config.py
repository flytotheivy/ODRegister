"""Environment-only runtime configuration. No local/admin credential fallback."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="L1_", env_file=None, extra="ignore", hide_input_in_errors=True
    )
    environment: str = Field(default="development", validation_alias="L1_ENV")
    database_url: SecretStr | None = Field(
        default=None, validation_alias="DATABASE_URL", repr=False
    )
    connect_timeout: int = Field(default=2, ge=1, le=5)
    db_pool_mode: Literal["null", "bounded"] = "null"
    db_pool_size: int = Field(default=2, ge=1, le=5)
    db_pool_timeout: int = Field(default=2, ge=1, le=5)

    recovery_grant_seconds: int = Field(default=900, ge=60, le=3600)
    recovery_session_seconds: int = Field(default=600, ge=60, le=1800)
    app_origin: str = "http://127.0.0.1:8001"
    session_idle_seconds: int = Field(default=1800, ge=60, le=86400)
    session_absolute_seconds: int = Field(default=28800, ge=300, le=604800)

    @model_validator(mode="after")
    def session_configuration(self):
        origin = urlsplit(self.app_origin)
        if (
            origin.scheme not in ("http", "https")
            or not origin.netloc
            or origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
        ):
            raise ValueError("canonical origin required")
        _ = origin.port
        if not origin.hostname:
            raise ValueError("origin hostname required")
        if self.environment in ("development", "test") and origin.hostname not in (
            "127.0.0.1",
            "localhost",
            "::1",
            "testserver",
        ):
            raise ValueError("local environment requires loopback/test origin")
        if self.environment not in ("development", "test") and origin.scheme != "https":
            raise ValueError("HTTPS origin required")
        if self.session_idle_seconds > self.session_absolute_seconds:
            raise ValueError("idle exceeds absolute lifetime")
        return self


@lru_cache
def get_settings():
    return Settings()
