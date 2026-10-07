from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """配置来源：`.env`（唯一来源）；所有字段必填，缺 key 启动即报错（fail-fast）。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str = Field(min_length=32)
    access_token_expire_minutes: int
    cors_origins: list[str]
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout: int
    db_pool_recycle: int

    storage_dir: Path
    review_concurrency: int = Field(ge=1, le=32)
    upload_max_bytes: int = Field(ge=1)
    task_poll_interval_seconds: float = Field(gt=0)
    task_max_attempts: int = Field(ge=1)
    task_stale_seconds: int = Field(ge=60)

    @field_validator("jwt_secret")
    @classmethod
    def _reject_placeholder_secret(cls, value: str) -> str:
        if "change-me" in value:
            raise ValueError("JWT_SECRET 还是占位值，请换成随机密钥（openssl rand -hex 32）")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
