from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_SECRET = "0" * 32

# 全部字段（无默认值，缺一不可）；测试用值
FULL_VALUES: dict[str, Any] = {
    "database_url": "postgresql+asyncpg://user:pw@localhost:5432/db",
    "jwt_secret": VALID_SECRET,
    "access_token_expire_minutes": 60,
    "cors_origins": ["http://localhost:5173"],
    "db_pool_size": 5,
    "db_max_overflow": 10,
    "db_pool_timeout": 30,
    "db_pool_recycle": 1800,
    "storage_dir": "storage",
    "review_concurrency": 4,
    "upload_max_bytes": 50 * 1024 * 1024,
    "task_poll_interval_seconds": 1.0,
    "task_max_attempts": 3,
    "task_stale_seconds": 600,
}


def _settings(**overrides: Any) -> Settings:
    """用字段值直接构造；`_env_file=None` 断开 .env，只测代码内校验规则。"""
    values = dict(FULL_VALUES)
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_jwt_secret_must_be_long_enough():
    with pytest.raises(ValidationError):
        _settings(jwt_secret="short")


def test_jwt_secret_rejects_placeholder():
    with pytest.raises(ValidationError):
        _settings(jwt_secret="change-me-in-production-min-32-bytes!!")


def test_valid_settings_pass():
    settings = _settings()
    assert settings.jwt_secret == VALID_SECRET
    assert settings.storage_dir == Path("storage")
    assert settings.review_concurrency == 4
    assert settings.upload_max_bytes == 50 * 1024 * 1024
    assert settings.task_poll_interval_seconds == 1.0
    assert settings.task_max_attempts == 3
    assert settings.task_stale_seconds == 600


@pytest.mark.parametrize("field", sorted(FULL_VALUES))
def test_every_setting_is_required(field: str):
    """所有字段必填（无代码内默认值）：缺任意一个都报 ValidationError。"""
    values = dict(FULL_VALUES)
    del values[field]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("review_concurrency", 0),
        ("review_concurrency", 33),
        ("upload_max_bytes", 0),
        ("task_poll_interval_seconds", 0),
        ("task_max_attempts", 0),
        ("task_stale_seconds", 59),
    ],
)
def test_new_settings_reject_out_of_range(field: str, value: Any):
    with pytest.raises(ValidationError):
        _settings(**{field: value})
