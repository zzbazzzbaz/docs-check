from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.infrastructure.db.base import TimestampMixin


class Submission(TimestampMixin, table=True):
    __tablename__ = "submissions"

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    original_filename: str = Field(max_length=255, nullable=False)
    storage_dir: str | None = Field(default=None, max_length=255)

    # 唯一状态机（前端轮询依据 + worker 队列依据）
    # 枚举：pending（排队中）/ processing（审核中）/ success（成功）/ failed（失败，终态）
    status: str = Field(default="pending", max_length=16, nullable=False, index=True)
    error_message: str | None = Field(default=None)  # 面向学生（中文，可直接展示）
    task_error: str | None = Field(default=None)  # 最近一次基础设施异常（诊断用）
    attempts: int = Field(default=0, nullable=False)  # 领取次数（重试上限）
    started_at: datetime | None = Field(default=None)  # 领取时间（stale 判定）
    finished_at: datetime | None = Field(default=None)  # 终态时间（观测）

    fail_count: int = Field(default=0, nullable=False)
    undetermined_count: int = Field(default=0, nullable=False)
    not_run_count: int = Field(default=0, nullable=False)
    unrecognised_count: int = Field(default=0, nullable=False)
    by_scope: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    ruleset_version: str | None = Field(default=None, max_length=32)
