"""规则用例框架：在底稿上声明一个偏差，断言**只报这一条**。

`expect_only` 是本脚手架的精髓：它不只断言"期望的规则命中"，还断言**没有别的规则被牵连**
（规则互相干扰、改一处引发别处误报都会被它抓住）。各条规则都按同一形态往里填。

用法::

    CASE("ABS-C-02", change=ea("中文摘要标题", "仿宋"), expect_only=["ABS-C-02"])
    CASE("ABS-C-02", change=None, expect_only=[])          # 通过样例：底稿零问题
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path

from tests.fixtures.base import BASE
from tests.fixtures.synth import Deviation
from thesischeck.parse.document import parse_document
from thesischeck.parse.package import Package
from thesischeck.rules import REGISTRY, run_rules
from thesischeck.rules.base import Issue, Verdict
from thesischeck.semantics.blocks import tag_context


def issues_for(data: bytes) -> list[Issue]:
    """解析一份 docx 字节并跑完全部已注册规则。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "case.docx"
        path.write_bytes(data)
        with Package.open(path) as pkg:
            document = parse_document(pkg)
    return run_rules(tag_context(document), REGISTRY)


def CASE(
    rule_id: str,
    *,
    base: bytes = BASE,
    change: Deviation | None = None,
    expect_only: Sequence[str] = (),
) -> None:
    """跑一个用例：`change` 应用到 `base` 后，报告里**只**应出现 `expect_only` 的规则号。

    `rule_id` 只用于失败信息，便于在 197 条用例里一眼找到是哪条。
    """
    data = change.apply(base) if change is not None else base
    reported = sorted(
        {issue.rule for issue in issues_for(data) if issue.verdict in (Verdict.FAIL, Verdict.UNDETERMINED)}
    )
    assert reported == sorted(expect_only), (
        f"用例 {rule_id}：期望只报 {sorted(expect_only)}，实际报 {reported}"
    )
