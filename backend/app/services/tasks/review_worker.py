"""审核 worker：submissions 单表状态机 + 进程内消费协程（单实例部署）。

- 领取：`SELECT ... FOR UPDATE SKIP LOCKED WHERE status='pending'`，天然防重复
- 收尾三分支：引擎成功 / 坏文档（不重试，清理文件）/ 基础设施异常（重试至上限）
- 启动恢复 `processing → pending`；运行期 stale 兜底重置
- 测试通过 `process_next()` 手动驱动，不启动后台循环
"""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlmodel import col, select

from app.core.config import Settings
from app.infrastructure.db.models.submission import Submission
from app.infrastructure.db.session import SessionFactory
from app.infrastructure.review.engine import ReviewOutcome, ReviewRejected
from app.infrastructure.review.runner import ReviewRunner
from app.infrastructure.storage.local import LocalStorage

logger = logging.getLogger(__name__)

GENERIC_FAILED_MESSAGE = "审核服务异常，请重新提交或联系管理员"
_ERROR_MAX_CHARS = 2000


class ReviewWorker:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        runner: ReviewRunner,
        storage: LocalStorage,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._runner = runner
        self._storage = storage
        self._settings = settings
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = False
        self._last_stale_check = 0.0

    # ── 生命周期（lifespan 调用；测试不调用） ─────────────────────

    async def start(self) -> None:
        recovered = await self.recover_stuck()
        if recovered:
            logger.warning("recovered %d stuck submission(s) on startup", recovered)
        self._stopping = False
        self._tasks = [
            asyncio.create_task(self._loop(), name=f"review-worker-{index}")
            for index in range(self._settings.review_concurrency)
        ]

    async def stop(self) -> None:
        self._stopping = True
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _loop(self) -> None:
        interval = self._settings.task_poll_interval_seconds
        while not self._stopping:
            try:
                processed = await self.process_next()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("review worker iteration failed")
                processed = False
            if not processed:
                await self._maybe_reset_stale()
                await asyncio.sleep(interval)

    # ── 领取与处理 ─────────────────────────────────────────────

    async def process_next(self) -> bool:
        """领取并处理一份提交；无待处理返回 False。测试直接调用（确定性）。"""
        submission_id = await self._claim()
        if submission_id is None:
            return False
        await self._process(submission_id)
        return True

    async def _claim(self) -> int | None:
        async with self._session_factory() as session:
            statement = (
                select(Submission)
                .where(Submission.status == "pending")
                .order_by(col(Submission.id))
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            submission = (await session.exec(statement)).one_or_none()
            if submission is None or submission.id is None:
                return None
            submission.status = "processing"
            submission.attempts += 1
            submission.started_at = datetime.now(UTC)
            session.add(submission)
            await session.commit()
            return submission.id

    async def _process(self, submission_id: int) -> None:
        storage_dir = await self._load_storage_dir(submission_id)
        if storage_dir is None:
            await self._finish_failed(submission_id, GENERIC_FAILED_MESSAGE, remove_files=False)
            return

        try:
            data = await asyncio.to_thread(self._storage.read_bytes, storage_dir, "original")
            outcome = await self._runner.run(data)
        except ReviewRejected as exc:
            await self._finish_failed(submission_id, str(exc), remove_files=True)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._retry_or_fail(submission_id, exc)
            return

        try:
            issues_bytes = json.dumps(outcome.issues_json, ensure_ascii=False, indent=2).encode(
                "utf-8"
            )
            await asyncio.to_thread(
                self._storage.save_review,
                submission_id,
                marked=outcome.marked_docx,
                issues_json=issues_bytes,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._retry_or_fail(submission_id, exc)
            return

        await self._finish_success(submission_id, outcome)

    async def _load_storage_dir(self, submission_id: int) -> str | None:
        async with self._session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                return None
            return submission.storage_dir

    async def _finish_success(self, submission_id: int, outcome: ReviewOutcome) -> None:
        async with self._session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is not None:
                submission.status = "success"
                submission.error_message = None
                submission.task_error = None
                submission.fail_count = outcome.counts["fail"]
                submission.undetermined_count = outcome.counts["undetermined"]
                submission.not_run_count = outcome.counts["not_run"]
                submission.unrecognised_count = outcome.counts["unrecognised"]
                submission.by_scope = outcome.by_scope
                submission.ruleset_version = outcome.ruleset_version
                submission.finished_at = datetime.now(UTC)
                session.add(submission)
            await session.commit()

    async def _finish_failed(self, submission_id: int, message: str, *, remove_files: bool) -> None:
        """终态失败（坏文档 / 数据缺失）：清零统计、落 finished_at；可选清理文件。"""
        if remove_files:
            await asyncio.to_thread(self._storage.remove, submission_id)
        async with self._session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is not None:
                submission.status = "failed"
                submission.error_message = message
                submission.task_error = None
                submission.fail_count = 0
                submission.undetermined_count = 0
                submission.not_run_count = 0
                submission.unrecognised_count = 0
                submission.by_scope = None
                submission.ruleset_version = None
                submission.finished_at = datetime.now(UTC)
                session.add(submission)
            await session.commit()

    async def _retry_or_fail(self, submission_id: int, exc: Exception) -> None:
        """基础设施异常：未达上限回 pending（退避），达上限标记 failed 并清理文件。"""
        logger.warning(
            "review submission %s failed: %s",
            submission_id,
            exc,
            exc_info=exc,
        )
        async with self._session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                return
            submission.task_error = f"{type(exc).__name__}: {exc}"[:_ERROR_MAX_CHARS]
            if submission.attempts >= self._settings.task_max_attempts:
                submission.status = "failed"
                submission.error_message = GENERIC_FAILED_MESSAGE
                submission.finished_at = datetime.now(UTC)
                session.add(submission)
                await session.commit()
                await asyncio.to_thread(self._storage.remove, submission_id)
                return
            submission.status = "pending"
            submission.started_at = None
            session.add(submission)
            await session.commit()
        await asyncio.sleep(self._settings.task_poll_interval_seconds)

    # ── 恢复与兜底 ─────────────────────────────────────────────

    async def recover_stuck(self) -> int:
        """启动恢复：所有 `processing` → `pending`（单实例部署前提）。返回恢复数量。"""
        return await self._reset_processing(older_than=None)

    async def reset_stale(self) -> int:
        """运行期兜底：`started_at` 早于 stale 阈值仍在 processing 的提交 → pending。"""
        cutoff = datetime.now(UTC) - timedelta(seconds=self._settings.task_stale_seconds)
        return await self._reset_processing(older_than=cutoff)

    async def _reset_processing(self, *, older_than: datetime | None) -> int:
        async with self._session_factory() as session:
            statement = select(Submission).where(Submission.status == "processing")
            if older_than is not None:
                statement = statement.where(col(Submission.started_at) < older_than)
            submissions = (await session.exec(statement)).all()
            for submission in submissions:
                submission.status = "pending"
                submission.started_at = None
                session.add(submission)
            await session.commit()
            return len(submissions)

    async def _maybe_reset_stale(self) -> None:
        now = time.monotonic()
        throttle = max(self._settings.task_stale_seconds / 10, 30.0)
        if now - self._last_stale_check < throttle:
            return
        self._last_stale_check = now
        reset = await self.reset_stale()
        if reset:
            logger.warning("reset %d stale submission(s)", reset)
