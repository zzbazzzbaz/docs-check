"""自助改密与强制改密门禁。"""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import CurrentStudentDep, get_session
from app.api.error_handlers import register_error_handlers
from app.core.config import get_settings
from app.core.security import create_access_token
from app.services.users import users_service
from tests.helpers import PASSWORD, auth_headers, login, make_user


async def test_change_password_flow(client, session):
    await make_user(session, "alice", must_change_password=True)
    headers = await auth_headers(client, "alice")

    # 宽依赖：未改密也能查看本人信息
    r = await client.get("/api/v1/users/me", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is True

    r = await client.post(
        "/api/v1/users/me/password",
        json={"old_password": PASSWORD, "new_password": "newpass123"},
        headers=headers,
    )
    assert r.status_code == 204, r.text

    # 旧密码失效、新密码可登录、标志已清除
    assert (await login(client, "alice", PASSWORD)).status_code == 401
    headers2 = await auth_headers(client, "alice", "newpass123")
    r = await client.get("/api/v1/users/me", headers=headers2)
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is False


async def test_change_password_wrong_old(client, session):
    await make_user(session, "bob")
    headers = await auth_headers(client, "bob")

    r = await client.post(
        "/api/v1/users/me/password",
        json={"old_password": "wrong-pass", "new_password": "newpass123"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "old_password_incorrect"


async def test_change_password_unchanged(client, session):
    await make_user(session, "carol")
    headers = await auth_headers(client, "carol")

    r = await client.post(
        "/api/v1/users/me/password",
        json={"old_password": PASSWORD, "new_password": PASSWORD},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "password_unchanged"


async def test_password_gate_on_ready_dependency(session):
    """CurrentStudentDep 门禁：未改密 403 password_required_change，改密后放行。

    真实业务路由（/submissions）在 M6 挂上后再补一条端到端用例。
    """
    user = await make_user(session, "gate", must_change_password=True)
    token = create_access_token(
        subject=str(user.id),
        secret=get_settings().jwt_secret,
        expires_minutes=5,
    )
    headers = {"Authorization": f"Bearer {token}"}

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/protected")
    async def protected(_me: CurrentStudentDep) -> dict[str, bool]:
        return {"ok": True}

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/protected", headers=headers)
        assert r.status_code == 403, r.text
        assert r.json()["code"] == "password_required_change"

        await users_service.change_password(
            session, user=user, old_password=PASSWORD, new_password="newpass123"
        )

        r = await c.get("/protected", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}
