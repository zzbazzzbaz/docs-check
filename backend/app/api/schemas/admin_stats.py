from pydantic import BaseModel


class AdminStats(BaseModel):
    """仪表盘概览：启用学生数 / 启用教师数 / 全部提交数。"""

    student_count: int
    teacher_count: int
    submission_count: int
