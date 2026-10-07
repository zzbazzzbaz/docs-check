"""学生端提交接口：上传入队 / 列表 / 详情 / 下载。

详情与下载共用归属鉴权：本人（学生）或名下教师（见 submissions_service.ensure_can_view）。
"""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import FileResponse

from app.api.dependencies import (
    CurrentReadyUserDep,
    CurrentStudentDep,
    PageParamsDep,
    SessionDep,
    StorageDep,
)
from app.api.schemas.common import Page
from app.api.schemas.submissions import (
    SubmissionDetail,
    SubmissionListItem,
    submission_detail,
    submission_list_item,
)
from app.api.uploads import read_capped
from app.core.config import get_settings
from app.services.pagination import normalize
from app.services.submissions import submissions_service

router = APIRouter()

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("", response_model=Page[SubmissionListItem])
async def list_my_submissions(
    session: SessionDep, page: PageParamsDep, me: CurrentStudentDep
) -> Page[SubmissionListItem]:
    offset, limit = normalize(*page)
    total, items = await submissions_service.list_mine(
        session, student=me, offset=offset, limit=limit
    )
    return Page[SubmissionListItem](
        total=total,
        items=[submission_list_item(item) for item in items],
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=SubmissionDetail, status_code=status.HTTP_202_ACCEPTED)
async def create_submission(
    file: Annotated[UploadFile, File()],
    *,
    session: SessionDep,
    storage: StorageDep,
    me: CurrentStudentDep,
) -> SubmissionDetail:
    settings = get_settings()
    data = await read_capped(file, settings.upload_max_bytes)
    submission = await submissions_service.create(
        session,
        student=me,
        filename=file.filename,
        data=data,
        storage=storage,
        max_bytes=settings.upload_max_bytes,
    )
    assert submission.id is not None
    _, sequence = await submissions_service.get_detail(
        session, viewer=me, submission_id=submission.id
    )
    return submission_detail(submission, sequence)


@router.get("/{submission_id}", response_model=SubmissionDetail)
async def get_submission(
    submission_id: int, session: SessionDep, me: CurrentReadyUserDep
) -> SubmissionDetail:
    submission, sequence = await submissions_service.get_detail(
        session, viewer=me, submission_id=submission_id
    )
    return submission_detail(submission, sequence)


@router.get("/{submission_id}/original")
async def download_original(
    submission_id: int, session: SessionDep, storage: StorageDep, me: CurrentReadyUserDep
) -> FileResponse:
    path, name = await submissions_service.resolve_download(
        session, viewer=me, submission_id=submission_id, kind="original", storage=storage
    )
    return FileResponse(path, media_type=_DOCX_MIME, filename=name)


@router.get("/{submission_id}/marked")
async def download_marked(
    submission_id: int, session: SessionDep, storage: StorageDep, me: CurrentReadyUserDep
) -> FileResponse:
    path, name = await submissions_service.resolve_download(
        session, viewer=me, submission_id=submission_id, kind="marked", storage=storage
    )
    return FileResponse(path, media_type=_DOCX_MIME, filename=name)
