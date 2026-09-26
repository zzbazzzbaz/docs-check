"""参考文献规则 REF-01 ~ REF-13、REF-21、REF-22 用例：每条一个命中 + 一个底稿合规。"""

from __future__ import annotations

import pytest

from tests.fixtures.synth import (
    Deviation,
    alignment,
    delete,
    ea,
    insert_blank_after,
    insert_line_after,
    line_spacing,
    run_replace,
    run_text,
    size,
    west,
)
from tests.rules.case import CASE

HITS: list[tuple[str, Deviation, list[str]]] = [
    ("REF-01", run_text("参考文献标题", "参考文献", "参考 文献"), ["REF-01"]),
    ("REF-02", ea("参考文献标题", "仿宋"), ["REF-02"]),
    ("REF-03", size("参考文献标题", 14), ["REF-03"]),
    ("REF-04", alignment("参考文献标题", "left"), ["REF-04"]),
    ("REF-05", insert_blank_after("参考文献标题"), ["REF-05"]),
    ("REF-06", ea("文献条目", "仿宋"), ["REF-06"]),
    ("REF-07", west("文献条目", "宋体"), ["REF-07"]),
    ("REF-08", size("文献条目", 14), ["REF-08"]),
    ("REF-09", line_spacing("文献条目", 2.0), ["REF-09"]),
    # 编号后多 1 个空格：编号仍可解析，连续性不受影响（REF-10 与 REF-11 不重复报）
    ("REF-10", run_replace("文献条目", "[1]", "[1] ", "[1]  "), ["REF-10"]),
    # 把 [2] 改成 [3]：跳号，由 REF-11 报
    ("REF-11", run_replace("文献条目", "[2]", "[2]", "[3]"), ["REF-11"]),
    ("REF-12", run_replace("文献条目", "[1]", "[M]", "[C]"), ["REF-12"]),
    (
        "REF-13",
        run_text("文献条目", "[2]", "[2] 严蔚敏，吴伟民.数据结构[M].北京：清华大学出版社，1997：35-37."),
        ["REF-13"],
    ),
    # 区内插入一条「有类型标识但没有编号」的条目：REF-21 报，REF-10 让开
    ("REF-21", insert_line_after("文献条目2", "无编号.某文献[M].北京：某社，2000：1."), ["REF-21"]),
    ("REF-22", delete("文献条目"), ["REF-22"]),
]


@pytest.mark.parametrize(("rule_id", "change", "expected"), HITS, ids=[row[0] for row in HITS])
def test_references_hit(rule_id: str, change: Deviation, expected: list[str]) -> None:
    CASE(rule_id, change=change, expect_only=expected)


@pytest.mark.parametrize("rule_id", [row[0] for row in HITS])
def test_references_pass_on_base(rule_id: str) -> None:
    CASE(rule_id, change=None, expect_only=[])
