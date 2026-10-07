"""管理端用户管理：列表（含聚合）、新建、编辑、禁用/启用、重置密码、教师下拉。"""

from dataclasses import dataclass
from typing import Any

from sqlmodel import col, func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import hash_password
from app.infrastructure.db.models.user import User
from app.services.errors import InvalidActionError, NotFoundError
from app.services.pagination import normalize
from app.services.users import users_service

_MANAGED_ROLES = ("student", "teacher")
_STUDENT_FIELDS = {"name", "major", "teacher_id"}
_TEACHER_FIELDS = {"name"}


@dataclass(frozen=True, slots=True)
class AdminUserRow:
    """列表行：账号 + 学生的导师 / 教师名下启用学生数。"""

    user: User
    teacher: User | None
    student_count: int


async def list_users(
    session: AsyncSession,
    *,
    role: str | None,
    is_active: bool | None,
    q: str | None,
    offset: int,
    limit: int,
) -> tuple[int, list[AdminUserRow]]:
    offset, limit = normalize(offset, limit)
    conditions = [col(User.role).in_(_MANAGED_ROLES)]  # 管理员永不出现在列表
    if role is not None:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active == is_active)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        conditions.append(or_(col(User.username).ilike(pattern), col(User.name).ilike(pattern)))

    total = (await session.exec(select(func.count()).select_from(User).where(*conditions))).one()
    users = (
        await session.exec(
            select(User)
            .where(*conditions)
            .order_by(col(User.created_at).desc(), col(User.id).desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    teacher_ids = sorted({user.teacher_id for user in users if user.teacher_id is not None})
    teacher_map = await _teachers_map(session, teacher_ids)
    count_map = await _student_count_map(
        session, [user.id for user in users if user.id is not None]
    )

    items: list[AdminUserRow] = []
    for user in users:
        teacher = teacher_map.get(user.teacher_id) if user.teacher_id is not None else None
        count = count_map.get(user.id, 0) if user.id is not None else 0
        items.append(AdminUserRow(user=user, teacher=teacher, student_count=count))
    return total, items


async def create_user(
    session: AsyncSession,
    *,
    role: str,
    username: str,
    name: str,
    major: str | None,
    teacher_id: int | None,
) -> AdminUserRow:
    if role not in _MANAGED_ROLES:
        raise InvalidActionError("only student or teacher can be created", code="invalid_fields")
    if role == "teacher" and (major is not None or teacher_id is not None):
        raise InvalidActionError("teachers have no major/teacher field", code="invalid_fields")
    if role == "student" and teacher_id is not None:
        await _ensure_teacher(session, teacher_id)
    user = await users_service.create_user(
        session,
        username=username,
        password=users_service.INITIAL_PASSWORD,
        name=name,
        role=role,
        must_change_password=True,
        major=major if role == "student" else None,
        teacher_id=teacher_id if role == "student" else None,
    )
    return await _row_for(session, user)


async def update_user(
    session: AsyncSession, *, target_id: int, fields: dict[str, Any]
) -> AdminUserRow:
    """字段白名单：学生 name/major/teacher_id；教师仅 name。"""
    user = await _load_managed_user(session, target_id)
    allowed = _TEACHER_FIELDS if user.role == "teacher" else _STUDENT_FIELDS
    illegal = set(fields) - allowed
    if illegal:
        raise InvalidActionError(
            f"fields not allowed for {user.role}: {sorted(illegal)}", code="invalid_fields"
        )
    if "name" in fields and not fields["name"]:
        raise InvalidActionError("name cannot be empty", code="invalid_fields")
    if "teacher_id" in fields and fields["teacher_id"] is not None:
        await _ensure_teacher(session, fields["teacher_id"])
    for field, value in fields.items():
        setattr(user, field, value)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return await _row_for(session, user)


async def set_active(session: AsyncSession, *, target_id: int, is_active: bool) -> AdminUserRow:
    user = await _load_managed_user(session, target_id)
    user.is_active = is_active
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return await _row_for(session, user)


async def reset_password(session: AsyncSession, *, target_id: int) -> None:
    user = await _load_managed_user(session, target_id)
    user.password_hash = hash_password(users_service.INITIAL_PASSWORD)
    user.must_change_password = True
    session.add(user)
    await session.commit()


async def list_teacher_options(session: AsyncSession, *, q: str | None) -> list[User]:
    conditions = [User.role == "teacher", User.is_active]
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        conditions.append(or_(col(User.username).ilike(pattern), col(User.name).ilike(pattern)))
    return list(
        (
            await session.exec(
                select(User).where(*conditions).order_by(col(User.username)).limit(50)
            )
        ).all()
    )


async def _load_managed_user(session: AsyncSession, target_id: int) -> User:
    user = await session.get(User, target_id)
    if user is None:
        raise NotFoundError(f"user {target_id} not found")
    if user.role not in _MANAGED_ROLES:
        raise InvalidActionError("admin accounts are immutable", code="admin_immutable")
    return user


async def _ensure_teacher(session: AsyncSession, teacher_id: int) -> User:
    teacher = await session.get(User, teacher_id)
    if teacher is None or teacher.role != "teacher" or not teacher.is_active:
        raise InvalidActionError(
            f"teacher {teacher_id} not found or disabled", code="teacher_not_found"
        )
    return teacher


async def _row_for(session: AsyncSession, user: User) -> AdminUserRow:
    teacher = None
    if user.role == "student" and user.teacher_id is not None:
        teacher = await session.get(User, user.teacher_id)
    count = 0
    if user.role == "teacher" and user.id is not None:
        count = (
            await session.exec(
                select(func.count())
                .select_from(User)
                .where(User.role == "student", User.is_active, User.teacher_id == user.id)
            )
        ).one()
    return AdminUserRow(user=user, teacher=teacher, student_count=count)


async def _teachers_map(session: AsyncSession, teacher_ids: list[int]) -> dict[int, User]:
    if not teacher_ids:
        return {}
    rows = (await session.exec(select(User).where(col(User.id).in_(teacher_ids)))).all()
    return {user.id: user for user in rows if user.id is not None}


async def _student_count_map(session: AsyncSession, teacher_ids: list[int]) -> dict[int, int]:
    if not teacher_ids:
        return {}
    rows = (
        await session.exec(
            select(col(User.teacher_id), func.count())
            .where(
                User.role == "student",
                User.is_active,
                col(User.teacher_id).in_(teacher_ids),
            )
            .group_by(col(User.teacher_id))
        )
    ).all()
    return {teacher_id: count for teacher_id, count in rows if teacher_id is not None}
