from fastapi import APIRouter

from app.api.dependencies import SessionDep
from app.api.schemas.auth import LoginRequest, TokenResponse
from app.core.config import get_settings
from app.services.auth import auth_service

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: SessionDep) -> TokenResponse:
    token = await auth_service.login(
        session,
        username=body.username,
        password=body.password,
        settings=get_settings(),
    )
    return TokenResponse(access_token=token)
