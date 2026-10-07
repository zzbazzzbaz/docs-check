"""学生端提交接口：上传入队、轮询状态、下载、列表分页、鉴权门禁。"""

from types import SimpleNamespace

from tests.factories import corrupt_docx_bytes, minimal_docx_bytes
from tests.helpers import auth_headers, make_user

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ZERO_COUNTS = {"fail": 0, "undetermined": 0, "not_run": 0, "unrecognised": 0}


def _files(data: bytes, filename: str = "论文初稿.docx") -> dict:
    return {"file": (filename, data, DOCX_MIME)}


async def test_upload_pending_then_success(client, session, worker, storage):
    await make_user(session, "2206118101", name="张三")
    headers = await auth_headers(client, "2206118101")
    data = minimal_docx_bytes()

    # 上传 → 202 pending；文件已落盘
    r = await client.post("/api/v1/submissions", files=_files(data), headers=headers)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["counts"] == ZERO_COUNTS
    assert body["by_scope"] is None
    assert body["ruleset_version"] is None
    assert body["sequence"] == 1
    submission_id = body["id"]
    assert (storage.submission_dir(submission_id) / "original.docx").is_file()

    # 未处理：详情 pending；原始可下载；标注 404
    r = await client.get(f"/api/v1/submissions/{submission_id}", headers=headers)
    assert r.json()["status"] == "pending"
    r = await client.get(f"/api/v1/submissions/{submission_id}/original", headers=headers)
    assert r.status_code == 200, r.text
    assert r.content == data
    r = await client.get(f"/api/v1/submissions/{submission_id}/marked", headers=headers)
    assert r.status_code == 404

    # worker 处理 → success
    assert await worker.process_next() is True
    r = await client.get(f"/api/v1/submissions/{submission_id}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["ruleset_version"]
    assert body["by_scope"]
    assert body["error_message"] is None

    # 两个文件都可下载
    r = await client.get(f"/api/v1/submissions/{submission_id}/original", headers=headers)
    assert r.status_code == 200
    r = await client.get(f"/api/v1/submissions/{submission_id}/marked", headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == DOCX_MIME
    assert r.content[:2] == b"PK"


async def test_corrupt_docx_becomes_failed_and_cleans_files(client, session, worker, storage):
    await make_user(session, "baduser")
    headers = await auth_headers(client, "baduser")

    r = await client.post(
        "/api/v1/submissions", files=_files(corrupt_docx_bytes(), "坏文件.docx"), headers=headers
    )
    assert r.status_code == 202, r.text
    submission_id = r.json()["id"]
    assert storage.submission_dir(submission_id).exists()

    assert await worker.process_next() is True

    r = await client.get(f"/api/v1/submissions/{submission_id}", headers=headers)
    body = r.json()
    assert body["status"] == "failed"
    assert body["error_message"]  # 引擎中文原因
    assert body["counts"] == ZERO_COUNTS
    assert body["by_scope"] is None
    assert not storage.submission_dir(submission_id).exists()

    for suffix in ("original", "marked"):
        r = await client.get(f"/api/v1/submissions/{submission_id}/{suffix}", headers=headers)
        assert r.status_code == 404, suffix


async def test_upload_rejects_non_docx(client, session):
    await make_user(session, "v001")
    headers = await auth_headers(client, "v001")

    r = await client.post("/api/v1/submissions", files=_files(b"x", "论文.pdf"), headers=headers)
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "unsupported_file_type"


async def test_upload_rejects_empty_file(client, session):
    await make_user(session, "v002")
    headers = await auth_headers(client, "v002")

    r = await client.post("/api/v1/submissions", files=_files(b"", "空.docx"), headers=headers)
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "empty_file"


async def test_upload_rejects_too_large(client, session, monkeypatch):
    from app.api.routes.submissions import submissions as route_module

    await make_user(session, "v003")
    headers = await auth_headers(client, "v003")
    fake_settings = SimpleNamespace(upload_max_bytes=100)
    monkeypatch.setattr(route_module, "get_settings", lambda: fake_settings)

    r = await client.post(
        "/api/v1/submissions", files=_files(b"x" * 200, "大文件.docx"), headers=headers
    )
    assert r.status_code == 413, r.text
    assert r.json()["code"] == "file_too_large"


async def test_list_only_own_submissions_desc(client, session):
    await make_user(session, "lister")
    await make_user(session, "other")
    h1 = await auth_headers(client, "lister")
    h2 = await auth_headers(client, "other")

    ids = []
    for _ in range(3):
        r = await client.post("/api/v1/submissions", files=_files(minimal_docx_bytes()), headers=h1)
        assert r.status_code == 202
        ids.append(r.json()["id"])
    await client.post("/api/v1/submissions", files=_files(minimal_docx_bytes()), headers=h2)

    r = await client.get("/api/v1/submissions?offset=0&limit=2", headers=h1)
    body = r.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [ids[2], ids[1]]
    assert body["offset"] == 0
    assert body["limit"] == 2

    # sequence 按本人提交正序编号
    for index, sid in enumerate(ids, start=1):
        r = await client.get(f"/api/v1/submissions/{sid}", headers=h1)
        assert r.json()["sequence"] == index


async def test_other_student_cannot_access(client, session):
    await make_user(session, "owner")
    await make_user(session, "intruder")
    h_owner = await auth_headers(client, "owner")
    h_intruder = await auth_headers(client, "intruder")

    r = await client.post(
        "/api/v1/submissions", files=_files(minimal_docx_bytes()), headers=h_owner
    )
    submission_id = r.json()["id"]

    for path in (
        f"/api/v1/submissions/{submission_id}",
        f"/api/v1/submissions/{submission_id}/original",
        f"/api/v1/submissions/{submission_id}/marked",
    ):
        r = await client.get(path, headers=h_intruder)
        assert r.status_code == 403, (path, r.text)
        assert r.json()["code"] == "forbidden"

    r = await client.get("/api/v1/submissions/999999", headers=h_owner)
    assert r.status_code == 404


async def test_admin_cannot_access_submissions(client, session):
    await make_user(session, "owner2")
    await make_user(session, "admin1", role="admin")
    h_owner = await auth_headers(client, "owner2")
    h_admin = await auth_headers(client, "admin1")

    r = await client.post(
        "/api/v1/submissions", files=_files(minimal_docx_bytes()), headers=h_owner
    )
    submission_id = r.json()["id"]

    r = await client.get(f"/api/v1/submissions/{submission_id}", headers=h_admin)
    assert r.status_code == 403
    r = await client.get(f"/api/v1/submissions/{submission_id}/marked", headers=h_admin)
    assert r.status_code == 403


async def test_upload_requires_student_role(client, session):
    await make_user(session, "t3001", role="teacher")
    headers = await auth_headers(client, "t3001")

    r = await client.post(
        "/api/v1/submissions", files=_files(minimal_docx_bytes()), headers=headers
    )
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden"


async def test_password_gate_blocks_submission_routes(client, session):
    await make_user(session, "locked", must_change_password=True)
    headers = await auth_headers(client, "locked")

    r = await client.get("/api/v1/submissions", headers=headers)
    assert r.status_code == 403
    assert r.json()["code"] == "password_required_change"

    r = await client.post(
        "/api/v1/submissions", files=_files(minimal_docx_bytes()), headers=headers
    )
    assert r.status_code == 403
    assert r.json()["code"] == "password_required_change"
