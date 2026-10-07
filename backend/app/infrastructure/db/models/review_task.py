from datetime import datetime

from sqlmodel import Field

from app.infrastructure.db.base import TimestampMixin


class ReviewTask(TimestampMixin, table=True):
    __tablename__ = "review_tasks"

    id: int | None = Field(default=None, primary_key=True)
    submission_id: int = Field(
        foreign_key="submissions.id", unique=True, index=True, nullable=False
    )
    # 枚举：pending（待领取）/ processing（处理中）/ finished（已结束，终态）
    status: str = Field(default="pending", max_length=16, nullable=False)
    attempts: int = Field(default=0, nullable=False)
    error: str | None = Field(default=None)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)
