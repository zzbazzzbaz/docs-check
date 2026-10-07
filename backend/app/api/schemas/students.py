from datetime import datetime

from pydantic import BaseModel

from app.api.schemas.submissions import Counts


class StudentListItem(BaseModel):
    id: int
    username: str
    name: str
    major: str | None = None
    success_count: int
    latest_submitted_at: datetime | None = None
    latest_counts: Counts | None = None


class StudentDetail(BaseModel):
    id: int
    username: str
    name: str
    major: str | None = None
