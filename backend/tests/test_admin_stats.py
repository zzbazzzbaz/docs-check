"""管理端仪表盘统计：口径（启用学生/教师、全部提交）与权限。"""

from tests.helpers import auth_headers, make_user, upload_docx


async def test_stats_counts_and_access(client, session, storage):
    await make_user(session, "admin910", role="admin")
    t1 = await make_user(session, "t7101", role="teacher", name="李老师")
    await make_user(session, "t7102", role="teacher", name="王老师", is_active=False)
    s1 = await make_user(session, "2209100101", name="张三")
    s1.teacher_id = t1.id
    session.add(s1)
    await session.commit()
    await make_user(session, "2209100102", name="李四", is_active=False)

    admin_headers = await auth_headers(client, "admin910")

    # 初始：启用学生 1、启用教师 1、提交 0（禁用账号不计）
    r = await client.get("/api/v1/admin/stats", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"student_count": 1, "teacher_count": 1, "submission_count": 0}

    # 一条提交（不论状态）都计入
    student_headers = await auth_headers(client, "2209100101")
    await upload_docx(client, storage, student_headers, filename="论文初稿.docx")

    r = await client.get("/api/v1/admin/stats", headers=admin_headers)
    assert r.json()["submission_count"] == 1

    # 学生与教师无权访问
    r = await client.get("/api/v1/admin/stats", headers=student_headers)
    assert r.status_code == 403
    teacher_headers = await auth_headers(client, "t7101")
    r = await client.get("/api/v1/admin/stats", headers=teacher_headers)
    assert r.status_code == 403
