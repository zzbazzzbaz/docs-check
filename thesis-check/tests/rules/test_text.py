"""正文规则 TXT-01 ~ TXT-51（本批 46 条）用例：每条一个命中 + 一个底稿合规。

题注位置（`TXT-38/44`）用删掉图块 / 在表题与表格之间插空段构造命中；公式编号
（`TXT-32`）用清空编号文本构造，二者都不牵连其它规则。
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
    page_break,
    run_replace,
    run_size,
    run_text,
    run_va,
    run_west,
    size,
    table_border,
    west,
)
from tests.rules.case import CASE

HITS: list[tuple[str, Deviation, list[str]]] = [
    ("TXT-01", run_text("第一章标题", "第一章", "第一章 绪论"), ["TXT-01"]),
    ("TXT-02", ea("第一章标题", "仿宋"), ["TXT-02"]),
    ("TXT-03", size("第一章标题", 14), ["TXT-03"]),
    ("TXT-04", alignment("第一章标题", "left"), ["TXT-04"]),
    ("TXT-05", line_spacing("第一章标题", 2.0), ["TXT-05"]),
    ("TXT-06", insert_blank_after("第一章标题"), ["TXT-06"]),
    ("TXT-07", page_break("第二章标题", False), ["TXT-07"]),
    ("TXT-08", run_text("二级标题", "1.1", "1.1研究背景"), ["TXT-08"]),
    ("TXT-09", ea("二级标题", "仿宋"), ["TXT-09"]),
    ("TXT-10", size("二级标题", 12), ["TXT-10"]),
    ("TXT-11", west("二级标题", "宋体"), ["TXT-11"]),
    ("TXT-12", line_spacing("二级标题", 2.0), ["TXT-12"]),
    ("TXT-13", run_text("三级标题", "1.1", "1.1.1现状分析"), ["TXT-13"]),
    ("TXT-14", ea("三级标题", "仿宋"), ["TXT-14"]),
    ("TXT-15", size("三级标题", 14), ["TXT-15"]),
    ("TXT-16", west("三级标题", "宋体"), ["TXT-16"]),
    ("TXT-17", line_spacing("三级标题", 2.0), ["TXT-17"]),
    ("TXT-18", first_line("三级标题", 1), ["TXT-18"]),
    ("TXT-19", run_text("三级以下标题", "（1）", "1、关键技术"), ["TXT-19"]),
    ("TXT-20", ea("三级以下标题", "仿宋"), ["TXT-20"]),
    ("TXT-21", size("三级以下标题", 14), ["TXT-21"]),
    ("TXT-22", west("三级以下标题", "宋体"), ["TXT-22"]),
    ("TXT-23", line_spacing("三级以下标题", 2.0), ["TXT-23"]),
    ("TXT-24", first_line("三级以下标题", 1), ["TXT-24"]),
    ("TXT-25", ea("正文段落", "仿宋"), ["TXT-25"]),
    ("TXT-26", west("正文段落", "宋体"), ["TXT-26"]),
    ("TXT-27", size("正文段落", 14), ["TXT-27"]),
    ("TXT-28", first_line("正文段落", 1), ["TXT-28"]),
    ("TXT-29", line_spacing("正文段落", 2.0), ["TXT-29"]),
    ("TXT-30", run_va("引用标注", "[1]", "baseline"), ["TXT-30"]),
    ("TXT-31", run_west("引用标注", "[2]", "宋体"), ["TXT-31"]),
    ("TXT-32", run_text("公式段落", "(1-1)", ""), ["TXT-32"]),
    ("TXT-33", alignment("公式段落", "left"), ["TXT-33"]),
    ("TXT-34", run_size("公式段落", "(1-1)", 14), ["TXT-34"]),
    ("TXT-35", run_west("公式段落", "(1-1)", "宋体"), ["TXT-35"]),
    ("TXT-37", run_text("图题", "图", "图 1-1 系统总体结构"), ["TXT-37"]),
    ("TXT-38", delete("图块"), ["TXT-38"]),
    ("TXT-39", alignment("图题", "left"), ["TXT-39"]),
    ("TXT-40", ea("图题", "仿宋"), ["TXT-40"]),
    ("TXT-41", run_text("图题", "图", "图1-1系统总体结构"), ["TXT-41"]),
    ("TXT-43", run_text("表题", "表", "表 1-1 主要器件清单"), ["TXT-43"]),
    ("TXT-44", insert_blank_after("表题"), ["TXT-44"]),
    ("TXT-45", alignment("表题", "left"), ["TXT-45"]),
    ("TXT-46", ea("表题", "仿宋"), ["TXT-46"]),
    ("TXT-47", run_text("表题", "表", "表1-1主要器件清单"), ["TXT-47"]),
    # ── 批 2（FR-8）：必须有引用 / 三线表 / 公式编号 ──
    # 反恒真：删掉正文里的公式引用（题注自身不算数），TXT-36 必须报出
    ("TXT-36", run_replace("结果引用段落", "本文", "式(1-1)", ""), ["TXT-36"]),
    # 反恒真：删掉正文里的图引用，图题里的「图1-1」不参与搜索
    ("TXT-42", run_replace("结果引用段落", "本文", "图1-1", ""), ["TXT-42"]),
    # 反恒真：删掉正文里的表引用，表题里的「表1-1」不参与搜索
    ("TXT-48", run_replace("结果引用段落", "本文", "表1-1", ""), ["TXT-48"]),
    # 给三线表加一条竖线：不再是三线表
    ("TXT-49", table_border("insideV", "single"), ["TXT-49"]),
    # 序号跳号：把 (1-1) 改成 (1-2)，同时把正文引用一并改成式(1-2)，只由 TXT-52 报出
    (
        "TXT-52",
        combined(
            [
                run_replace("公式段落", "(1-1)", "(1-1)", "(1-2)"),
                run_replace("结果引用段落", "本文", "式(1-1)", "式(1-2)"),
            ]
        ),
        ["TXT-52"],
    ),
    ("TXT-51", run_text("第三章标题", "第三章", "第三篇  系统设计"), ["TXT-51"]),
]


@pytest.mark.parametrize(("rule_id", "change", "expected"), HITS, ids=[row[0] for row in HITS])
def test_text_hit(rule_id: str, change: Deviation, expected: list[str]) -> None:
    CASE(rule_id, change=change, expect_only=expected)


@pytest.mark.parametrize("rule_id", [row[0] for row in HITS])
def test_text_pass_on_base(rule_id: str) -> None:
    CASE(rule_id, change=None, expect_only=[])
