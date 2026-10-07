from fastapi import APIRouter

from app.api.routes.admin.users import router as admin_routes

admin_router = APIRouter()
admin_router.include_router(admin_routes, prefix="/admin", tags=["admin"])
