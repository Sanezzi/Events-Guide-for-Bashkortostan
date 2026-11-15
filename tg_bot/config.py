"""Environment configuration; importing this module has no network side effects."""

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PACKAGE_DIR.parent / ".env", PACKAGE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    bot_token: str = ""
    backend_url: str = ""
    internal_api_token: str = ""
    database_url: str = "sqlite+aiosqlite:///./tg_bot/catalog.db"
    webapp_url: str = ""
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    admin_ids: list[int] = Field(default_factory=list)
    dev_mode: bool = False
    seed_sample: bool = False
    timezone: str = "Asia/Yekaterinburg"
    init_data_max_age: int = Field(default=3600, ge=30, le=86400)

    @field_validator("database_url")
    @classmethod
    def async_driver(cls, value: str) -> str:
        if not value.strip():
            return "sqlite+aiosqlite:///./tg_bot/catalog.db"
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return value.replace(prefix, "postgresql+asyncpg://", 1)
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @model_validator(mode="after")
    def public_url(self):
        if self.webapp_url and not self.webapp_url.startswith("https://"):
            raise ValueError("WEBAPP_URL must be an HTTPS URL")
        if self.dev_mode and self.host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("DEV_MODE requires a loopback HOST")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
