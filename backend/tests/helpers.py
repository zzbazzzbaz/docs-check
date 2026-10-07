"""测试共享工具：建号 / 登录（后续里程碑继续复用）。"""

import httpx
from sqlmodel.ext.asyncio.session import AsyncSession

from app.infrastructure.db.models.user import User
from app.services.users import users_service

PASSWORD = "secret123"


async def make_user(
    session: AsyncSession,
    username: str,
    *,
    role: str = "student",
    password: str = PASSWORD,
    name: str = "",
    must_change_password: bool = False,
    is_active: bool = True,
) -> User:
    user = await users_service.create_user(
        session,
        username=username,
        password=password,
        name=name,
        role=role,
        must_change_password=must_change_password,
    )
    if not is_active:
        user.is_active = False
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def login(
    client: httpx.AsyncClient, username: str, password: str = PASSWORD
) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


async def auth_headers(
    client: httpx.AsyncClient, username: str, password: str = PASSWORD
) -> dict[str, str]:
    r = await login(client, username, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
