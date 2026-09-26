"""网页服务：上传 → 同步审核 → 三件下载（技术设计 §8）。

覆盖四件安全事：超大上传被拒、坏文件给人话、job 地址不可越权（未知 / 过期 404）。
"""

from __future__ import annotations

import io
import os
import re
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from tests.fixtures.base import BASE
from tests.fixtures.synth import ea

import thesischeck.web.app as web

_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(web, "JOBS_ROOT", tmp_path / "jobs")
    # `raise_server_exceptions=False`：未预期异常走兜底 handler 返回 500，正好用来验证"不漏堆栈"
    with TestClient(web.app, raise_server_exceptions=False) as test_client:
        yield test_client


def _upload(client: TestClient, name: str, data: bytes) -> Response:
    return cast(Response, client.post("/api/review", files={"file": (name, data, _MEDIA)}))


def test_review_returns_summary_and_three_downloads(client: TestClient) -> None:
    response = _upload(client, "thesis.docx", BASE)
    assert response.status_code == 200
    payload: dict[str, Any] = response.json()
    summary = payload["summary"]
    assert summary["fail"] == 0
    assert summary["undetermined"] == 0
    assert summary["unrecognised"] == 0
    assert summary["not_run"] == 0
    assert isinstance(summary["by_scope"], dict)
    assert payload["uncovered"]
    assert set(payload["downloads"]) == {"issues", "report", "marked"}

    issues = client.get(payload["downloads"]["issues"])
    assert issues.status_code == 200
    assert issues.json()["summary"]["fail"] == 0

    report = client.get(payload["downloads"]["report"])
    assert report.status_code == 200
    assert b"<html" in report.content.lower()

    marked = client.get(payload["downloads"]["marked"])
    assert marked.status_code == 200
    assert marked.content[:2] == b"PK"


def test_deviation_is_counted_and_annotated(client: TestClient) -> None:
    """真实偏差：摘要标题字体改掉，必须计入不通过，标注版里能看到批注。"""
    response = _upload(client, "case.docx", ea("中文摘要标题", "仿宋").apply(BASE))
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["fail"] >= 1

    marked = client.get(payload["downloads"]["marked"])
    assert marked.status_code == 200
    comments = zipfile.ZipFile(io.BytesIO(marked.content)).read("word/comments.xml")
    assert b"ABS-C-02" in comments


def test_oversized_upload_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """请求体上限：调小常量即可验证，不必真造 50 MB。"""
    monkeypatch.setattr(web, "MAX_UPLOAD_BYTES", 64)
    response = _upload(client, "big.docx", BASE)
    assert response.status_code == 413
    assert "过大" in response.json()["error"]


@pytest.mark.parametrize("name", ["broken.docx", "legacy.doc"])
def test_broken_upload_gets_readable_error(client: TestClient, name: str) -> None:
    """不是 zip / 老式 .doc：4xx + 人话，不是 500 堆栈。"""
    response = _upload(client, name, b"definitely not a word package")
    assert response.status_code == 400
    message = response.json()["error"]
    assert message
    assert "Traceback" not in message


def test_ole_content_named_docx_is_rejected_readably(client: TestClient) -> None:
    response = _upload(client, "legacy.docx", _OLE)
    assert response.status_code == 400
    assert "doc" in response.json()["error"]


def test_unknown_job_is_not_found(client: TestClient) -> None:
    assert client.get("/api/review/deadbeef/issues.json").status_code == 404
    assert client.get("/api/review/not-a-job/report.html").status_code == 404


def test_upload_filename_is_reduced_to_basename() -> None:
    """上传名里的路径成分一律丢弃（Windows 反斜杠也要处理），落盘另有随机名。"""
    assert web._safe_name("..\\..\\evil.docx") == "evil.docx"
    assert web._safe_name("/etc/passwd.docx") == "passwd.docx"


def test_expired_job_is_removed(client: TestClient, tmp_path: Path) -> None:
    payload = _upload(client, "case.docx", BASE).json()
    job_dir = tmp_path / "jobs" / payload["job"]
    assert job_dir.is_dir()
    old = time.time() - web.JOB_TTL_SECONDS - 60
    os.utime(job_dir, (old, old))

    response = client.get(payload["downloads"]["issues"])
    assert response.status_code == 404
    assert not job_dir.exists()


def test_index_is_single_page_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/api/review" in response.text


class _FakeReport:
    """只提供 `create_review` 用到的两个成员。"""

    uncovered: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {"summary": {}}


class _FakeResult:
    def __init__(self, marked_docx: Path) -> None:
        self.marked_docx = marked_docx
        self.report = _FakeReport()


def test_upload_is_stored_under_a_random_name(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """落盘用随机名，不采用上传的原始名（防可预测路径 / 覆盖）。"""
    seen: list[str] = []

    def fake_review(docx: Path, outdir: Path) -> _FakeResult:
        seen.append(docx.name)
        marked = outdir / "marked.docx"
        marked.write_bytes(b"PK")
        return _FakeResult(marked)

    monkeypatch.setattr(web, "review", fake_review)
    assert _upload(client, "thesis.docx", BASE).status_code == 200
    assert len(seen) == 1
    assert re.fullmatch(r"[0-9a-f]{32}\.docx", seen[0])
    assert seen[0] != "thesis.docx"


def test_unexpected_error_returns_500_without_stack(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未预期异常 → 500 + 通用消息，堆栈与异常细节不外泄。"""

    def boom(_: Path, __: Path) -> _FakeResult:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(web, "review", boom)
    response = _upload(client, "thesis.docx", BASE)
    assert response.status_code == 500
    assert "Traceback" not in response.text
    assert "secret internal detail" not in response.text
    assert response.json()["error"]
