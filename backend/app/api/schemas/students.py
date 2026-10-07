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


class TeacherStatsPoint(BaseModel):
    created_at: datetime
    counts: Counts


class TeacherStatsSeries(BaseModel):
    student_id: int
    username: str
    name: str
    points: list[TeacherStatsPoint]


class TeacherStatsResponse(BaseModel):
    student_count: int
    submitted_count: int
    series: list[TeacherStatsSeries]
