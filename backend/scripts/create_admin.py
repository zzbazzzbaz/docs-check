"""创建或提升管理员账号。

用法：
    uv run python -m scripts.create_admin <username> [password] [name]

用户不存在时必须提供 password；已存在则重置为启用状态的管理员（不改密码）。
管理员不强制首次改密（must_change_password=False）。
"""

import asyncio
import sys

from app.core.config import get_settings
from app.infrastructure.db.engine import create_engine
from app.infrastructure.db.session import create_session_factory
from app.services.users import users_service


async def main() -> int:
    if len(sys.argv) not in (2, 3, 4):
        print("用法：uv run python -m scripts.create_admin <username> [password] [name]")
        return 2

    username = sys.argv[1]
    password = sys.argv[2] if len(sys.argv) >= 3 else None
    name = sys.argv[3] if len(sys.argv) == 4 else username

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
            user = await users_service.get_by_username(session, username)
            if user is None:
                if password is None:
                    print(f"用户 {username!r} 不存在，创建需要提供密码")
                    return 1
                await users_service.create_user(
                    session,
                    username=username,
                    password=password,
                    name=name,
                    role="admin",
                    must_change_password=False,
                )
                print(f"已创建管理员 {username!r}")
                return 0
            user.role = "admin"
            user.is_active = True
            user.must_change_password = False
            session.add(user)
            await session.commit()
            print(f"已把 {username!r} 设为启用状态的管理员")
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
