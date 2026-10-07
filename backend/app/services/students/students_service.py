"""教师视角：名下学生列表（含提交聚合）、学生信息、学生提交列表。"""

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import col, func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.infrastructure.db.models.submission import Submission
from app.infrastructure.db.models.user import User
from app.services.errors import ForbiddenError, NotFoundError
from app.services.pagination import normalize
from app.services.submissions import submissions_service


@dataclass(frozen=True, slots=True)
class StudentRow:
    """列表行 = 学生 + 聚合字段（最近一次成功提交在响应层换算成计数）。"""

    user: User
    success_count: int
    latest_submitted_at: datetime | None
    latest_success: Submission | None


async def list_students(
    session: AsyncSession, *, teacher: User, q: str | None, offset: int, limit: int
) -> tuple[int, list[StudentRow]]:
    offset, limit = normalize(offset, limit)
    conditions = [User.role == "student", User.teacher_id == teacher.id, User.is_active]
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        conditions.append(or_(col(User.username).ilike(pattern), col(User.name).ilike(pattern)))

    total = (await session.exec(select(func.count()).select_from(User).where(*conditions))).one()

    success_count = (
        select(func.count())
        .select_from(Submission)
        .where(Submission.student_id == User.id, Submission.status == "success")
        .scalar_subquery()
    )
    latest_submitted_at = (
        select(func.max(Submission.created_at))
        .where(Submission.student_id == User.id)
        .scalar_subquery()
    )
    rows = (
        await session.exec(
            select(User, success_count, latest_submitted_at)
            .where(*conditions)
            .order_by(col(User.username))
            .offset(offset)
            .limit(limit)
        )
    ).all()

    page: list[tuple[User, int, datetime | None]] = [(row[0], row[1], row[2]) for row in rows]
    student_ids = [user.id for user, _, _ in page if user.id is not None]
    latest_map = await _latest_success_map(session, student_ids)

    items: list[StudentRow] = []
    for user, success, latest_at in page:
        user_id = user.id
        items.append(
            StudentRow(
                user=user,
                success_count=success,
                latest_submitted_at=latest_at,
                latest_success=latest_map.get(user_id) if user_id is not None else None,
            )
        )
    return total, items


async def _latest_success_map(
    session: AsyncSession, student_ids: list[int]
) -> dict[int, Submission]:
    """当前页学生的「最近一次成功提交」：DISTINCT ON (student_id)。"""
    if not student_ids:
        return {}
    rows = (
        await session.exec(
            select(Submission)
            .where(col(Submission.student_id).in_(student_ids), Submission.status == "success")
            .order_by(
                col(Submission.student_id),
                col(Submission.created_at).desc(),
                col(Submission.id).desc(),
            )
            .distinct(col(Submission.student_id))
        )
    ).all()
    return {row.student_id: row for row in rows}


async def get_student(session: AsyncSession, *, teacher: User, student_id: int) -> User:
    """非学生 / 禁用 / 不存在 → 404；存在但非名下 → 403。"""
    student = await session.get(User, student_id)
    if student is None or student.role != "student" or not student.is_active:
        raise NotFoundError(f"student {student_id} not found")
    if student.teacher_id != teacher.id:
        raise ForbiddenError("无权访问该学生")
    return student


async def list_submissions(
    session: AsyncSession, *, teacher: User, student_id: int, offset: int, limit: int
) -> tuple[int, list[Submission]]:
    student = await get_student(session, teacher=teacher, student_id=student_id)
    return await submissions_service.list_mine(session, student=student, offset=offset, limit=limit)
