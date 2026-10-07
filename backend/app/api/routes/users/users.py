"""用户域接口：本人信息与自助改密（宽依赖，未改初始密码也可用）。"""

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.schemas.users import ChangePasswordRequest, MeResponse
from app.infrastructure.db.models.user import User
from app.services.users import users_service

router = APIRouter()


def _me_response(user: User, teacher: User | None) -> MeResponse:
    """ORM → 响应（model_validate 统一走 pydantic 校验）。"""
    teacher_payload = None
    if teacher is not None:
        teacher_payload = {"id": teacher.id, "name": teacher.name}
    return MeResponse.model_validate(
        {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "role": user.role,
            "major": user.major,
            "teacher": teacher_payload,
            "must_change_password": user.must_change_password,
            "created_at": user.created_at,
        }
    )


@router.get("/me", response_model=MeResponse)
async def get_me(me: CurrentUserDep, session: SessionDep) -> MeResponse:
    user, teacher = await users_service.get_me(session, user=me)
    return _me_response(user, teacher)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest, me: CurrentUserDep, session: SessionDep
) -> None:
    await users_service.change_password(
        session,
        user=me,
        old_password=body.old_password,
        new_password=body.new_password,
    )
