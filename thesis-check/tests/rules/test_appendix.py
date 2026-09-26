"""附录规则 APP-01 ~ APP-18 用例：每条一个命中 + 一个底稿合规。"""

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
    outline_level,
    run_text,
    size,
    west,
)
from tests.rules.case import CASE

HITS: list[tuple[str, Deviation, list[str]]] = [
    ("APP-01", run_text("附录标题", "附", "附录"), ["APP-01"]),
    ("APP-02", ea("附录标题", "仿宋"), ["APP-02"]),
    ("APP-03", size("附录标题", 14), ["APP-03"]),
    ("APP-04", alignment("附录标题", "left"), ["APP-04"]),
    ("APP-05", insert_blank_after("附录标题"), ["APP-05"]),
    # 把 A 改成小写 a：编号由 APP-06 报（识别仍是「附录 + 非空白字符」）
    ("APP-06", run_text("附录子标题", "附录A", "附录a 名词术语及缩略词"), ["APP-06"]),
    # 反恒真：把子标题大纲级别从 2 级改成 3 级
    ("APP-13", outline_level("附录子标题", 2), ["APP-13"]),
    ("APP-14", ea("附录子标题", "宋体"), ["APP-14"]),
    ("APP-15", size("附录子标题", 12), ["APP-15"]),
    ("APP-16", west("附录子标题", "宋体"), ["APP-16"]),
    ("APP-17", line_spacing("附录子标题", 2.0), ["APP-17"]),
    ("APP-07", ea("附录正文", "仿宋"), ["APP-07"]),
    ("APP-08", west("附录正文", "宋体"), ["APP-08"]),
    ("APP-09", size("附录正文", 14), ["APP-09"]),
    ("APP-10", line_spacing("附录正文", 2.0), ["APP-10"]),
    ("APP-11", first_line("附录正文", 1), ["APP-11"]),
    ("APP-12", alignment("附录正文", "left"), ["APP-12"]),
    ("APP-18", delete("附录子标题"), ["APP-18"]),
]


@pytest.mark.parametrize(("rule_id", "change", "expected"), HITS, ids=[row[0] for row in HITS])
def test_appendix_hit(rule_id: str, change: Deviation, expected: list[str]) -> None:
    CASE(rule_id, change=change, expect_only=expected)


@pytest.mark.parametrize("rule_id", [row[0] for row in HITS])
def test_appendix_pass_on_base(rule_id: str) -> None:
    CASE(rule_id, change=None, expect_only=[])
