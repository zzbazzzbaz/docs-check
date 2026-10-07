from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import hash_password, verify_password
from app.infrastructure.db.models.user import User
from app.services.errors import (
    AlreadyExistsError,
    InvalidActionError,
    OldPasswordIncorrectError,
)

# 手动新建账号 / 重置密码时的统一初始密码（仅服务层引用，不散落）
INITIAL_PASSWORD = "123456"


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_by_username(session: AsyncSession, username: str) -> User | None:
    return (await session.exec(select(User).where(User.username == username))).one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    name: str,
    role: str,
    must_change_password: bool = True,
    major: str | None = None,
    teacher_id: int | None = None,
) -> User:
    """通用建号（学生/教师/管理员）；角色相关校验由各自入口先做。"""
    if await get_by_username(session, username) is not None:
        raise AlreadyExistsError(f"username {username!r} already taken", code="username_taken")
    user = User(
        username=username,
        password_hash=hash_password(password),
        name=name,
        role=role,
        must_change_password=must_change_password,
        major=major,
        teacher_id=teacher_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def change_password(
    session: AsyncSession, *, user: User, old_password: str, new_password: str
) -> None:
    """自助改密；成功后清除强制改密标志。"""
    if not verify_password(old_password, user.password_hash):
        raise OldPasswordIncorrectError("old password is incorrect")
    if old_password == new_password:
        raise InvalidActionError("new password must differ from old", code="password_unchanged")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    session.add(user)
    await session.commit()


async def get_me(session: AsyncSession, *, user: User) -> tuple[User, User | None]:
    """本人资料 + 导师（仅学生、且已分配时返回）。"""
    teacher = None
    if user.role == "student" and user.teacher_id is not None:
        teacher = await get_by_id(session, user.teacher_id)
    return user, teacher
