"""开发种子数据（仅开发工具，不属于产品功能）。

用法：
    uv run python -m scripts.dev_seed

幂等：账号已存在则跳过。统一初始密码 123456；除管理员外强制首次改密。
"""

import asyncio

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.infrastructure.db.engine import create_engine
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import create_session_factory
from app.services.users import users_service

ADMIN = ("admin", "管理员")

TEACHERS: list[tuple[str, str]] = [
    ("t1001", "李老师"),
    ("t1002", "王老师"),
]

STUDENTS: list[tuple[str, str, str | None, str | None]] = [
    # (学号, 姓名, 专业, 指导教师工号)
    ("2206100001", "张三", "物联网工程", "t1001"),
    ("2206100002", "李四", "物联网工程", "t1001"),
    ("2206100003", "王五", "计算机科学与技术", "t1001"),
    ("2206100004", "赵六", "计算机科学与技术", "t1001"),
    ("2206100005", "钱七", "软件工程", "t1001"),
    ("2206100006", "孙八", "软件工程", "t1002"),
    ("2206100007", "周九", "网络工程", "t1002"),
    ("2206100008", "吴十", "网络工程", "t1002"),
    ("2206100009", "郑十一", "电子信息工程", "t1002"),
    ("2206100010", "王十二", "电子信息工程", None),
]


async def _ensure_user(
    session: AsyncSession,
    *,
    username: str,
    name: str,
    role: str,
    must_change_password: bool = True,
    major: str | None = None,
    teacher_id: int | None = None,
) -> User:
    existing = await users_service.get_by_username(session, username)
    if existing is not None:
        print(f"skip  {role:<7} {username}（已存在）")
        return existing
    user = await users_service.create_user(
        session,
        username=username,
        password=users_service.INITIAL_PASSWORD,
        name=name,
        role=role,
        must_change_password=must_change_password,
        major=major,
        teacher_id=teacher_id,
    )
    print(f"seed  {role:<7} {username} {name}")
    return user


async def main() -> None:
    settings = get_settings()
    engine = create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            await _ensure_user(
                session,
                username=ADMIN[0],
                name=ADMIN[1],
                role="admin",
                must_change_password=False,
            )
            teacher_ids: dict[str, int] = {}
            for username, name in TEACHERS:
                teacher = await _ensure_user(session, username=username, name=name, role="teacher")
                if teacher.id is not None:
                    teacher_ids[username] = teacher.id
            for username, name, major, teacher_username in STUDENTS:
                teacher_id = teacher_ids.get(teacher_username) if teacher_username else None
                await _ensure_user(
                    session,
                    username=username,
                    name=name,
                    role="student",
                    major=major,
                    teacher_id=teacher_id,
                )
        print("种子数据就绪（初始密码 123456）")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
