"""教师端：名下学生列表 / 学生信息 / 学生提交列表（只读）。"""

from fastapi import APIRouter, Query

from app.api.dependencies import CurrentTeacherDep, PageParamsDep, SessionDep
from app.api.schemas.common import Page
from app.api.schemas.students import StudentDetail, StudentListItem
from app.api.schemas.submissions import (
    SubmissionListItem,
    submission_counts,
    submission_list_item,
)
from app.services.pagination import normalize
from app.services.students import students_service
from app.services.students.students_service import StudentRow

router = APIRouter()


def _student_item(row: StudentRow) -> StudentListItem:
    latest = row.latest_success
    return StudentListItem.model_validate(
        {
            "id": row.user.id,
            "username": row.user.username,
            "name": row.user.name,
            "major": row.user.major,
            "success_count": row.success_count,
            "latest_submitted_at": row.latest_submitted_at,
            "latest_counts": submission_counts(latest).model_dump() if latest else None,
        }
    )


@router.get("", response_model=Page[StudentListItem])
async def list_students(
    session: SessionDep,
    page: PageParamsDep,
    me: CurrentTeacherDep,
    q: str | None = Query(default=None, max_length=64),
) -> Page[StudentListItem]:
    offset, limit = normalize(*page)
    total, rows = await students_service.list_students(
        session, teacher=me, q=q, offset=offset, limit=limit
    )
    return Page[StudentListItem](
        total=total,
        items=[_student_item(row) for row in rows],
        offset=offset,
        limit=limit,
    )


@router.get("/{student_id}", response_model=StudentDetail)
async def get_student(student_id: int, session: SessionDep, me: CurrentTeacherDep) -> StudentDetail:
    student = await students_service.get_student(session, teacher=me, student_id=student_id)
    return StudentDetail.model_validate(
        {
            "id": student.id,
            "username": student.username,
            "name": student.name,
            "major": student.major,
        }
    )


@router.get("/{student_id}/submissions", response_model=Page[SubmissionListItem])
async def list_student_submissions(
    student_id: int, session: SessionDep, page: PageParamsDep, me: CurrentTeacherDep
) -> Page[SubmissionListItem]:
    offset, limit = normalize(*page)
    total, items = await students_service.list_submissions(
        session, teacher=me, student_id=student_id, offset=offset, limit=limit
    )
    return Page[SubmissionListItem](
        total=total,
        items=[submission_list_item(item) for item in items],
        offset=offset,
        limit=limit,
    )
