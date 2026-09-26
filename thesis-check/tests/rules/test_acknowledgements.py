"""致谢规则 ACK-01 ~ ACK-12 用例：每条一个命中 + 一个底稿合规。"""

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
    run_text,
    size,
    west,
)
from tests.rules.case import CASE

HITS: list[tuple[str, Deviation, list[str]]] = [
    ("ACK-01", run_text("致谢标题", "致", "致谢"), ["ACK-01"]),
    ("ACK-02", ea("致谢标题", "仿宋"), ["ACK-02"]),
    ("ACK-03", size("致谢标题", 14), ["ACK-03"]),
    ("ACK-04", alignment("致谢标题", "left"), ["ACK-04"]),
    ("ACK-05", insert_blank_after("致谢标题"), ["ACK-05"]),
    ("ACK-06", ea("致谢正文", "仿宋"), ["ACK-06"]),
    ("ACK-07", west("致谢正文", "宋体"), ["ACK-07"]),
    ("ACK-08", size("致谢正文", 14), ["ACK-08"]),
    ("ACK-09", line_spacing("致谢正文", 2.0), ["ACK-09"]),
    ("ACK-10", first_line("致谢正文", 1), ["ACK-10"]),
    ("ACK-11", alignment("致谢正文", "left"), ["ACK-11"]),
    ("ACK-12", delete("致谢正文"), ["ACK-12"]),
]


@pytest.mark.parametrize(("rule_id", "change", "expected"), HITS, ids=[row[0] for row in HITS])
def test_acknowledgements_hit(rule_id: str, change: Deviation, expected: list[str]) -> None:
    CASE(rule_id, change=change, expect_only=expected)


@pytest.mark.parametrize("rule_id", [row[0] for row in HITS])
def test_acknowledgements_pass_on_base(rule_id: str) -> None:
    CASE(rule_id, change=None, expect_only=[])
