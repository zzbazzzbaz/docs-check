"""管理端：仪表盘统计（只返回数量，不暴露提交内容）。"""

from fastapi import APIRouter

from app.api.dependencies import CurrentAdminDep, SessionDep
from app.api.schemas.admin_stats import AdminStats
from app.services.admin import admin_stats_service

router = APIRouter()


@router.get("/stats", response_model=AdminStats)
async def get_stats(session: SessionDep, _admin: CurrentAdminDep) -> AdminStats:
    counts = await admin_stats_service.get_stats(session)
    return AdminStats.model_validate(
        {
            "student_count": counts.student_count,
            "teacher_count": counts.teacher_count,
            "submission_count": counts.submission_count,
        }
    )
