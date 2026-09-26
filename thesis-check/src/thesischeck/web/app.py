"""HTTP 服务：单页 HTML 上传，同步审核，产出三件下载。

纪律（技术设计 §8）：

- 端点写成 `def`——解析是同步 CPU 代码，`async def` 里直接调用会卡住事件循环；
- 上传是不可信输入：请求体限长、落盘随机名、只取文件名 basename、不跟随文档里的 URL；
- 临时产物不落数据库：`job` → 临时目录，保留 1 小时，启动时清理过期；
- 出错一律转成人话，不把堆栈丢给学生。
"""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..errors import ThesisCheckError
from ..pipeline import review

JOBS_ROOT = Path(tempfile.gettempdir()) / "thesischeck-jobs"
JOB_TTL_SECONDS = 3600
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

_CHUNK = 1024 * 1024
_STATIC_DIR = Path(__file__).parent / "static"
_JOB_ID = re.compile(r"[0-9a-f]{32}")
_DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_GONE = "结果不存在或已过期，请重新上传。"


class ClientError(Exception):
    """面向学生的 HTTP 错误：状态码 + 一句人话。"""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _cleanup_expired() -> None:
    """删除超过保留期的 job 目录；启动时调用一次。"""
    if not JOBS_ROOT.is_dir():
        return
    deadline = time.time() - JOB_TTL_SECONDS
    for child in list(JOBS_ROOT.iterdir()):
        try:
            if child.is_dir() and child.stat().st_mtime < deadline:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            continue


def _too_large() -> ClientError:
    limit = MAX_UPLOAD_BYTES // (1024 * 1024)
    return ClientError(413, f"文件过大（超过 {limit} MB），请压缩图片后重试。")


def _read_upload(file: UploadFile) -> bytes:
    """流式读上传内容并限长；超限立刻拒绝，不先落盘。"""
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise _too_large()
    data = bytearray()
    while True:
        chunk = file.file.read(_CHUNK)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_UPLOAD_BYTES:
            raise _too_large()
    return bytes(data)


def _safe_name(filename: str | None) -> str:
    """只取文件名的 basename（Windows 客户端可能用反斜杠），其余一律丢弃。"""
    if not filename:
        raise ClientError(400, "没有收到文件，请选择要上传的 .docx。")
    return filename.replace("\\", "/").rsplit("/", 1)[-1]


def _job_dir(job: str) -> Path:
    """校验 job id 并返回目录；不存在或过期一律 404。"""
    if _JOB_ID.fullmatch(job) is None:
        raise ClientError(404, _GONE)
    directory = JOBS_ROOT / job
    try:
        expired = directory.stat().st_mtime < time.time() - JOB_TTL_SECONDS
    except OSError:
        raise ClientError(404, _GONE) from None
    if expired:
        shutil.rmtree(directory, ignore_errors=True)
        raise ClientError(404, _GONE)
    return directory


def _product(job: str, name: str, media_type: str, *, as_attachment: bool = True) -> FileResponse:
    path = _job_dir(job) / name
    if not path.is_file():
        raise ClientError(404, _GONE)
    return FileResponse(path, media_type=media_type, filename=name if as_attachment else None)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    _cleanup_expired()
    yield


app = FastAPI(title="毕业论文格式审核", lifespan=_lifespan)


@app.exception_handler(ClientError)
def _client_error(_: Request, exc: ClientError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status_code)


@app.exception_handler(ThesisCheckError)
def _bad_document(_: Request, exc: ThesisCheckError) -> JSONResponse:
    # 坏文件是常见输入，不是服务器故障，按 400 返回可读原因
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(Exception)
def _unexpected(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse({"error": "服务器内部错误，请稍后再试。"}, status_code=500)


@app.get("/")
def index() -> FileResponse:
    """单页 HTML：上传 + 结果 + 下载，全部由这一个文件完成。"""
    return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")


@app.post("/api/review")
def create_review(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    """同步审核：落盘 → `pipeline.review` → 返回摘要与三个下载地址。"""
    name = _safe_name(file.filename).lower()
    if not name.endswith(".docx"):
        raise ClientError(400, "只支持 .docx 文件；老式 .doc 请用 WPS 另存为 .docx 后再上传。")
    data = _read_upload(file)

    _cleanup_expired()
    job = uuid4().hex
    job_dir = JOBS_ROOT / job
    job_dir.mkdir(parents=True)
    upload = job_dir / f"{uuid4().hex}.docx"
    upload.write_bytes(data)
    try:
        result = review(upload, job_dir)
    except ThesisCheckError:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    upload.unlink(missing_ok=True)
    result.marked_docx.rename(job_dir / "marked.docx")

    return {
        "job": job,
        "summary": result.report.to_json()["summary"],
        "uncovered": list(result.report.uncovered),
        "downloads": {
            "issues": f"/api/review/{job}/issues.json",
            "report": f"/api/review/{job}/report.html",
            "marked": f"/api/review/{job}/marked.docx",
        },
    }


@app.get("/api/review/{job}/issues.json")
def download_issues(job: str) -> FileResponse:
    return _product(job, "issues.json", "application/json")


@app.get("/api/review/{job}/report.html")
def download_report(job: str) -> FileResponse:
    # 报告在浏览器里直接看，不强制下载
    return _product(job, "report.html", "text/html", as_attachment=False)


@app.get("/api/review/{job}/marked.docx")
def download_marked(job: str) -> FileResponse:
    return _product(job, "marked.docx", _DOCX_MEDIA)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thesis-check-web", description="毕业论文格式审核（网页版）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认只监听本机）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    args = parser.parse_args(argv)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0
