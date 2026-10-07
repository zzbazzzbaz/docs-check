"""学生端提交接口：上传三段式、轮询状态、下载 307、列表分页、鉴权门禁。"""

import re
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from app.core.config import get_settings
from app.infrastructure.db.models.submission import Submission
from tests.factories import corrupt_docx_bytes, minimal_docx_bytes
from tests.helpers import auth_headers, make_user, upload_docx

ZERO_COUNTS = {"fail": 0, "undetermined": 0, "not_run": 0, "unrecognised": 0}


def _patch_settings(monkeypatch: pytest.MonkeyPatch, *, max_bytes: int) -> None:
    """把路由读到的 settings 换成小上限，方便构造「暂存超限」用例。"""
    from app.api.routes.submissions import submissions as route_module

    monkeypatch.setattr(
        route_module,
        "get_settings",
        lambda: SimpleNamespace(upload_max_bytes=max_bytes, presign_expire_seconds=600),
    )


async def test_upload_url_signs_tmp_key(client, session):
    await make_user(session, "signer")
    headers = await auth_headers(client, "signer")

    r = await client.post(
        "/api/v1/submissions/upload-url",
        json={"filename": "论文初稿.docx", "size": 1234},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert re.fullmatch(r"tmp/[0-9a-f]{32}\.docx", body["object_key"])
    assert body["upload_url"].startswith(f"https://fake-cos.example.com/{body['object_key']}?")
    assert body["expires_in"] == get_settings().presign_expire_seconds


async def test_upload_pending_then_success(client, session, worker, storage):
    await make_user(session, "2206118101", name="张三")
    headers = await auth_headers(client, "2206118101")
    data = minimal_docx_bytes()

    # 三段式确认 → 202 pending；响应形状不变
    submission_id = await upload_docx(client, storage, headers, data=data)
    key = storage.upload_keys[-1]
    uuid = key.removeprefix("tmp/").removesuffix(".docx")
    r = await client.get(f"/api/v1/submissions/{submission_id}", headers=headers)
    body = r.json()
    assert body["status"] == "pending"
    assert body["counts"] == ZERO_COUNTS
    assert body["by_scope"] is None
    assert body["ruleset_version"] is None
    assert body["sequence"] == 1

    # 转正：暂存已删、original 就位
    assert key not in storage.objects
    assert storage.objects[f"submissions/{uuid}/original.docx"] == data

    # 未处理：原始可下载（307 预签名 + 中文附件名），标注 404
    r = await client.get(f"/api/v1/submissions/{submission_id}/original", headers=headers)
    assert r.status_code == 307, r.text
    location = r.headers["location"]
    assert location.startswith(f"https://fake-cos.example.com/submissions/{uuid}/original.docx?")
    assert "filename%2A%3DUTF-8%27%27" in location
    assert quote("论文初稿.docx") in location
    r = await client.get(f"/api/v1/submissions/{submission_id}/marked", headers=headers)
    assert r.status_code == 404

    # worker 处理 → success；三件产物齐（全程 FakeStorage）
    assert await worker.process_next() is True
    r = await client.get(f"/api/v1/submissions/{submission_id}", headers=headers)
    body = r.json()
    assert body["status"] == "success"
    assert body["ruleset_version"]
    assert body["by_scope"]
    assert body["error_message"] is None
    assert storage.keys_under(f"submissions/{uuid}") == [
        f"submissions/{uuid}/issues.json",
        f"submissions/{uuid}/marked.docx",
        f"submissions/{uuid}/original.docx",
    ]

    # 标注可下载：307 + 文件名 {stem}.marked.docx
    r = await client.get(f"/api/v1/submissions/{submission_id}/marked", headers=headers)
    assert r.status_code == 307, r.text
    location = r.headers["location"]
    assert "/marked.docx?" in location
    assert quote("论文初稿.marked.docx") in location


async def test_corrupt_docx_becomes_failed_and_cleans_files(client, session, worker, storage):
    await make_user(session, "baduser")
    headers = await auth_headers(client, "baduser")

    submission_id = await upload_docx(
        client, storage, headers, data=corrupt_docx_bytes(), filename="坏文件.docx"
    )
    session.expire_all()
    submission = await session.get(Submission, submission_id)
    assert submission is not None and submission.storage_dir is not None
    assert storage.keys_under(submission.storage_dir)  # 转正后有条目

    assert await worker.process_next() is True

    r = await client.get(f"/api/v1/submissions/{submission_id}", headers=headers)
    body = r.json()
    assert body["status"] == "failed"
    assert body["error_message"]  # 引擎中文原因
    assert body["counts"] == ZERO_COUNTS
    assert body["by_scope"] is None
    assert storage.keys_under(submission.storage_dir) == []

    for suffix in ("original", "marked"):
        r = await client.get(f"/api/v1/submissions/{submission_id}/{suffix}", headers=headers)
        assert r.status_code == 404, suffix


async def test_upload_url_rejects_non_docx(client, session):
    await make_user(session, "v001")
    headers = await auth_headers(client, "v001")

    r = await client.post(
        "/api/v1/submissions/upload-url",
        json={"filename": "论文.pdf", "size": 10},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "unsupported_file_type"


async def test_upload_url_rejects_non_positive_size(client, session):
    await make_user(session, "v002")
    headers = await auth_headers(client, "v002")

    for size in (0, -1):
        r = await client.post(
            "/api/v1/submissions/upload-url",
            json={"filename": "空.docx", "size": size},
            headers=headers,
        )
        assert r.status_code == 400, (size, r.text)
        assert r.json()["code"] == "empty_file", size


async def test_upload_url_rejects_too_large(client, session):
    await make_user(session, "v003")
    headers = await auth_headers(client, "v003")

    r = await client.post(
        "/api/v1/submissions/upload-url",
        json={"filename": "大文件.docx", "size": get_settings().upload_max_bytes + 1},
        headers=headers,
    )
    assert r.status_code == 413, r.text
    assert r.json()["code"] == "file_too_large"


@pytest.mark.parametrize(
    "bad_key",
    [
        "tmp/xyz.docx",
        "submissions/aaa.docx",
        "tmp/../escape.docx",
        f"tmp/{'A' * 32}.docx",
        f"tmp/{'a' * 32}.pdf",
    ],
)
async def test_confirm_rejects_bad_object_key(client, session, bad_key):
    await make_user(session, "v004")
    headers = await auth_headers(client, "v004")

    r = await client.post(
        "/api/v1/submissions",
        json={"object_key": bad_key, "filename": "论文.docx"},
        headers=headers,
    )
    assert r.status_code == 400, (bad_key, r.text)
    assert r.json()["code"] == "invalid_upload_key", bad_key


async def test_confirm_rejects_missing_staged_object(client, session):
    await make_user(session, "v005")
    headers = await auth_headers(client, "v005")

    r = await client.post(
        "/api/v1/submissions",
        json={"object_key": f"tmp/{'c' * 32}.docx", "filename": "论文.docx"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "upload_not_found"


async def test_confirm_rejects_empty_staged_object(client, session, storage):
    await make_user(session, "v008")
    headers = await auth_headers(client, "v008")
    key = f"tmp/{'f' * 32}.docx"
    storage.write_staged(key, b"")

    r = await client.post(
        "/api/v1/submissions",
        json={"object_key": key, "filename": "空.docx"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "empty_file"


async def test_confirm_rejects_oversized_staged_object_and_removes_tmp(
    client, session, storage, monkeypatch
):
    await make_user(session, "v006")
    headers = await auth_headers(client, "v006")
    _patch_settings(monkeypatch, max_bytes=100)
    key = f"tmp/{'d' * 32}.docx"
    storage.write_staged(key, b"x" * 200)

    r = await client.post(
        "/api/v1/submissions",
        json={"object_key": key, "filename": "大文件.docx"},
        headers=headers,
    )
    assert r.status_code == 413, r.text
    assert r.json()["code"] == "file_too_large"
    assert key not in storage.objects  # HEAD 兜底：超限拒收并清掉暂存


async def test_confirm_rolls_back_when_adopt_fails(client, session, storage):
    await make_user(session, "v007")
    headers = await auth_headers(client, "v007")
    key = f"tmp/{'e' * 32}.docx"
    storage.write_staged(key, minimal_docx_bytes())
    storage.fail_adopt = True

    with pytest.raises(RuntimeError):
        await client.post(
            "/api/v1/submissions",
            json={"object_key": key, "filename": "论文.docx"},
            headers=headers,
        )
    storage.fail_adopt = False

    # 无残留：记录未落库、转正目录已清理
    assert storage.keys_under(f"submissions/{'e' * 32}") == []
    r = await client.get("/api/v1/submissions", headers=headers)
    assert r.json()["total"] == 0


async def test_list_only_own_submissions_desc(client, session, storage):
    await make_user(session, "lister")
    await make_user(session, "other")
    h1 = await auth_headers(client, "lister")
    h2 = await auth_headers(client, "other")

    ids = [await upload_docx(client, storage, h1) for _ in range(3)]
    await upload_docx(client, storage, h2)

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


async def test_other_student_cannot_access(client, session, storage):
    await make_user(session, "owner")
    await make_user(session, "intruder")
    h_owner = await auth_headers(client, "owner")
    h_intruder = await auth_headers(client, "intruder")

    submission_id = await upload_docx(client, storage, h_owner)

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


async def test_admin_cannot_access_submissions(client, session, storage):
    await make_user(session, "owner2")
    await make_user(session, "admin1", role="admin")
    h_owner = await auth_headers(client, "owner2")
    h_admin = await auth_headers(client, "admin1")

    submission_id = await upload_docx(client, storage, h_owner)

    r = await client.get(f"/api/v1/submissions/{submission_id}", headers=h_admin)
    assert r.status_code == 403
    r = await client.get(f"/api/v1/submissions/{submission_id}/marked", headers=h_admin)
    assert r.status_code == 403


async def test_upload_requires_student_role(client, session):
    await make_user(session, "t3001", role="teacher")
    headers = await auth_headers(client, "t3001")

    r = await client.post(
        "/api/v1/submissions/upload-url",
        json={"filename": "论文.docx", "size": 10},
        headers=headers,
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
        "/api/v1/submissions/upload-url",
        json={"filename": "论文.docx", "size": 10},
        headers=headers,
    )
    assert r.status_code == 403
    assert r.json()["code"] == "password_required_change"
