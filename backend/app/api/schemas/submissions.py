from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.infrastructure.db.models.submission import Submission

SubmissionStatus = Literal["pending", "processing", "success", "failed"]


class UploadUrlRequest(BaseModel):
    """三段式 ①：签发预签名 PUT 的请求。"""

    filename: str
    size: int


class UploadUrlResponse(BaseModel):
    object_key: str
    upload_url: str
    expires_in: int


class SubmissionCreate(BaseModel):
    """三段式 ③：确认上传（客户端已直传完成）。"""

    object_key: str
    filename: str


class Counts(BaseModel):
    fail: int = 0
    undetermined: int = 0
    not_run: int = 0
    unrecognised: int = 0


class SubmissionListItem(BaseModel):
    id: int
    created_at: datetime
    original_filename: str
    status: SubmissionStatus
    counts: Counts


class SubmissionDetail(SubmissionListItem):
    error_message: str | None = None
    by_scope: dict[str, Counts] | None = None
    ruleset_version: str | None = None
    sequence: int


def submission_counts(submission: Submission) -> Counts:
    return Counts(
        fail=submission.fail_count,
        undetermined=submission.undetermined_count,
        not_run=submission.not_run_count,
        unrecognised=submission.unrecognised_count,
    )


def submission_list_item(submission: Submission) -> SubmissionListItem:
    return SubmissionListItem.model_validate(
        {
            "id": submission.id,
            "created_at": submission.created_at,
            "original_filename": submission.original_filename,
            "status": submission.status,
            "counts": submission_counts(submission).model_dump(),
        }
    )


def submission_detail(submission: Submission, sequence: int) -> SubmissionDetail:
    return SubmissionDetail.model_validate(
        {
            "id": submission.id,
            "created_at": submission.created_at,
            "original_filename": submission.original_filename,
            "status": submission.status,
            "counts": submission_counts(submission).model_dump(),
            "error_message": submission.error_message,
            "by_scope": submission.by_scope,
            "ruleset_version": submission.ruleset_version,
            "sequence": sequence,
        }
    )
