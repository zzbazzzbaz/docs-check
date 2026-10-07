from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.infrastructure.db.base import TimestampMixin


class Submission(TimestampMixin, table=True):
    __tablename__ = "submissions"

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    original_filename: str = Field(max_length=255, nullable=False)
    # 枚举：pending（排队中）/ processing（审核中）/ success（成功）/ failed（失败，终态）
    status: str = Field(default="pending", max_length=16, nullable=False)
    error_message: str | None = Field(default=None)
    fail_count: int = Field(default=0, nullable=False)
    undetermined_count: int = Field(default=0, nullable=False)
    not_run_count: int = Field(default=0, nullable=False)
    unrecognised_count: int = Field(default=0, nullable=False)
    by_scope: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    ruleset_version: str | None = Field(default=None, max_length=32)
    storage_dir: str | None = Field(default=None, max_length=255)
