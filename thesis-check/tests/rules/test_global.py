"""整体规则 GLB-01 ~ GLB-28 用例：每条一个命中 + 一个底稿合规。

- 页眉 / 页脚 / 页面设置 / 分页类规则作用在分节上，用 `synth` 的分节 / 部件编辑构造命中。
- `GLB-27`（模块顺序）单独测：模块区间由作用域分区固定了顺序，把两个模块标题对调会连带
  改变分区，无法只报一条；故直接断言 `module_order` 判定函数（识别器与判定器分离）。
"""

from __future__ import annotations

import pytest

from tests.fixtures.synth import (
    Deviation,
    add_footer_reference,
    auto_numbering,
    combined,
    dangling_footer_reference,
    delete,
    footer_align,
    footer_page_size,
    footer_page_west,
    header_align,
    header_ea,
    header_size,
    header_text,
    insert_line_before,
    page_margin,
    page_number_format,
    page_size,
    remove_footer_reference,
    remove_header_reference,
    remove_section_break,
)
from tests.rules.case import CASE

HITS: list[tuple[str, Deviation, list[str]]] = [
    ("GLB-01", header_text("山东石油化工学院本科毕业设计（论文）X"), ["GLB-01"]),
    ("GLB-02", header_ea("仿宋"), ["GLB-02"]),
    ("GLB-03", header_size(14), ["GLB-03"]),
    ("GLB-04", header_align("left"), ["GLB-04"]),
    ("GLB-05", remove_header_reference(2), ["GLB-05"]),
    ("GLB-06", remove_footer_reference(5), ["GLB-06"]),
    ("GLB-07", page_number_format(5, "upperRoman"), ["GLB-07"]),
    ("GLB-08", footer_align("left"), ["GLB-08"]),
    ("GLB-09", footer_page_west("宋体"), ["GLB-09"]),
    ("GLB-10", footer_page_size(14), ["GLB-10"]),
    (
        "GLB-11",
        combined([add_footer_reference(1), dangling_footer_reference(2)]),
        ["GLB-11"],
    ),
    (
        "GLB-12",
        combined([add_footer_reference(2), dangling_footer_reference(3)]),
        ["GLB-12"],
    ),
    (
        "GLB-13",
        combined([add_footer_reference(3), dangling_footer_reference(4)]),
        ["GLB-13"],
    ),
    ("GLB-14", add_footer_reference(4), ["GLB-14"]),
    ("GLB-15", page_size(1), ["GLB-15"]),
    ("GLB-16", page_margin(1, "top", "1000"), ["GLB-16"]),
    ("GLB-17", page_margin(1, "bottom", "1000"), ["GLB-17"]),
    ("GLB-18", page_margin(1, "left", "1000"), ["GLB-18"]),
    ("GLB-19", page_margin(1, "right", "1000"), ["GLB-19"]),
    ("GLB-20", remove_section_break(1), ["GLB-20"]),
    ("GLB-21", remove_section_break(3), ["GLB-21"]),
    # 去掉「目录 → 正文」的分节符：目录与正文并入同一节后，目录也带上了页码
    # （GLB-14）——规则文档未定义抑制口径，按字面实现并记录
    ("GLB-22", remove_section_break(4), ["GLB-14", "GLB-22"]),
    ("GLB-23", insert_line_before("参考文献标题", "插入的正文段落。"), ["GLB-23"]),
    # 在致谢前插入一条文献 [3]：它落在参考文献区，且正文里没有 [3] 的引用，
    # 所以 REF-14 也报出（跨作用域耦合，按字面实现并记录）
    (
        "GLB-24",
        insert_line_before("致谢标题", "[3] 张三.测试文献[M].北京：某社，2000：1."),
        ["GLB-24", "REF-14"],
    ),
    ("GLB-25", insert_line_before("附录标题", "插入的致谢段落。"), ["GLB-25"]),
    ("GLB-26", delete("本科生毕业设计行"), ["GLB-26"]),
    # 反恒真：给正文段落加 Word 自动编号
    ("GLB-28", auto_numbering("正文段落"), ["GLB-28"]),
]


@pytest.mark.parametrize(("rule_id", "change", "expected"), HITS, ids=[row[0] for row in HITS])
def test_global_hit(rule_id: str, change: Deviation, expected: list[str]) -> None:
    CASE(rule_id, change=change, expect_only=expected)


@pytest.mark.parametrize("rule_id", [row[0] for row in HITS] + ["GLB-27"])
def test_global_pass_on_base(rule_id: str) -> None:
    CASE(rule_id, change=None, expect_only=[])


@pytest.mark.parametrize("target", ["正文段落", "文献条目", "附录子标题", "三级以下标题"])
def test_auto_numbering_paragraphs_are_left_to_glb28(target: str) -> None:
    """验收 6.1-8：自动编号段让开下游编号类规则（`TXT-19` / `REF-10` / `REF-11` / `APP-06`）。

    选择器过滤（需求 §3.4）生效时，这些段落只由 `GLB-28` 报出，下游规则不再给出错误的修改指令。
    """
    CASE("GLB-28", change=auto_numbering(target), expect_only=["GLB-28"])


def test_glb27_module_order_verdict() -> None:
    """GLB-27 判定：顺序正确放行，乱序报出（识别器与判定器分离，不靠 XML 构造）。"""
    from thesischeck.rules.document_wide import module_order

    ordered = ("封面", "中文摘要", "英文摘要", "目录", "正文", "参考文献", "致谢", "附录")
    assert module_order(ordered) == "顺序正确"
    swapped = ("封面", "中文摘要", "英文摘要", "目录", "正文", "致谢", "参考文献", "附录")
    assert module_order(swapped) == "模块顺序有误"
