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


@dataclass(frozen=True, slots=True)
class StatsPoint:
    """趋势点：一次成功提交的四态计数。"""

    created_at: datetime
    fail_count: int
    undetermined_count: int
    not_run_count: int
    unrecognised_count: int


@dataclass(frozen=True, slots=True)
class StatsSeries:
    """单个学生的趋势序列（仅成功提交，时间正序，最多 50 点）。"""

    student_id: int
    username: str
    name: str
    points: list[StatsPoint]


@dataclass(frozen=True, slots=True)
class TeacherStats:
    """教师概览：名下启用学生数 / 提交过的学生数 / 趋势序列。"""

    student_count: int
    submitted_count: int
    series: list[StatsSeries]


POINTS_LIMIT = 50


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


async def get_stats(session: AsyncSession, *, teacher: User) -> TeacherStats:
    """名下启用学生概览：提交过（任意状态）计数 + 每生最近 50 次成功提交序列。"""
    students = (
        await session.exec(
            select(User)
            .where(User.role == "student", User.teacher_id == teacher.id, User.is_active)
            .order_by(col(User.username))
        )
    ).all()
    student_ids = [student.id for student in students if student.id is not None]
    if not student_ids:
        return TeacherStats(student_count=0, submitted_count=0, series=[])

    submitted_count = (
        await session.exec(
            select(func.count(func.distinct(Submission.student_id))).where(
                col(Submission.student_id).in_(student_ids)
            )
        )
    ).one()

    # 每生只取最近 POINTS_LIMIT 条成功提交：窗口函数先取 id，再按 id 取实体（库内截断）
    ranked = (
        select(
            Submission.id,
            func.row_number()
            .over(
                partition_by=col(Submission.student_id),
                order_by=(col(Submission.created_at).desc(), col(Submission.id).desc()),
            )
            .label("rn"),
        )
        .where(col(Submission.student_id).in_(student_ids), Submission.status == "success")
        .subquery()
    )
    keep_ids = (await session.exec(select(ranked.c.id).where(ranked.c.rn <= POINTS_LIMIT))).all()
    submissions = (
        await session.exec(
            select(Submission)
            .where(col(Submission.id).in_(keep_ids))
            .order_by(col(Submission.student_id), col(Submission.created_at), col(Submission.id))
        )
    ).all()

    points_by_student: dict[int, list[StatsPoint]] = {}
    for submission in submissions:
        points_by_student.setdefault(submission.student_id, []).append(
            StatsPoint(
                created_at=submission.created_at,
                fail_count=submission.fail_count,
                undetermined_count=submission.undetermined_count,
                not_run_count=submission.not_run_count,
                unrecognised_count=submission.unrecognised_count,
            )
        )

    series: list[StatsSeries] = []
    for student in students:
        student_id = student.id
        if student_id is None or student_id not in points_by_student:
            continue
        series.append(
            StatsSeries(
                student_id=student_id,
                username=student.username,
                name=student.name,
                points=points_by_student[student_id],
            )
        )
    return TeacherStats(student_count=len(students), submitted_count=submitted_count, series=series)


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
