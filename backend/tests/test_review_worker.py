"""任务 worker：领取、重试上限、启动恢复、stale 重置。"""

from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.core.config import get_settings
from app.infrastructure.db.models.review_task import ReviewTask
from app.infrastructure.db.models.submission import Submission
from app.infrastructure.review.runner import ReviewRunner
from app.services.tasks.review_worker import GENERIC_FAILED_MESSAGE, ReviewWorker
from tests.factories import minimal_docx_bytes
from tests.helpers import auth_headers, make_user

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class _FailingRunner:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def run(self, data: bytes):
        raise self._exc


def _make_worker(session_factory, storage, runner, **settings_overrides) -> ReviewWorker:
    settings = get_settings().model_copy(update=settings_overrides)
    return ReviewWorker(
        session_factory=session_factory, runner=runner, storage=storage, settings=settings
    )


async def _fresh_task(session, submission_id: int) -> ReviewTask:
    session.expire_all()
    return (
        await session.exec(select(ReviewTask).where(ReviewTask.submission_id == submission_id))
    ).one()


async def _fresh_submission(session, submission_id: int) -> Submission:
    session.expire_all()
    submission = await session.get(Submission, submission_id)
    assert submission is not None
    return submission


async def _upload(client, headers) -> int:
    r = await client.post(
        "/api/v1/submissions",
        files={"file": ("论文.docx", minimal_docx_bytes(), DOCX_MIME)},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    return r.json()["id"]


async def test_process_next_processes_each_task_once(client, session, worker):
    await make_user(session, "many")
    headers = await auth_headers(client, "many")
    await _upload(client, headers)
    await _upload(client, headers)

    assert await worker.process_next() is True
    assert await worker.process_next() is True
    assert await worker.process_next() is False


async def test_infra_error_retries_then_fails(client, session, session_factory, storage):
    await make_user(session, "retry")
    headers = await auth_headers(client, "retry")
    submission_id = await _upload(client, headers)

    runner = _FailingRunner(RuntimeError("boom"))
    worker = _make_worker(session_factory, storage, runner, task_poll_interval_seconds=0.01)

    # 前两次异常 → 回 pending（attempts 递增、error 记录、提交回 pending）
    for attempt in (1, 2):
        assert await worker.process_next() is True
        task = await _fresh_task(session, submission_id)
        assert task.status == "pending", attempt
        assert task.attempts == attempt
        assert task.error == "RuntimeError: boom"
        assert (await _fresh_submission(session, submission_id)).status == "pending"

    # 第三次达上限 → 任务 finished、提交 failed + 通用原因、文件清理
    assert await worker.process_next() is True
    task = await _fresh_task(session, submission_id)
    assert task.status == "finished"
    assert task.attempts == 3
    submission = await _fresh_submission(session, submission_id)
    assert submission.status == "failed"
    assert submission.error_message == GENERIC_FAILED_MESSAGE
    assert not storage.submission_dir(submission_id).exists()


async def test_recover_stuck_resets_processing(session, session_factory, storage):
    user = await make_user(session, "stuck")
    user_id = user.id
    assert user_id is not None
    submission = Submission(
        student_id=user_id, original_filename="a.docx", status="processing", storage_dir="s/1"
    )
    session.add(submission)
    await session.flush()
    submission_id = submission.id
    assert submission_id is not None
    task = ReviewTask(
        submission_id=submission_id,
        status="processing",
        attempts=1,
        started_at=datetime.now(UTC),
    )
    session.add(task)
    await session.commit()

    worker = _make_worker(session_factory, storage, ReviewRunner())
    assert await worker.recover_stuck() == 1

    assert (await _fresh_task(session, submission_id)).status == "pending"
    assert (await _fresh_submission(session, submission_id)).status == "pending"


async def test_reset_stale_only_touches_old_processing_tasks(session, session_factory, storage):
    user = await make_user(session, "stale")
    user_id = user.id
    assert user_id is not None
    settings = get_settings()

    fresh_submission = Submission(
        student_id=user_id, original_filename="fresh.docx", status="processing", storage_dir="s/1"
    )
    old_submission = Submission(
        student_id=user_id, original_filename="old.docx", status="processing", storage_dir="s/2"
    )
    session.add(fresh_submission)
    session.add(old_submission)
    await session.flush()
    fresh_id = fresh_submission.id
    old_id = old_submission.id
    assert fresh_id is not None
    assert old_id is not None
    session.add(
        ReviewTask(
            submission_id=fresh_id,
            status="processing",
            attempts=1,
            started_at=datetime.now(UTC),
        )
    )
    session.add(
        ReviewTask(
            submission_id=old_id,
            status="processing",
            attempts=1,
            started_at=datetime.now(UTC) - timedelta(seconds=settings.task_stale_seconds + 60),
        )
    )
    await session.commit()

    worker = _make_worker(session_factory, storage, ReviewRunner())
    assert await worker.reset_stale() == 1

    assert (await _fresh_task(session, old_id)).status == "pending"
    assert (await _fresh_submission(session, old_id)).status == "pending"
    assert (await _fresh_task(session, fresh_id)).status == "processing"
    assert (await _fresh_submission(session, fresh_id)).status == "processing"
