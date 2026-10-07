from fastapi import APIRouter

from app.api.routes.admin import admin_router
from app.api.routes.auth import auth_router
from app.api.routes.students import students_router
from app.api.routes.submissions import submissions_router
from app.api.routes.users import users_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(submissions_router)
api_router.include_router(students_router)
api_router.include_router(admin_router)
