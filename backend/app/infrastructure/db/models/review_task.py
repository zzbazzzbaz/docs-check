from datetime import datetime

from sqlmodel import Field

from app.infrastructure.db.base import TimestampMixin


class ReviewTask(TimestampMixin, table=True):
    __tablename__ = "review_tasks"

    id: int | None = Field(default=None, primary_key=True)
    submission_id: int = Field(
        foreign_key="submissions.id", unique=True, index=True, nullable=False
    )
    # pending / processing / finished（队列状态，与 submissions.status 解耦）
    status: str = Field(default="pending", max_length=16, nullable=False)
    attempts: int = Field(default=0, nullable=False)
    error: str | None = Field(default=None)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)
