"""提交域：上传三段式（签发 / 确认）、我的列表、详情（sequence）、下载解析、归属鉴权。"""

import asyncio
import re
from pathlib import Path
from typing import Literal
from uuid import uuid4

from sqlmodel import and_, col, func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.infrastructure.db.models.submission import Submission
from app.infrastructure.db.models.user import User
from app.infrastructure.storage.base import Storage
from app.services.errors import (
    EmptyFileError,
    FileTooLargeError,
    ForbiddenError,
    InvalidUploadKeyError,
    NotFoundError,
    UnsupportedFileTypeError,
    UploadNotFoundError,
)
from app.services.pagination import normalize

DownloadKind = Literal["original", "marked"]

# 暂存 key 由后端生成；格式即安全边界（不接受客户端任意路径）
_UPLOAD_KEY_RE = re.compile(r"^tmp/(?P<uuid>[0-9a-f]{32})\.docx$")


def validate_filename(filename: str | None) -> None:
    """后缀校验：签发与确认都过这一关。"""
    if not filename or not filename.lower().endswith(".docx"):
        raise UnsupportedFileTypeError("仅支持 .docx 文件")


async def prepare_upload(
    *, filename: str | None, size: int, storage: Storage, max_bytes: int
) -> tuple[str, str]:
    """三段式 ①：校验声明的大小（预签名 PUT 无法硬限长）→ 签发预签名 PUT。

    返回（object_key, upload_url）。
    """
    validate_filename(filename)
    if size <= 0:
        raise EmptyFileError("请选择文件")
    if size > max_bytes:
        raise FileTooLargeError(f"文件超过 {max_bytes // (1024 * 1024)}MB 限制")
    key = f"tmp/{uuid4().hex}.docx"
    url = await asyncio.to_thread(storage.presigned_upload_url, key)
    return key, url


async def create(
    session: AsyncSession,
    *,
    student: User,
    object_key: str,
    filename: str,
    storage: Storage,
    max_bytes: int,
) -> Submission:
    """三段式 ③：确认上传 → 建 pending 记录 → 暂存转正 → commit。

    大小以 HEAD 为准（兜底），超限拒收并清理暂存；请求内不跑引擎（异步任务见 worker）。
    """
    validate_filename(filename)
    match = _UPLOAD_KEY_RE.fullmatch(object_key)
    if match is None:
        raise InvalidUploadKeyError("上传标识无效，请重新提交")
    staged_size = await asyncio.to_thread(storage.staged_size, object_key)
    if staged_size is None:
        raise UploadNotFoundError("上传文件不存在或已过期，请重新上传")
    if staged_size == 0:
        raise EmptyFileError("请选择文件")
    if staged_size > max_bytes:
        await asyncio.to_thread(storage.remove_staged, object_key)
        raise FileTooLargeError(f"文件超过 {max_bytes // (1024 * 1024)}MB 限制")

    assert student.id is not None
    safe_name = Path(filename.replace("\\", "/")).name[:255]
    storage_dir = f"submissions/{match['uuid']}"
    submission = Submission(student_id=student.id, original_filename=safe_name, status="pending")
    session.add(submission)
    await session.flush()
    try:
        await asyncio.to_thread(storage.adopt_staged, object_key, storage_dir)
        submission.storage_dir = storage_dir
        await session.commit()
    except Exception:
        await session.rollback()
        await asyncio.to_thread(storage.remove, storage_dir)  # best-effort：清掉可能的半转正
        raise
    await session.refresh(submission)
    return submission


async def list_mine(
    session: AsyncSession, *, student: User, offset: int, limit: int
) -> tuple[int, list[Submission]]:
    offset, limit = normalize(offset, limit)
    total = (
        await session.exec(
            select(func.count()).select_from(Submission).where(Submission.student_id == student.id)
        )
    ).one()
    items = (
        await session.exec(
            select(Submission)
            .where(Submission.student_id == student.id)
            .order_by(col(Submission.created_at).desc(), col(Submission.id).desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return total, list(items)


async def get_detail(
    session: AsyncSession, *, viewer: User, submission_id: int
) -> tuple[Submission, int]:
    """详情 + 「第 N 次提交」（按该生提交时间正序，含并列时间用 id 决胜）。"""
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise NotFoundError(f"submission {submission_id} not found")
    await ensure_can_view(session, viewer=viewer, submission=submission)
    target_id = submission.id
    if target_id is None:  # 理论不可达：已入库对象必有主键
        raise NotFoundError(f"submission {submission_id} not found")
    created_at = submission.created_at
    not_after = or_(
        Submission.created_at < created_at,
        and_(Submission.created_at == created_at, col(Submission.id) <= target_id),
    )
    sequence = (
        await session.exec(
            select(func.count())
            .select_from(Submission)
            .where(Submission.student_id == submission.student_id, not_after)
        )
    ).one()
    return submission, sequence


async def ensure_can_view(session: AsyncSession, *, viewer: User, submission: Submission) -> None:
    """归属鉴权：学生本人 / 名下且启用学生的教师；管理员一律不可见。"""
    if viewer.role == "student" and submission.student_id == viewer.id:
        return
    if viewer.role == "teacher":
        student = await session.get(User, submission.student_id)
        if student is not None and student.teacher_id == viewer.id and student.is_active:
            return
    raise ForbiddenError("无权访问该资源")


async def resolve_download(
    session: AsyncSession,
    *,
    viewer: User,
    submission_id: int,
    kind: DownloadKind,
    storage: Storage,
) -> str:
    """返回预签名下载 URL；无文件 / 失败提交 → 404（不签发）。"""
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise NotFoundError(f"submission {submission_id} not found")
    await ensure_can_view(session, viewer=viewer, submission=submission)
    if submission.status == "failed" or submission.storage_dir is None:
        raise NotFoundError("文件不存在")
    if kind == "marked" and submission.status != "success":
        raise NotFoundError("文件不存在")
    url = await asyncio.to_thread(
        storage.presigned_download_url,
        submission.storage_dir,
        kind,
        filename=download_name(submission.original_filename, kind),
    )
    if url is None:
        raise NotFoundError("文件不存在")
    return url


def download_name(original_filename: str, kind: DownloadKind) -> str:
    if kind == "original":
        return original_filename
    return f"{Path(original_filename).stem}.marked.docx"
