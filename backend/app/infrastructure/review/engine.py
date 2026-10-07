"""thesischeck 引擎适配：本项目唯一允许 import thesischeck 的模块。"""

from dataclasses import dataclass
from typing import Any

from thesischeck.errors import ThesisCheckError
from thesischeck.pipeline import review_bytes


class ReviewRejected(Exception):
    """坏文档（坏输入/解析失败），message 为引擎中文原因，可直接展示。"""


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    """一次成功审核的产物（全部在内存）。"""

    issues_json: dict[str, Any]
    marked_docx: bytes
    counts: dict[str, int]
    by_scope: dict[str, dict[str, int]]
    ruleset_version: str


def run_review(data: bytes) -> ReviewOutcome:
    """同步执行审核；坏文档抛 `ReviewRejected`（中文原因可直接展示）。"""
    try:
        payload = review_bytes(data)
    except ThesisCheckError as exc:
        raise ReviewRejected(str(exc)) from exc
    report = payload.report
    return ReviewOutcome(
        issues_json=report.to_json(),
        marked_docx=payload.marked_docx,
        counts=report.counts(),
        by_scope=report.by_scope(),
        ruleset_version=report.ruleset_version,
    )
