"""封面规则 COV-01 ~ COV-16 用例：每条一个命中 + 一个底稿合规。"""

from __future__ import annotations

import pytest

from tests.fixtures.synth import Deviation, alignment, bold, ea, run_bold, run_ea, run_size, run_text, size
from tests.rules.case import CASE

# (规则号, 命中用的偏差, 期望只报的规则号)
# COV-13「五行一致」与逐行规则天然重叠：任一行偏离期望值，既违反 COV-10/11/12 又违反
# COV-13，无法只报 COV-13（规则文档未定义抑制口径，按字面实现并记录）。
HITS: list[tuple[str, Deviation, list[str]]] = [
    ("COV-01", ea("本科生毕业设计行", "仿宋"), ["COV-01"]),
    ("COV-02", size("本科生毕业设计行", 42), ["COV-02"]),
    ("COV-03", alignment("本科生毕业设计行", "left"), ["COV-03"]),
    ("COV-04", run_text("题目行", "题", "题  目："), ["COV-04"]),
    ("COV-05", run_ea("题目行", "题", "宋体"), ["COV-05"]),
    ("COV-06", run_size("题目行", "题", 14), ["COV-06"]),
    ("COV-07", run_bold("题目行", "题", False), ["COV-07"]),
    ("COV-08", run_ea("题目行", "基于", "宋体"), ["COV-08"]),
    ("COV-09", run_size("题目行", "基于", 20), ["COV-09"]),
    ("COV-10", ea("信息行", "宋体"), ["COV-10"]),
    ("COV-11", size("信息行", 14), ["COV-11"]),
    ("COV-12", bold("信息行", False), ["COV-12"]),
    ("COV-13", run_bold("学生姓名行", "学生姓名", False), ["COV-12", "COV-13"]),
    ("COV-14", ea("日期行", "宋体"), ["COV-14"]),
    ("COV-15", size("日期行", 14), ["COV-15"]),
    ("COV-16", bold("日期行", False), ["COV-16"]),
]


@pytest.mark.parametrize(("rule_id", "change", "expected"), HITS, ids=[row[0] for row in HITS])
def test_cover_hit(rule_id: str, change: Deviation, expected: list[str]) -> None:
    CASE(rule_id, change=change, expect_only=expected)


@pytest.mark.parametrize("rule_id", [row[0] for row in HITS])
def test_cover_pass_on_base(rule_id: str) -> None:
    CASE(rule_id, change=None, expect_only=[])
