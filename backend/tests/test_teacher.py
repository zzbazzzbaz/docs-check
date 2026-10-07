"""教师视角：名下学生列表聚合、搜索分页、学生详情/提交列表、下载鉴权。"""

from datetime import UTC, datetime, timedelta

from app.infrastructure.db.models.submission import Submission
from tests.factories import minimal_docx_bytes
from tests.helpers import auth_headers, make_user

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
BASE = datetime(2026, 10, 7, 8, 0, 0, tzinfo=UTC)


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


async def _add_submission(
    session,
    student,
    *,
    status: str = "success",
    created_at: datetime = BASE,
    fail: int = 0,
    undetermined: int = 0,
    not_run: int = 0,
    unrecognised: int = 0,
) -> Submission:
    student_id = student.id
    assert student_id is not None
    submission = Submission(
        student_id=student_id,
        original_filename="旧稿.docx",
        status=status,
        created_at=created_at,
        updated_at=created_at,
        fail_count=fail,
        undetermined_count=undetermined,
        not_run_count=not_run,
        unrecognised_count=unrecognised,
    )
    session.add(submission)
    await session.commit()
    return submission


async def _aggregate_setup(session):
    t1 = await make_user(session, "t5001", role="teacher", name="李老师")
    t2 = await make_user(session, "t5002", role="teacher", name="王老师")
    s1 = await make_user(session, "2207100001", name="张三")
    s1.major = "物联网工程"
    s1.teacher_id = t1.id
    s2 = await make_user(session, "2207100002", name="李四")
    s2.teacher_id = t1.id
    s3 = await make_user(session, "2207100003", name="王五")
    s3.teacher_id = t2.id
    await make_user(session, "2207100004", name="赵六")  # 无导师
    s5 = await make_user(session, "2207100005", name="钱七", is_active=False)
    s5.teacher_id = t1.id
    for user in (s1, s2, s3, s5):
        session.add(user)
    await session.commit()

    # s1：成功(早) / 失败(中) / 成功(晚)；s2：只有失败
    await _add_submission(session, s1, status="success", created_at=BASE, fail=5)
    await _add_submission(session, s1, status="failed", created_at=BASE + timedelta(minutes=1))
    await _add_submission(
        session,
        s1,
        status="success",
        created_at=BASE + timedelta(minutes=2),
        fail=2,
        undetermined=1,
    )
    await _add_submission(session, s2, status="failed", created_at=BASE + timedelta(minutes=3))
    return t1, t2, s1, s2, s3, s5


async def test_student_list_aggregates_and_scope(client, session):
    t1, _t2, s1, s2, _s3, _s5 = await _aggregate_setup(session)
    headers = await auth_headers(client, "t5001")

    r = await client.get("/api/v1/students", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2  # 只含名下启用学生（t2 的、无导师的、禁用的都不在）
    assert [item["username"] for item in body["items"]] == ["2207100001", "2207100002"]

    first, second = body["items"]
    assert first["id"] == s1.id
    assert first["major"] == "物联网工程"
    assert first["success_count"] == 2  # 只数成功
    assert _dt(first["latest_submitted_at"]) == BASE + timedelta(minutes=2)
    assert first["latest_counts"] == {
        "fail": 2,
        "undetermined": 1,
        "not_run": 0,
        "unrecognised": 0,
    }

    assert second["id"] == s2.id
    assert second["success_count"] == 0
    assert _dt(second["latest_submitted_at"]) == BASE + timedelta(minutes=3)
    assert second["latest_counts"] is None  # 无成功提交


async def test_student_list_search_and_pagination(client, session):
    await _aggregate_setup(session)
    headers = await auth_headers(client, "t5001")

    r = await client.get("/api/v1/students?q=张", headers=headers)
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["name"] == "张三"

    r = await client.get("/api/v1/students?q=0002", headers=headers)
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["name"] == "李四"

    r = await client.get("/api/v1/students?offset=0&limit=1", headers=headers)
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["limit"] == 1


async def test_student_detail_authz(client, session):
    _t1, _t2, s1, _s2, s3, s5 = await _aggregate_setup(session)
    h_t1 = await auth_headers(client, "t5001")
    h_t2 = await auth_headers(client, "t5002")

    r = await client.get(f"/api/v1/students/{s1.id}", headers=h_t1)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "张三"
    assert r.json()["major"] == "物联网工程"

    r = await client.get(f"/api/v1/students/{s1.id}", headers=h_t2)
    assert r.status_code == 403, r.text

    r = await client.get(f"/api/v1/students/{s3.id}", headers=h_t1)
    assert r.status_code == 403

    r = await client.get(f"/api/v1/students/{s5.id}", headers=h_t1)
    assert r.status_code == 404  # 禁用学生不可见

    r = await client.get("/api/v1/students/999999", headers=h_t1)
    assert r.status_code == 404

    # 学生访问教师接口 → 403
    h_student = await auth_headers(client, "2207100001")
    r = await client.get("/api/v1/students", headers=h_student)
    assert r.status_code == 403


async def test_student_submission_list(client, session):
    _t1, _t2, s1, _s2, _s3, _s5 = await _aggregate_setup(session)
    headers = await auth_headers(client, "t5001")

    r = await client.get(f"/api/v1/students/{s1.id}/submissions", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    statuses = [item["status"] for item in body["items"]]
    assert statuses == ["success", "failed", "success"]  # 倒序

    r2 = await client.get("/api/v1/students/999999/submissions", headers=headers)
    assert r2.status_code == 404


async def test_teacher_can_view_and_download_owned_student(client, session, worker):
    teacher = await make_user(session, "t5003", role="teacher", name="陈老师")
    student = await make_user(session, "2207100010", name="孙同学")
    student.teacher_id = teacher.id
    session.add(student)
    await session.commit()

    h_student = await auth_headers(client, "2207100010")
    r = await client.post(
        "/api/v1/submissions",
        files={"file": ("学生论文.docx", minimal_docx_bytes(), DOCX_MIME)},
        headers=h_student,
    )
    submission_id = r.json()["id"]
    assert await worker.process_next() is True

    h_teacher = await auth_headers(client, "t5003")
    r = await client.get(f"/api/v1/submissions/{submission_id}", headers=h_teacher)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "success"

    for suffix in ("original", "marked"):
        r = await client.get(f"/api/v1/submissions/{submission_id}/{suffix}", headers=h_teacher)
        assert r.status_code == 200, (suffix, r.text)


async def test_other_teacher_cannot_touch_students_submission(client, session, worker):
    teacher1 = await make_user(session, "t5004", role="teacher")
    _teacher2 = await make_user(session, "t5005", role="teacher")
    student = await make_user(session, "2207100011", name="周同学")
    student.teacher_id = teacher1.id
    session.add(student)
    await session.commit()

    h_student = await auth_headers(client, "2207100011")
    r = await client.post(
        "/api/v1/submissions",
        files={"file": ("论文.docx", minimal_docx_bytes(), DOCX_MIME)},
        headers=h_student,
    )
    submission_id = r.json()["id"]

    h_other = await auth_headers(client, "t5005")
    r = await client.get(f"/api/v1/submissions/{submission_id}", headers=h_other)
    assert r.status_code == 403
    r = await client.get(f"/api/v1/submissions/{submission_id}/original", headers=h_other)
    assert r.status_code == 403
    r = await client.get(f"/api/v1/students/{student.id}", headers=h_other)
    assert r.status_code == 403
