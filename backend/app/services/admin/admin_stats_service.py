"""管理端仪表盘：账号与提交数量概览（仅计数，不含任何提交内容）。"""

from dataclasses import dataclass

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.infrastructure.db.models.submission import Submission
from app.infrastructure.db.models.user import User


@dataclass(frozen=True, slots=True)
class StatsCounts:
    student_count: int
    teacher_count: int
    submission_count: int


async def _user_count(session: AsyncSession, *, role: str) -> int:
    return (
        await session.exec(
            select(func.count()).select_from(User).where(User.role == role, User.is_active)
        )
    ).one()


async def get_stats(session: AsyncSession) -> StatsCounts:
    """启用学生数 / 启用教师数 / 全部提交数。"""
    submission_count = (await session.exec(select(func.count()).select_from(Submission))).one()
    return StatsCounts(
        student_count=await _user_count(session, role="student"),
        teacher_count=await _user_count(session, role="teacher"),
        submission_count=submission_count,
    )
