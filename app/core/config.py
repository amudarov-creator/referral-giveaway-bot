"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str = Field(..., min_length=10)
    webhook_secret: str = Field(default="change-me", min_length=8)
    webhook_path: str = "/webhook"
    webhook_host: str = ""
    bot_mode: str = Field(default="polling", pattern="^(polling|webhook)$")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://giveaway_bot:password@localhost:5432/giveaway"
    )
    postgres_user: str = "giveaway_bot"
    postgres_password: str = "password"
    postgres_db: str = "giveaway"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Admins
    admin_ids: Annotated[list[int], Field(default_factory=list)]

    # Rate limits
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 30
    invite_link_rate_limit_per_hour: int = 5
    membership_check_cooldown_seconds: int = 30

    # Giveaway defaults
    default_timezone: str = "Europe/Moscow"
    verification_period_hours: int = 48
    appeal_period_hours: int = 72
    data_retention_days: int = 365

    # Logging / health
    log_level: str = "INFO"
    log_json: bool = True
    health_port: int = 8080

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: object) -> list[int]:
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return []

    @property
    def is_webhook(self) -> bool:
        return self.bot_mode == "webhook"


@lru_cache
def get_settings() -> Settings:
    return Settings()
