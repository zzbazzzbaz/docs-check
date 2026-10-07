"""管理端：用户管理（列表/新建/编辑/禁用/重置密码）与教师下拉。"""

from typing import Literal

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentAdminDep, PageParamsDep, SessionDep
from app.api.schemas.admin_users import (
    AdminUserCreate,
    AdminUserItem,
    AdminUserStatusUpdate,
    AdminUserUpdate,
    TeacherOption,
)
from app.api.schemas.common import Page
from app.services.admin import admin_users_service
from app.services.admin.admin_users_service import AdminUserRow
from app.services.pagination import normalize

router = APIRouter()


def _item(row: AdminUserRow) -> AdminUserItem:
    user = row.user
    teacher = row.teacher
    return AdminUserItem.model_validate(
        {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "role": user.role,
            "major": user.major,
            "teacher": {"id": teacher.id, "name": teacher.name} if teacher else None,
            "student_count": row.student_count,
            "is_active": user.is_active,
            "created_at": user.created_at,
        }
    )


@router.get("/users", response_model=Page[AdminUserItem])
async def list_users(
    session: SessionDep,
    page: PageParamsDep,
    _admin: CurrentAdminDep,
    role: Literal["student", "teacher"] | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=64),
) -> Page[AdminUserItem]:
    offset, limit = normalize(*page)
    total, rows = await admin_users_service.list_users(
        session, role=role, is_active=is_active, q=q, offset=offset, limit=limit
    )
    return Page[AdminUserItem](
        total=total,
        items=[_item(row) for row in rows],
        offset=offset,
        limit=limit,
    )


@router.post("/users", response_model=AdminUserItem, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserCreate, session: SessionDep, _admin: CurrentAdminDep
) -> AdminUserItem:
    row = await admin_users_service.create_user(
        session,
        role=body.role,
        username=body.username,
        name=body.name,
        major=body.major,
        teacher_id=body.teacher_id,
    )
    return _item(row)


@router.patch("/users/{user_id}", response_model=AdminUserItem)
async def update_user(
    user_id: int,
    body: AdminUserUpdate,
    session: SessionDep,
    _admin: CurrentAdminDep,
) -> AdminUserItem:
    row = await admin_users_service.update_user(
        session, target_id=user_id, fields=body.model_dump(exclude_unset=True)
    )
    return _item(row)


@router.patch("/users/{user_id}/status", response_model=AdminUserItem)
async def set_user_status(
    user_id: int,
    body: AdminUserStatusUpdate,
    session: SessionDep,
    _admin: CurrentAdminDep,
) -> AdminUserItem:
    row = await admin_users_service.set_active(session, target_id=user_id, is_active=body.is_active)
    return _item(row)


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(user_id: int, session: SessionDep, _admin: CurrentAdminDep) -> None:
    await admin_users_service.reset_password(session, target_id=user_id)


@router.get("/teachers/options", response_model=list[TeacherOption])
async def teacher_options(
    session: SessionDep,
    _admin: CurrentAdminDep,
    q: str | None = Query(default=None, max_length=64),
) -> list[TeacherOption]:
    teachers = await admin_users_service.list_teacher_options(session, q=q)
    return [
        TeacherOption.model_validate(
            {"id": teacher.id, "username": teacher.username, "name": teacher.name}
        )
        for teacher in teachers
    ]
