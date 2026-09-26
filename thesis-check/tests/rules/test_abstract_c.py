"""示范规则 `ABS-C-02`（中文摘要标题的中文字体 = 黑体）——证明脚手架可用。

一个通过样例（底稿零问题）+ 一个命中样例（把标题中文字体改成仿宋），
命中样例断言**只报这一条**。批 1 的其余规则照此形态添加。
"""

from __future__ import annotations

from tests.fixtures.synth import ea
from tests.rules.case import CASE


def test_abs_c_02_hits_when_title_font_is_wrong() -> None:
    CASE("ABS-C-02", change=ea("中文摘要标题", "仿宋"), expect_only=["ABS-C-02"])


def test_abs_c_02_silent_on_compliant_base() -> None:
    CASE("ABS-C-02", change=None, expect_only=[])
