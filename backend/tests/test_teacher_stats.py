"""教师端统计接口：口径（启用学生 / 任意状态提交 / 仅成功序列）、50 点上限与权限。"""

from datetime import UTC, datetime, timedelta

from app.infrastructure.db.models.submission import Submission
from tests.helpers import auth_headers, make_user

BASE = datetime(2026, 10, 7, 8, 0, 0, tzinfo=UTC)


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _submission(
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
    return Submission(
        student_id=student_id,
        original_filename="论文.docx",
        status=status,
        created_at=created_at,
        updated_at=created_at,
        fail_count=fail,
        undetermined_count=undetermined,
        not_run_count=not_run,
        unrecognised_count=unrecognised,
    )


async def test_stats_counts_and_series_scope(client, session):
    t1 = await make_user(session, "t8101", role="teacher", name="李老师")
    t2 = await make_user(session, "t8102", role="teacher", name="王老师")
    await make_user(session, "t8103", role="teacher", name="空老师")
    s1 = await make_user(session, "2208100001", name="张三")
    s2 = await make_user(session, "2208100002", name="李四")
    s3 = await make_user(session, "2208100003", name="王五")
    disabled = await make_user(session, "2208100005", name="钱七", is_active=False)
    s1.teacher_id = t1.id
    s2.teacher_id = t1.id
    s3.teacher_id = t2.id
    disabled.teacher_id = t1.id
    session.add_all([s1, s2, s3, disabled])
    await session.commit()

    # s1：成功(早) / 失败(中) / 成功(晚)；s2：只有失败；s3：成功；禁用学生：成功
    session.add_all(
        [
            _submission(s1, status="success", created_at=BASE, fail=5),
            _submission(s1, status="failed", created_at=BASE + timedelta(minutes=1)),
            _submission(
                s1,
                status="success",
                created_at=BASE + timedelta(minutes=2),
                fail=2,
                undetermined=1,
            ),
            _submission(s2, status="failed", created_at=BASE + timedelta(minutes=3)),
            _submission(s3, status="success", created_at=BASE + timedelta(minutes=4), fail=9),
            _submission(disabled, status="success", created_at=BASE + timedelta(minutes=5), fail=7),
        ]
    )
    await session.commit()

    r = await client.get("/api/v1/students/stats", headers=await auth_headers(client, "t8101"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student_count"] == 2  # 只含名下启用学生（禁用/他人的不计）
    assert body["submitted_count"] == 2  # s2 只有失败也算提交过
    assert len(body["series"]) == 1  # 无成功提交的学生不进序列
    series = body["series"][0]
    assert (series["student_id"], series["username"], series["name"]) == (
        s1.id,
        "2208100001",
        "张三",
    )
    points = series["points"]
    assert [point["counts"] for point in points] == [
        {"fail": 5, "undetermined": 0, "not_run": 0, "unrecognised": 0},
        {"fail": 2, "undetermined": 1, "not_run": 0, "unrecognised": 0},
    ]
    assert _dt(points[0]["created_at"]) == BASE
    assert _dt(points[1]["created_at"]) == BASE + timedelta(minutes=2)

    # 另一教师只看自己名下；无学生教师返回空
    body2 = (
        await client.get("/api/v1/students/stats", headers=await auth_headers(client, "t8102"))
    ).json()
    assert body2["student_count"] == 1
    assert body2["submitted_count"] == 1
    assert [item["student_id"] for item in body2["series"]] == [s3.id]

    body3 = (
        await client.get("/api/v1/students/stats", headers=await auth_headers(client, "t8103"))
    ).json()
    assert body3 == {"student_count": 0, "submitted_count": 0, "series": []}


async def test_stats_series_cap_keeps_latest_50(client, session):
    teacher = await make_user(session, "t8104", role="teacher", name="陈老师")
    student = await make_user(session, "2208100010", name="孙同学")
    student.teacher_id = teacher.id
    session.add(student)
    await session.commit()

    session.add_all(
        [_submission(student, created_at=BASE + timedelta(minutes=i), fail=i) for i in range(55)]
    )
    await session.commit()

    r = await client.get("/api/v1/students/stats", headers=await auth_headers(client, "t8104"))
    assert r.status_code == 200, r.text
    points = r.json()["series"][0]["points"]
    assert len(points) == 50
    # 最近 50 条 = 第 6~55 条（fail 5..54），时间正序
    assert [point["counts"]["fail"] for point in points] == list(range(5, 55))
    assert _dt(points[0]["created_at"]) == BASE + timedelta(minutes=5)
    assert _dt(points[-1]["created_at"]) == BASE + timedelta(minutes=54)


async def test_stats_permissions(client, session):
    await make_user(session, "t8105", role="teacher", name="周老师")
    await make_user(session, "2208100020", name="吴同学")

    r = await client.get("/api/v1/students/stats")
    assert r.status_code == 401

    student_headers = await auth_headers(client, "2208100020")
    r = await client.get("/api/v1/students/stats", headers=student_headers)
    assert r.status_code == 403
