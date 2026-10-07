from fastapi import APIRouter

from app.api.routes.admin import stats as admin_stats
from app.api.routes.admin import users as admin_users

admin_router = APIRouter()
admin_router.include_router(admin_stats.router, prefix="/admin", tags=["admin"])
admin_router.include_router(admin_users.router, prefix="/admin", tags=["admin"])
