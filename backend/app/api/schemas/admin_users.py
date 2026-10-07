from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.users import TeacherBrief


class AdminUserItem(BaseModel):
    id: int
    username: str
    name: str
    role: Literal["student", "teacher"]
    major: str | None = None
    teacher: TeacherBrief | None = None
    student_count: int = 0
    is_active: bool
    created_at: datetime


class AdminUserCreate(BaseModel):
    model_config = {"extra": "forbid"}

    role: Literal["student", "teacher"]
    username: str = Field(min_length=3, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    major: str | None = Field(default=None, max_length=64)
    teacher_id: int | None = None


class AdminUserUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str | None = Field(default=None, min_length=1, max_length=64)
    major: str | None = Field(default=None, max_length=64)
    teacher_id: int | None = None


class AdminUserStatusUpdate(BaseModel):
    is_active: bool


class TeacherOption(BaseModel):
    id: int
    username: str
    name: str
