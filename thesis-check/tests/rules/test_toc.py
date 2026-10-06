"""目录规则 TOC-01 ~ TOC-18 用例：每条一个命中 + 一个底稿合规。

`TOC-15`（必须有目录条目）用「把 `toc 2/3` 样式改名 + 删掉一级条目」构造命中：
不依赖条目、TOC 域仍在，只有本规则报出。
"""

from __future__ import annotations

import pytest

from tests.fixtures.synth import (
    Deviation,
    alignment,
    combined,
    delete,
    ea,
    first_line,
    insert_blank_after,
    line_spacing,
    rename_style,
    run_bold,
    run_text,
    size,
    west,
)
from tests.rules.case import CASE

HITS: list[tuple[str, Deviation, list[str]]] = [
    ("TOC-01", run_text("目录标题", "目", "目  录"), ["TOC-01"]),
    ("TOC-02", ea("目录标题", "仿宋"), ["TOC-02"]),
    ("TOC-03", size("目录标题", 14), ["TOC-03"]),
    ("TOC-04", alignment("目录标题", "left"), ["TOC-04"]),
    ("TOC-05", line_spacing("目录标题", 2.0), ["TOC-05"]),
    ("TOC-06", insert_blank_after("目录标题"), ["TOC-06"]),
    ("TOC-07", ea("目录二级条目", "仿宋"), ["TOC-07"]),
    ("TOC-08", west("目录二级条目", "宋体"), ["TOC-08"]),
    ("TOC-09", size("目录二级条目", 14), ["TOC-09"]),
    ("TOC-10", line_spacing("目录二级条目", 2.0), ["TOC-10"]),
    ("TOC-11", run_bold("目录二级条目", "1.1", True), ["TOC-11"]),
    ("TOC-12", run_text("目录一级条目", "第一章", "第一章 绪论"), ["TOC-12"]),
    ("TOC-13", run_text("目录二级条目", "1.1", "1.1研究背景与意义"), ["TOC-13"]),
    ("TOC-14", run_text("目录三级条目", "1.1.1", "1.1.1国内研究现状"), ["TOC-14"]),
    ("TOC-16", first_line("目录一级条目", 2), ["TOC-16"]),
    ("TOC-17", first_line("目录二级条目", 1), ["TOC-17"]),
    ("TOC-18", first_line("目录三级条目", 2), ["TOC-18"]),
    (
        "TOC-15",
        combined(
            [
                rename_style("toc 1", "目录 1"),
                rename_style("toc 2", "目录 2"),
                rename_style("toc 3", "目录 3"),
                delete("目录一级条目"),
            ]
        ),
        ["TOC-15"],
    ),
]


@pytest.mark.parametrize(("rule_id", "change", "expected"), HITS, ids=[row[0] for row in HITS])
def test_toc_hit(rule_id: str, change: Deviation, expected: list[str]) -> None:
    CASE(rule_id, change=change, expect_only=expected)


@pytest.mark.parametrize("rule_id", [row[0] for row in HITS])
def test_toc_pass_on_base(rule_id: str) -> None:
    CASE(rule_id, change=None, expect_only=[])
