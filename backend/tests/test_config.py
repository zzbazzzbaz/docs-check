from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_SECRET = "0" * 32


def _settings(**overrides: object) -> Settings:
    """直接从字段值构造（不走 .env），只测校验规则。"""
    values: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pw@localhost:5432/db",
        "jwt_secret": VALID_SECRET,
        "db_pool_size": 5,
        "db_max_overflow": 10,
        "db_pool_timeout": 30,
        "db_pool_recycle": 1800,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_jwt_secret_must_be_long_enough():
    with pytest.raises(ValidationError):
        _settings(jwt_secret="short")


def test_jwt_secret_rejects_placeholder():
    with pytest.raises(ValidationError):
        _settings(jwt_secret="change-me-in-production-min-32-bytes!!")


def test_valid_settings_pass():
    assert _settings().jwt_secret == VALID_SECRET


def test_new_settings_defaults():
    settings = _settings()
    assert settings.storage_dir == Path("storage")
    assert settings.review_concurrency == 4
    assert settings.upload_max_bytes == 50 * 1024 * 1024
    assert settings.task_poll_interval_seconds == 1.0
    assert settings.task_max_attempts == 3
    assert settings.task_stale_seconds == 600


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
def test_new_settings_reject_out_of_range(field: str, value: object):
    with pytest.raises(ValidationError):
        _settings(**{field: value})
