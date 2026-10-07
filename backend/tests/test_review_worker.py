"""审核 worker：领取、重试上限、启动恢复、stale 重置（submissions 单表状态机）。"""

from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
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


async def test_process_next_processes_each_submission_once(client, session, worker):
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

    # 前两次异常 → 回 pending（attempts 递增、task_error 记录、started_at 清空）
    for attempt in (1, 2):
        assert await worker.process_next() is True
        submission = await _fresh_submission(session, submission_id)
        assert submission.status == "pending", attempt
        assert submission.attempts == attempt
        assert submission.task_error == "RuntimeError: boom"
        assert submission.started_at is None

    # 第三次达上限 → failed + 通用原因、task_error 保留、finished_at 落库、文件清理
    assert await worker.process_next() is True
    submission = await _fresh_submission(session, submission_id)
    assert submission.status == "failed"
    assert submission.attempts == 3
    assert submission.error_message == GENERIC_FAILED_MESSAGE
    assert submission.task_error == "RuntimeError: boom"
    assert submission.finished_at is not None
    assert not storage.submission_dir(submission_id).exists()


async def test_recover_stuck_resets_processing(session, session_factory, storage):
    user = await make_user(session, "stuck")
    user_id = user.id
    assert user_id is not None
    submission = Submission(
        student_id=user_id,
        original_filename="a.docx",
        status="processing",
        attempts=1,
        started_at=datetime.now(UTC),
        storage_dir="s/1",
    )
    session.add(submission)
    await session.commit()
    submission_id = submission.id
    assert submission_id is not None

    worker = _make_worker(session_factory, storage, ReviewRunner())
    assert await worker.recover_stuck() == 1

    submission = await _fresh_submission(session, submission_id)
    assert submission.status == "pending"
    assert submission.started_at is None


async def test_reset_stale_only_touches_old_processing(session, session_factory, storage):
    user = await make_user(session, "stale")
    user_id = user.id
    assert user_id is not None
    settings = get_settings()

    fresh = Submission(
        student_id=user_id,
        original_filename="fresh.docx",
        status="processing",
        attempts=1,
        started_at=datetime.now(UTC),
        storage_dir="s/1",
    )
    old = Submission(
        student_id=user_id,
        original_filename="old.docx",
        status="processing",
        attempts=1,
        started_at=datetime.now(UTC) - timedelta(seconds=settings.task_stale_seconds + 60),
        storage_dir="s/2",
    )
    session.add(fresh)
    session.add(old)
    await session.commit()
    fresh_id = fresh.id
    old_id = old.id
    assert fresh_id is not None
    assert old_id is not None

    worker = _make_worker(session_factory, storage, ReviewRunner())
    assert await worker.reset_stale() == 1

    assert (await _fresh_submission(session, old_id)).status == "pending"
    assert (await _fresh_submission(session, fresh_id)).status == "processing"
