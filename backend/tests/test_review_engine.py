"""引擎适配：run_review 输出形状、坏文档拒绝、runner 线程池包装。"""

import pytest

from app.infrastructure.review.engine import ReviewRejected, run_review
from app.infrastructure.review.runner import ReviewRunner
from tests.factories import corrupt_docx_bytes, minimal_docx_bytes


def test_run_review_minimal_docx_returns_outcome():
    outcome = run_review(minimal_docx_bytes())

    assert set(outcome.counts) == {"fail", "undetermined", "not_run", "unrecognised"}
    assert isinstance(outcome.by_scope, dict)
    assert outcome.ruleset_version
    assert outcome.marked_docx[:2] == b"PK"  # 标注版本身是 docx（zip）
    assert "summary" in outcome.issues_json
    assert "problems" in outcome.issues_json


def test_run_review_rejects_corrupt_docx():
    with pytest.raises(ReviewRejected) as exc:
        run_review(corrupt_docx_bytes())

    message = str(exc.value)
    assert message  # 中文可读原因，非空
    assert ".docx" in message


async def test_runner_returns_outcome_off_event_loop():
    outcome = await ReviewRunner().run(minimal_docx_bytes())

    assert outcome.ruleset_version
    assert outcome.marked_docx.startswith(b"PK")


async def test_runner_propagates_rejection():
    with pytest.raises(ReviewRejected):
        await ReviewRunner().run(corrupt_docx_bytes())
