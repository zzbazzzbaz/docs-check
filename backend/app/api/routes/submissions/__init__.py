from fastapi import APIRouter

from app.api.routes.submissions.submissions import router as submissions_routes

submissions_router = APIRouter()
submissions_router.include_router(submissions_routes, prefix="/submissions", tags=["submissions"])
