"""登录与 /users/me：启用校验、导师信息、禁用即时生效。"""

from tests.helpers import PASSWORD, auth_headers, login, make_user


async def test_login_and_me_student(client, session):
    teacher = await make_user(session, "t1001", role="teacher", name="李老师")
    student = await make_user(session, "2206118101", name="张三")
    student.major = "物联网工程"
    student.teacher_id = teacher.id
    session.add(student)
    await session.commit()

    r = await login(client, "2206118101")
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.get("/api/v1/users/me", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["username"] == "2206118101"
    assert body["name"] == "张三"
    assert body["role"] == "student"
    assert body["major"] == "物联网工程"
    assert body["teacher"] == {"id": teacher.id, "name": "李老师"}
    assert body["must_change_password"] is False
    assert "password_hash" not in body


async def test_teacher_me_has_no_major_or_teacher(client, session):
    await make_user(session, "t2002", role="teacher", name="王老师")
    headers = await auth_headers(client, "t2002")

    r = await client.get("/api/v1/users/me", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "teacher"
    assert body["major"] is None
    assert body["teacher"] is None


async def test_login_wrong_password(client, session):
    await make_user(session, "alice")
    r = await login(client, "alice", "wrong-password")
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "invalid_credentials"


async def test_login_unknown_user(client):
    r = await login(client, "nobody")
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "invalid_credentials"


async def test_login_disabled_account(client, session):
    await make_user(session, "bob", is_active=False)
    r = await login(client, "bob")
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "account_disabled"


async def test_me_requires_token(client):
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 401


async def test_disabling_account_invalidates_existing_token(client, session):
    user = await make_user(session, "carol")
    headers = await auth_headers(client, "carol")

    user.is_active = False
    session.add(user)
    await session.commit()

    r = await client.get("/api/v1/users/me", headers=headers)
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "account_disabled"


async def test_must_change_password_visible_in_me(client, session):
    await make_user(session, "dave", must_change_password=True)
    headers = await auth_headers(client, "dave")

    r = await client.get("/api/v1/users/me", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is True


async def test_password_constant_matches_spec():
    from app.services.users.users_service import INITIAL_PASSWORD

    assert PASSWORD != INITIAL_PASSWORD
    assert INITIAL_PASSWORD == "123456"
