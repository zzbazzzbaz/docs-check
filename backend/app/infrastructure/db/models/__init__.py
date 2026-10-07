"""集中注册所有表模型，保证 SQLModel.metadata 扫到全部表。

新增模型后在此 import 一次即可（脚本 / alembic / 测试共用）。
"""

from app.infrastructure.db.models.review_task import ReviewTask as ReviewTask
from app.infrastructure.db.models.submission import Submission as Submission
from app.infrastructure.db.models.user import User as User

__all__ = ["ReviewTask", "Submission", "User"]
