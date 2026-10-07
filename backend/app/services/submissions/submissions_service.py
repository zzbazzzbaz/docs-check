"""提交域：上传入队、我的列表、详情（sequence）、下载解析、归属鉴权。"""

import asyncio
from pathlib import Path
from typing import Literal

from sqlmodel import and_, col, func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.infrastructure.db.models.submission import Submission
from app.infrastructure.db.models.user import User
from app.infrastructure.storage.local import LocalStorage
from app.services.errors import (
    EmptyFileError,
    FileTooLargeError,
    ForbiddenError,
    NotFoundError,
    UnsupportedFileTypeError,
)
from app.services.pagination import normalize

DownloadKind = Literal["original", "marked"]


def validate_docx(filename: str | None, data: bytes, *, max_bytes: int) -> None:
    """同步校验：后缀 / 非空 / 大小（大小兜底，正常由 read_capped 先拦）。"""
    if not filename or not filename.lower().endswith(".docx"):
        raise UnsupportedFileTypeError("仅支持 .docx 文件")
    if not data:
        raise EmptyFileError("请选择文件")
    if len(data) > max_bytes:
        raise FileTooLargeError(f"文件超过 {max_bytes // (1024 * 1024)}MB 限制")


async def create(
    session: AsyncSession,
    *,
    student: User,
    filename: str | None,
    data: bytes,
    storage: LocalStorage,
    max_bytes: int,
) -> Submission:
    """上传入队：校验 → 建 pending 记录 → 落原始文件 → 建 pending 任务 → commit。

    请求内不跑引擎（异步任务见 tasks/review_worker.py）。
    """
    validate_docx(filename, data, max_bytes=max_bytes)
    assert filename is not None  # validate_docx 已保证
    assert student.id is not None
    safe_name = Path(filename.replace("\\", "/")).name[:255]
    submission = Submission(student_id=student.id, original_filename=safe_name, status="pending")
    session.add(submission)
    await session.flush()
    assert submission.id is not None
    try:
        storage_dir = await asyncio.to_thread(storage.save_original, submission.id, data)
    except Exception:
        await session.rollback()
        storage.remove(submission.id)
        raise
    submission.storage_dir = storage_dir
    await session.commit()
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
    storage: LocalStorage,
) -> tuple[Path, str]:
    """返回（磁盘路径, 下载文件名）；无文件 / 失败提交 → 404。"""
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise NotFoundError(f"submission {submission_id} not found")
    await ensure_can_view(session, viewer=viewer, submission=submission)
    if submission.status == "failed" or submission.storage_dir is None:
        raise NotFoundError("文件不存在")
    if kind == "marked" and submission.status != "success":
        raise NotFoundError("文件不存在")
    path = storage.resolve(submission.storage_dir, kind)
    if not path.is_file():
        raise NotFoundError("文件不存在")
    return path, download_name(submission.original_filename, kind)


def download_name(original_filename: str, kind: DownloadKind) -> str:
    if kind == "original":
        return original_filename
    return f"{Path(original_filename).stem}.marked.docx"
