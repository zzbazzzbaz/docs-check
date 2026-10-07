from sqlmodel import Field

from app.infrastructure.db.base import TimestampMixin


class User(TimestampMixin, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, min_length=3, max_length=32)
    password_hash: str = Field(nullable=False)
    # 枚举：student（学生）/ teacher（教师）/ admin（管理员）
    role: str = Field(default="student", max_length=16)
    name: str = Field(default="", max_length=64)
    major: str | None = Field(default=None, max_length=64)
    teacher_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    must_change_password: bool = Field(default=True)
    is_active: bool = Field(default=True)
