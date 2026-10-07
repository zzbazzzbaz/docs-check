"""学生端提交接口：上传三段式（签发 / 确认）/ 列表 / 详情 / 下载（307 预签名）。

详情与下载共用归属鉴权：本人（学生）或名下教师（见 submissions_service.ensure_can_view）。
"""

from fastapi import APIRouter, status
from fastapi.responses import RedirectResponse

from app.api.dependencies import (
    CurrentReadyUserDep,
    CurrentStudentDep,
    PageParamsDep,
    SessionDep,
    StorageDep,
)
from app.api.schemas.common import Page
from app.api.schemas.submissions import (
    SubmissionCreate,
    SubmissionDetail,
    SubmissionListItem,
    UploadUrlRequest,
    UploadUrlResponse,
    submission_detail,
    submission_list_item,
)
from app.core.config import get_settings
from app.services.pagination import normalize
from app.services.submissions import submissions_service

router = APIRouter()


@router.post("/upload-url", response_model=UploadUrlResponse)
async def create_upload_url(
    payload: UploadUrlRequest, *, storage: StorageDep, me: CurrentStudentDep
) -> UploadUrlResponse:
    """三段式 ①：签发预签名 PUT（字节不经过本服务）。"""
    settings = get_settings()
    object_key, upload_url = await submissions_service.prepare_upload(
        filename=payload.filename,
        size=payload.size,
        storage=storage,
        max_bytes=settings.upload_max_bytes,
    )
    return UploadUrlResponse(
        object_key=object_key, upload_url=upload_url, expires_in=settings.presign_expire_seconds
    )


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
    payload: SubmissionCreate, *, session: SessionDep, storage: StorageDep, me: CurrentStudentDep
) -> SubmissionDetail:
    """三段式 ③：确认直传结果（HEAD 兜底校验）并入队审核。"""
    settings = get_settings()
    submission = await submissions_service.create(
        session,
        student=me,
        object_key=payload.object_key,
        filename=payload.filename,
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
) -> RedirectResponse:
    url = await submissions_service.resolve_download(
        session, viewer=me, submission_id=submission_id, kind="original", storage=storage
    )
    return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/{submission_id}/marked")
async def download_marked(
    submission_id: int, session: SessionDep, storage: StorageDep, me: CurrentReadyUserDep
) -> RedirectResponse:
    url = await submissions_service.resolve_download(
        session, viewer=me, submission_id=submission_id, kind="marked", storage=storage
    )
    return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
