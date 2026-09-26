"""英文摘要规则 ABS-E-01 ~ ABS-E-22 用例：每条一个命中 + 一个底稿合规。

`ABS-E-22`（Keywords 行存在性）用「删掉 Keywords 行」构造命中，避免恒真。
"""

from __future__ import annotations

import pytest

from tests.fixtures.synth import (
    Deviation,
    alignment,
    bold,
    delete,
    first_line,
    insert_blank_after,
    line_spacing,
    run_bold,
    run_size,
    run_text,
    run_west,
    size,
    west,
)
from tests.rules.case import CASE

HITS: list[tuple[str, Deviation, list[str]]] = [
    ("ABS-E-01", run_text("英文摘要标题", "ABSTRACT", "Abstract"), ["ABS-E-01"]),
    ("ABS-E-02", west("英文摘要标题", "宋体"), ["ABS-E-02"]),
    ("ABS-E-03", size("英文摘要标题", 14), ["ABS-E-03"]),
    ("ABS-E-04", bold("英文摘要标题", False), ["ABS-E-04"]),
    ("ABS-E-05", alignment("英文摘要标题", "left"), ["ABS-E-05"]),
    ("ABS-E-06", insert_blank_after("英文摘要标题"), ["ABS-E-06"]),
    ("ABS-E-07", west("英文摘要正文", "宋体"), ["ABS-E-07"]),
    ("ABS-E-08", size("英文摘要正文", 14), ["ABS-E-08"]),
    ("ABS-E-09", line_spacing("英文摘要正文", 2.0), ["ABS-E-09"]),
    ("ABS-E-10", first_line("英文摘要正文", 1), ["ABS-E-10"]),
    ("ABS-E-11", insert_blank_after("英文摘要正文"), ["ABS-E-11"]),
    ("ABS-E-12", run_text("英文关键词行", "Keywords", "keywords："), ["ABS-E-12"]),
    ("ABS-E-13", run_west("英文关键词行", "Keywords", "宋体"), ["ABS-E-13"]),
    ("ABS-E-14", run_size("英文关键词行", "Keywords", 14), ["ABS-E-14"]),
    ("ABS-E-15", run_bold("英文关键词行", "Keywords", False), ["ABS-E-15"]),
    ("ABS-E-16", run_west("英文关键词行", "embedded", "宋体"), ["ABS-E-16"]),
    ("ABS-E-17", run_size("英文关键词行", "embedded", 14), ["ABS-E-17"]),
    ("ABS-E-18", line_spacing("英文关键词行", 2.0), ["ABS-E-18"]),
    ("ABS-E-19", first_line("英文关键词行", 1), ["ABS-E-19"]),
    (
        "ABS-E-20",
        run_text("英文关键词行", "embedded", "embedded system; monitoring; real time"),
        ["ABS-E-20"],
    ),
    (
        "ABS-E-21",
        run_text("英文关键词行", "embedded", "embedded system；monitoring；real time。"),
        ["ABS-E-21"],
    ),
    ("ABS-E-22", delete("英文关键词行"), ["ABS-E-22"]),
]


@pytest.mark.parametrize(("rule_id", "change", "expected"), HITS, ids=[row[0] for row in HITS])
def test_abs_e_hit(rule_id: str, change: Deviation, expected: list[str]) -> None:
    CASE(rule_id, change=change, expect_only=expected)


@pytest.mark.parametrize("rule_id", [row[0] for row in HITS])
def test_abs_e_pass_on_base(rule_id: str) -> None:
    CASE(rule_id, change=None, expect_only=[])
