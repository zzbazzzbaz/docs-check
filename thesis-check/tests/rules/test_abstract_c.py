"""中文摘要规则 ABS-C-01 ~ ABS-C-25 用例：每条一个命中 + 一个底稿合规。

覆盖示范规则 `ABS-C-02`（原 `test_abstract_c.py` 的两个用例并入本表）。
`ABS-C-25`（关键词行存在性）用「删掉关键词行」构造命中，避免恒真。
"""

from __future__ import annotations

import pytest

from tests.fixtures.synth import (
    Deviation,
    alignment,
    delete,
    ea,
    first_line,
    insert_blank_after,
    line_spacing,
    run_bold,
    run_ea,
    run_size,
    run_text,
    run_west,
    size,
    west,
)
from tests.rules.case import CASE

HITS: list[tuple[str, Deviation, list[str]]] = [
    ("ABS-C-01", run_text("中文摘要标题", "摘", "摘  要"), ["ABS-C-01"]),
    ("ABS-C-02", ea("中文摘要标题", "仿宋"), ["ABS-C-02"]),
    ("ABS-C-03", size("中文摘要标题", 14), ["ABS-C-03"]),
    ("ABS-C-04", alignment("中文摘要标题", "left"), ["ABS-C-04"]),
    ("ABS-C-05", insert_blank_after("中文摘要标题"), ["ABS-C-05"]),
    ("ABS-C-06", ea("中文摘要正文", "仿宋"), ["ABS-C-06"]),
    ("ABS-C-07", west("中文摘要正文", "宋体"), ["ABS-C-07"]),
    ("ABS-C-08", size("中文摘要正文", 14), ["ABS-C-08"]),
    ("ABS-C-09", line_spacing("中文摘要正文", 2.0), ["ABS-C-09"]),
    ("ABS-C-10", first_line("中文摘要正文", 1), ["ABS-C-10"]),
    ("ABS-C-11", insert_blank_after("中文摘要正文末段"), ["ABS-C-11"]),
    ("ABS-C-12", run_text("中文关键词行", "关键词", "关键词:"), ["ABS-C-12"]),
    ("ABS-C-13", run_ea("中文关键词行", "关键词", "仿宋"), ["ABS-C-13"]),
    ("ABS-C-14", run_size("中文关键词行", "关键词", 14), ["ABS-C-14"]),
    ("ABS-C-15", run_bold("中文关键词行", "关键词", False), ["ABS-C-15"]),
    ("ABS-C-16", run_ea("中文关键词行", "嵌入式", "仿宋"), ["ABS-C-16"]),
    ("ABS-C-17", run_west("中文关键词行", "嵌入式", "宋体"), ["ABS-C-17"]),
    ("ABS-C-18", run_size("中文关键词行", "嵌入式", 14), ["ABS-C-18"]),
    ("ABS-C-19", line_spacing("中文关键词行", 2.0), ["ABS-C-19"]),
    ("ABS-C-20", first_line("中文关键词行", 1), ["ABS-C-20"]),
    ("ABS-C-21", alignment("中文关键词行", "left"), ["ABS-C-21"]),
    ("ABS-C-22", run_text("中文关键词行", "嵌入式", "嵌入式系统；；ARM；实时性"), ["ABS-C-22"]),
    ("ABS-C-23", run_text("中文关键词行", "嵌入式", "嵌入式系统；ARM；实时性。"), ["ABS-C-23"]),
    ("ABS-C-24", run_text("中文关键词行", "嵌入式", "嵌入式系统；实时性"), ["ABS-C-24"]),
    ("ABS-C-25", delete("中文关键词行"), ["ABS-C-25"]),
]


@pytest.mark.parametrize(("rule_id", "change", "expected"), HITS, ids=[row[0] for row in HITS])
def test_abs_c_hit(rule_id: str, change: Deviation, expected: list[str]) -> None:
    CASE(rule_id, change=change, expect_only=expected)


@pytest.mark.parametrize("rule_id", [row[0] for row in HITS])
def test_abs_c_pass_on_base(rule_id: str) -> None:
    CASE(rule_id, change=None, expect_only=[])
