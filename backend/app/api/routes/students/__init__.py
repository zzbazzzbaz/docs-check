from fastapi import APIRouter

from app.api.routes.students.students import router as students_routes

students_router = APIRouter()
students_router.include_router(students_routes, prefix="/students", tags=["students"])
