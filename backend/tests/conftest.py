from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel import SQLModel

import app.infrastructure.db.models  # noqa: F401 - 注册所有表到 metadata
from app.api.dependencies import get_session
from app.api.error_handlers import register_error_handlers
from app.api.routes import api_router
from app.core.config import get_settings
from app.infrastructure.db.engine import create_engine
from app.infrastructure.db.session import SessionFactory, create_session_factory
from app.infrastructure.review.runner import ReviewRunner
from app.services.tasks.review_worker import ReviewWorker
from tests.db import prepare_test_database
from tests.fakes import FakeStorage


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[SessionFactory]:
    """测试读 `.env`（唯一来源），连 DATABASE_URL 派生的 `<db>_test` 库。

    自动建库 + 每次重建表，不污染开发库；禁止在测试里硬编码环境变量。
    """
    get_settings.cache_clear()
    settings = get_settings()
    test_url = await prepare_test_database(settings.database_url)
    engine = create_engine(
        test_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(session_factory: SessionFactory) -> AsyncIterator:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def app(session_factory: SessionFactory) -> FastAPI:
    """测试用 app：不跑 lifespan（worker 不自动启动），手动装配 app.state。

    存储一律注入 FakeStorage（内存替身）：不访问网络、不触碰真实 COS。
    """
    settings = get_settings()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    storage = FakeStorage()
    runner = ReviewRunner()
    app.state.storage = storage
    app.state.review_runner = runner
    app.state.review_worker = ReviewWorker(
        session_factory=session_factory, runner=runner, storage=storage, settings=settings
    )

    async def override_session() -> AsyncIterator:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def worker(app: FastAPI) -> ReviewWorker:
    return app.state.review_worker


@pytest_asyncio.fixture
async def storage(app: FastAPI) -> FakeStorage:
    return app.state.storage
