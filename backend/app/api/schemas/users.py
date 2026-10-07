from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TeacherBrief(BaseModel):
    id: int
    name: str


class MeResponse(BaseModel):
    id: int
    username: str
    name: str
    role: Literal["student", "teacher", "admin"]
    major: str | None = None
    teacher: TeacherBrief | None = None
    must_change_password: bool
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)
