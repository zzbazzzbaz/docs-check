"""行距口径（需求 FR-3.5）：`exact` / `atLeast` 必须**直接判不合格**，不是「无法判定」。

横跨所有作用域的共用判定在 `rules.support.para_line`；这里锁定它的行为，避免以后
有人把它改回"只看 `line_multiple`"而把明确违规记成无法判定。
"""

from __future__ import annotations

from tests.fixtures.base import BASE
from tests.fixtures.synth import line_exact
from tests.rules.case import CASE, issues_for
from thesischeck.rules.base import Verdict


def test_fixed_line_spacing_is_a_failure_not_undetermined() -> None:
    """把底稿某段行距改成固定值 20pt：行距规则要**报出来**，且是 FAIL。"""
    data = line_exact("中文摘要正文", 20.0).apply(BASE)
    hits = [issue for issue in issues_for(data) if issue.rule == "ABS-C-09"]
    assert hits, "固定值行距没有被任何行距规则报出"
    assert all(issue.verdict is Verdict.FAIL for issue in hits), (
        f"固定值行距应判 FAIL，实际 {[issue.verdict for issue in hits]}"
    )
    CASE("ABS-C-09", change=line_exact("中文摘要正文", 20.0), expect_only=["ABS-C-09"])


def test_base_uses_auto_multiple_line_spacing() -> None:
    """底稿的 1.5 倍行距是 `auto` 倍率，正常通过（反向确认判定没有恒真）。"""
    CASE("ABS-C-09", change=None, expect_only=[])
