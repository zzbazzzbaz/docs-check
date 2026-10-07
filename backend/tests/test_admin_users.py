"""管理端用户管理：列表筛选、新建、编辑、禁用/启用、重置密码、教师下拉、越权。"""

from tests.helpers import PASSWORD, auth_headers, login, make_user


async def _admin_headers(client, session, username: str = "admin900") -> dict[str, str]:
    await make_user(session, username, role="admin", name="管理员")
    return await auth_headers(client, username)


async def test_list_users_filters_and_counts(client, session):
    await make_user(session, "admin901", role="admin")
    t1 = await make_user(session, "t7001", role="teacher", name="李老师")
    await make_user(session, "t7002", role="teacher", name="王老师", is_active=False)
    s1 = await make_user(session, "2209100001", name="张三")
    s1.major = "物联网工程"
    s1.teacher_id = t1.id
    await make_user(session, "2209100002", name="李四")  # 无导师
    s3 = await make_user(session, "2209100003", name="王五", is_active=False)
    s3.teacher_id = t1.id
    for user in (s1, s3):
        session.add(user)
    await session.commit()
    headers = await auth_headers(client, "admin901")

    r = await client.get("/api/v1/admin/users", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 5  # 2 教师 + 3 学生；管理员不出现在列表
    assert {item["role"] for item in body["items"]} == {"student", "teacher"}

    t1_item = next(item for item in body["items"] if item["username"] == "t7001")
    assert t1_item["student_count"] == 1  # 只数启用学生（s3 禁用不计）
    s1_item = next(item for item in body["items"] if item["username"] == "2209100001")
    assert s1_item["teacher"] == {"id": t1.id, "name": "李老师"}
    assert s1_item["major"] == "物联网工程"

    r = await client.get("/api/v1/admin/users?role=student", headers=headers)
    assert r.json()["total"] == 3

    r = await client.get("/api/v1/admin/users?role=teacher", headers=headers)
    assert r.json()["total"] == 2

    r = await client.get("/api/v1/admin/users?is_active=false", headers=headers)
    body = r.json()
    assert body["total"] == 2  # t2 + s3
    assert {item["username"] for item in body["items"]} == {"t7002", "2209100003"}

    r = await client.get("/api/v1/admin/users?q=张", headers=headers)
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["username"] == "2209100001"

    r = await client.get("/api/v1/admin/users?role=student&q=0002", headers=headers)
    assert r.json()["total"] == 1


async def test_create_student_and_teacher(client, session):
    headers = await _admin_headers(client, session)
    teacher = await make_user(session, "t7003", role="teacher", name="陈老师")

    r = await client.post(
        "/api/v1/admin/users",
        json={
            "role": "student",
            "username": "2209100010",
            "name": "新学生",
            "major": "软件工程",
            "teacher_id": teacher.id,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "student"
    assert body["teacher"] == {"id": teacher.id, "name": "陈老师"}
    assert body["is_active"] is True

    # 初始密码 123456 + 强制改密
    r = await login(client, "2209100010", "123456")
    assert r.status_code == 200, r.text
    student_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = await client.get("/api/v1/users/me", headers=student_headers)
    assert r.json()["must_change_password"] is True

    # 重复账号 → 409 username_taken
    r = await client.post(
        "/api/v1/admin/users",
        json={"role": "student", "username": "2209100010", "name": "重复"},
        headers=headers,
    )
    assert r.status_code == 409
    assert r.json()["code"] == "username_taken"

    # 新建教师：传 major → 400 invalid_fields；正常创建 → 201
    r = await client.post(
        "/api/v1/admin/users",
        json={"role": "teacher", "username": "t7004", "name": "新老师", "major": "非法"},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_fields"

    r = await client.post(
        "/api/v1/admin/users",
        json={"role": "teacher", "username": "t7004", "name": "新老师"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "teacher"


async def test_create_student_teacher_validation(client, session):
    headers = await _admin_headers(client, session)
    disabled = await make_user(session, "t7005", role="teacher", name="禁用老师", is_active=False)

    r = await client.post(
        "/api/v1/admin/users",
        json={"role": "student", "username": "2209100011", "name": "甲", "teacher_id": 999999},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["code"] == "teacher_not_found"

    r = await client.post(
        "/api/v1/admin/users",
        json={"role": "student", "username": "2209100012", "name": "乙", "teacher_id": disabled.id},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["code"] == "teacher_not_found"

    # 非学生/教师角色由 schema 拦 → 422
    r = await client.post(
        "/api/v1/admin/users",
        json={"role": "admin", "username": "hacker1", "name": "x"},
        headers=headers,
    )
    assert r.status_code == 422


async def test_update_user_fields(client, session):
    headers = await _admin_headers(client, session)
    admin = await make_user(session, "admin902", role="admin")
    t1 = await make_user(session, "t7006", role="teacher", name="李老师")
    t2 = await make_user(session, "t7007", role="teacher", name="王老师")
    student = await make_user(session, "2209100020", name="旧名")
    student.teacher_id = t1.id
    session.add(student)
    await session.commit()

    # 学生：改名 + 专业 + 换导师
    r = await client.patch(
        f"/api/v1/admin/users/{student.id}",
        json={"name": "新名", "major": "网络工程", "teacher_id": t2.id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "新名"
    assert body["major"] == "网络工程"
    assert body["teacher"] == {"id": t2.id, "name": "王老师"}

    # teacher_id: null = 取消分配
    r = await client.patch(
        f"/api/v1/admin/users/{student.id}", json={"teacher_id": None}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["teacher"] is None

    # 教师：仅姓名
    r = await client.patch(f"/api/v1/admin/users/{t1.id}", json={"name": "李改名"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "李改名"

    r = await client.patch(f"/api/v1/admin/users/{t1.id}", json={"major": "非法"}, headers=headers)
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_fields"

    # 账号/角色不可改（extra=forbid → 422）
    r = await client.patch(
        f"/api/v1/admin/users/{student.id}", json={"username": "hack"}, headers=headers
    )
    assert r.status_code == 422

    # 操作管理员 → 400 admin_immutable；不存在 → 404
    r = await client.patch(f"/api/v1/admin/users/{admin.id}", json={"name": "x"}, headers=headers)
    assert r.status_code == 400
    assert r.json()["code"] == "admin_immutable"

    r = await client.patch("/api/v1/admin/users/999999", json={"name": "x"}, headers=headers)
    assert r.status_code == 404


async def test_disable_and_enable_user(client, session):
    headers = await _admin_headers(client, session)
    student = await make_user(session, "2209100030", name="要禁用")

    r = await client.patch(
        f"/api/v1/admin/users/{student.id}/status", json={"is_active": False}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False

    # 禁用后无法登录
    assert (await login(client, "2209100030")).status_code == 403

    # 启用恢复
    r = await client.patch(
        f"/api/v1/admin/users/{student.id}/status", json={"is_active": True}, headers=headers
    )
    assert r.status_code == 200
    assert (await login(client, "2209100030")).status_code == 200

    # 管理员自身不可禁用
    admin = await make_user(session, "admin903", role="admin")
    r = await client.patch(
        f"/api/v1/admin/users/{admin.id}/status", json={"is_active": False}, headers=headers
    )
    assert r.status_code == 400
    assert r.json()["code"] == "admin_immutable"


async def test_reset_password(client, session):
    headers = await _admin_headers(client, session)
    student = await make_user(session, "2209100040", name="忘密码")

    r = await client.post(f"/api/v1/admin/users/{student.id}/reset-password", headers=headers)
    assert r.status_code == 204, r.text

    assert (await login(client, "2209100040", PASSWORD)).status_code == 401  # 旧密码失效
    r = await login(client, "2209100040", "123456")
    assert r.status_code == 200, r.text
    me_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = await client.get("/api/v1/users/me", headers=me_headers)
    assert r.json()["must_change_password"] is True


async def test_teacher_options(client, session):
    headers = await _admin_headers(client, session)
    await make_user(session, "t7008", role="teacher", name="李老师")
    await make_user(session, "t7009", role="teacher", name="王老师")
    await make_user(session, "t7010", role="teacher", name="禁用老师", is_active=False)

    r = await client.get("/api/v1/admin/teachers/options", headers=headers)
    assert r.status_code == 200, r.text
    assert [item["username"] for item in r.json()] == ["t7008", "t7009"]

    r = await client.get("/api/v1/admin/teachers/options?q=李", headers=headers)
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "李老师"


async def test_admin_endpoints_require_admin(client, session):
    await make_user(session, "2209100050", name="学生")
    await make_user(session, "t7011", role="teacher")
    h_student = await auth_headers(client, "2209100050")
    h_teacher = await auth_headers(client, "t7011")

    for headers in (h_student, h_teacher):
        r = await client.get("/api/v1/admin/users", headers=headers)
        assert r.status_code == 403
        assert r.json()["code"] == "forbidden"

    r = await client.get("/api/v1/admin/users")
    assert r.status_code == 401
