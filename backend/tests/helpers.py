"""测试共享工具：建号 / 登录 / 上传（后续里程碑继续复用）。"""

import httpx
from sqlmodel.ext.asyncio.session import AsyncSession

from app.infrastructure.db.models.user import User
from app.services.users import users_service
from tests.factories import minimal_docx_bytes
from tests.fakes import FakeStorage

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


async def upload_docx(
    client: httpx.AsyncClient,
    storage: FakeStorage,
    headers: dict[str, str],
    *,
    data: bytes | None = None,
    filename: str = "论文初稿.docx",
) -> int:
    """三段式上传：upload-url → 向 FakeStorage 写暂存（模拟直传）→ confirm；返回提交 id。"""
    content = minimal_docx_bytes() if data is None else data
    r = await client.post(
        "/api/v1/submissions/upload-url",
        json={"filename": filename, "size": len(content)},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    object_key = r.json()["object_key"]
    storage.write_staged(object_key, content)
    r = await client.post(
        "/api/v1/submissions",
        json={"object_key": object_key, "filename": filename},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    return int(r.json()["id"])
