"""正文规则 TXT-01 ~ TXT-51（46 条：剔除第二批 5 条与渲染通道 1 条）。

标题对象：一级按**文本** `第X章`（宽松锚点，不依赖大纲级别）取，二 / 三 / 三级以下按
**大纲级别 / 样式名**取；属性一律走有效格式。编号形态与空格、题注位置、公式编号、
存在性写代码，其余都是一行数据。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from operator import attrgetter
from typing import Any

from ..parse.model import Run
from ..semantics import select
from ..semantics.blocks import Block, Scope
from ..semantics.matchers import chapter_no, is_citation
from .base import Comparison, Rule, ToleranceKey
from .support import (
    H1_TEXT_SHAPE,
    H2_TEXT_SHAPE,
    H3_TEXT_SHAPE,
    BlockSel,
    blanks_after,
    cjk_of,
    count,
    first_cjk_font,
    flag,
    found,
    gap_of,
    index_of,
    neighbour_flag,
    para_align,
    para_first_line,
    para_line,
    run_font,
    shape_verdict,
    visible_of,
    west_of,
)

_H4_SHAPE = re.compile(r"（\d+）.*")
_FIG_FORMAT = re.compile(r"图\d+-\d+.*")
_TAB_FORMAT = re.compile(r"表\d+-\d+.*")
_FIG_NO = re.compile(r"^图\s*\d+\s*-\s*\d+")
_TAB_NO = re.compile(r"^表\s*\d+\s*-\s*\d+")
_FORMULA_NO = re.compile(r"\(\d+-\d+\)")


# ── 对象识别（正文作用域内）─────────────────────────────────────


def _in_body(sel: BlockSel) -> BlockSel:
    def pick(blocks: Sequence[Block]) -> tuple[Block, ...]:
        return select.by_scope(sel(blocks), Scope.BODY)

    return pick


BODY_H1 = select.chapters
BODY_H2 = _in_body(select.h2)
BODY_H3 = _in_body(select.h3)
BODY_H4 = _in_body(select.h4)
BODY_H4_MANUAL = _in_body(select.h4_no_auto)  # 编号由手打：自动编号段让开（GLB-28）
BODY_TEXT = select.body_paragraphs
BODY_FIGS = _in_body(select.captions_fig)
BODY_TABS = _in_body(select.captions_tab)
BODY_FORMULAS = _in_body(select.formula_paragraphs)


def body_citation_runs(blocks: Sequence[Block]) -> tuple[Run, ...]:
    """正文区里的引用标注 run（按文本 `[n]` 认，是否上标由 TXT-30 判）。"""
    return tuple(
        run
        for block in select.by_scope(blocks, Scope.BODY)
        for run in block.para.runs
        if is_citation(run.text)
    )


def formula_number_runs(blocks: Sequence[Block]) -> tuple[Run, ...]:
    """公式段落里带半角 `(章号-序号)` 的 run。"""
    return tuple(
        run for block in BODY_FORMULAS(blocks) for run in block.para.runs if _FORMULA_NO.search(run.text)
    )


def _caption_below_figure(block: Block) -> bool:
    return bool(block.para.objects.inline_images or block.para.objects.floating_images)


def _follows_table(block: Block) -> bool:
    return block.para.in_table


FIG_ABOVE = neighbour_flag(BODY_FIGS, before=True, pred=_caption_below_figure)
TAB_BELOW = neighbour_flag(BODY_TABS, before=False, pred=_follows_table)


# ── 写代码的判定 ────────────────────────────────────────────────


def chapter_verdict(chapters: tuple[Block, ...]) -> str:
    """TXT-51：第一~第五章是否齐全（宽松锚点收集，不依赖大纲级别）。"""
    found_numbers = {no for block in chapters if (no := chapter_no(block.para.text)) is not None}
    missing = [zh for zh, no in zip("一二三四五", range(1, 6), strict=True) if no not in found_numbers]
    return "五章齐全" if not missing else "未识别到第" + "、第".join(missing) + "章"


def chapter_page_breaks(blocks: Sequence[Block]) -> tuple[tuple[Block, bool], ...]:
    """TXT-07：第二~第五章是否另起一页（段前分页 / 分页符 / 前一节以分节符结束）。"""
    out: list[tuple[Block, bool]] = []
    for block in select.chapters(blocks):
        number = chapter_no(block.para.text)
        if number is None or not 2 <= number <= 5:
            continue
        index = index_of(blocks, block)
        previous = blocks[index - 1] if index > 0 else None
        started = block.para.has_page_break or (previous is not None and previous.para.section_break)
        out.append((block, started))
    return tuple(out)


def formula_number_verdict(block: Block) -> str:
    """TXT-32：公式段落必须带半角圆括号、半角 `-` 的 `(章号-序号)`。"""
    return "合规" if _FORMULA_NO.search(block.para.text) else "公式缺编号"


_H1_VERDICT = shape_verdict(H1_TEXT_SHAPE)
_H2_VERDICT = shape_verdict(H2_TEXT_SHAPE)
_H3_VERDICT = shape_verdict(H3_TEXT_SHAPE)
_H4_VERDICT = shape_verdict(_H4_SHAPE)
_FIG_VERDICT = shape_verdict(_FIG_FORMAT)
_TAB_VERDICT = shape_verdict(_TAB_FORMAT)


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="TXT-51",
        of=found(select.chapters),
        prop=chapter_verdict,
        expect="五章齐全",
        src="规范原文：第一章~第五章五章齐全",
    ),
    Rule(
        id="TXT-01",
        of=BODY_H1,
        prop=_H1_VERDICT,
        expect="合规",
        src="规范原文：一级标题「第X章」后空 2 格",
    ),
    Rule(
        id="TXT-02",
        of=cjk_of(BODY_H1),
        prop=attrgetter("ea"),
        expect="黑体",
        src="规范原文：一级标题黑体",
    ),
    Rule(
        id="TXT-03",
        of=visible_of(BODY_H1),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：一级标题三号（16pt）",
    ),
    Rule(
        id="TXT-04",
        of=BODY_H1,
        prop=para_align,
        expect="center",
        src="规范样张：一级标题居中",
    ),
    Rule(
        id="TXT-05",
        of=BODY_H1,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范原文：标题 1.5 倍行距",
    ),
    Rule(
        id="TXT-06",
        of=blanks_after(BODY_H1),
        prop=count,
        expect=1,
        src="规范原文：一级标题后空一行",
    ),
    Rule(
        id="TXT-07",
        of=chapter_page_breaks,
        prop=flag,
        expect=True,
        src="规范原文：从第二章开始每章另起一页",
    ),
    Rule(
        id="TXT-08",
        of=BODY_H2,
        prop=_H2_VERDICT,
        expect="合规",
        src="规范原文：二级标题序数后空 1 格",
    ),
    Rule(
        id="TXT-09",
        of=cjk_of(BODY_H2),
        prop=attrgetter("ea"),
        expect="黑体",
        src="规范原文：二级标题四号黑体",
    ),
    Rule(
        id="TXT-10",
        of=visible_of(BODY_H2),
        prop=attrgetter("size"),
        expect=14.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：二级标题四号（14pt）",
    ),
    Rule(
        id="TXT-11",
        of=west_of(BODY_H2),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范原文：二级标题字母、数字均用 Times New Roman",
    ),
    Rule(
        id="TXT-12",
        of=BODY_H2,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范原文：二级标题 1.5 倍行间距",
    ),
    Rule(
        id="TXT-13",
        of=BODY_H3,
        prop=_H3_VERDICT,
        expect="合规",
        src="规范原文：三级标题序数后空 1 格",
    ),
    Rule(
        id="TXT-14",
        of=cjk_of(BODY_H3),
        prop=attrgetter("ea"),
        expect="黑体",
        src="规范原文：三级标题黑体",
    ),
    Rule(
        id="TXT-15",
        of=visible_of(BODY_H3),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：三级标题小四（12pt）",
    ),
    Rule(
        id="TXT-16",
        of=west_of(BODY_H3),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范原文：三级标题字母、数字均用 Times New Roman",
    ),
    Rule(
        id="TXT-17",
        of=BODY_H3,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范原文：三级标题 1.5 倍行距",
    ),
    Rule(
        id="TXT-18",
        of=BODY_H3,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src="规范原文：三级标题首行缩进 2 字符",
    ),
    Rule(
        id="TXT-19",
        of=BODY_H4_MANUAL,
        prop=_H4_VERDICT,
        expect="合规",
        src="规范原文：三级以下标题以「（1）」形式手打编号",
    ),
    Rule(
        id="TXT-20",
        of=cjk_of(BODY_H4),
        prop=attrgetter("ea"),
        expect="宋体",
        src="规范原文：三级以下标题小四号宋体",
    ),
    Rule(
        id="TXT-21",
        of=visible_of(BODY_H4),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：三级以下标题小四（12pt）",
    ),
    Rule(
        id="TXT-22",
        of=west_of(BODY_H4),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范原文：三级以下标题字母、数字均用 Times New Roman",
    ),
    Rule(
        id="TXT-23",
        of=BODY_H4,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范原文：三级以下标题 1.5 倍行距",
    ),
    Rule(
        id="TXT-24",
        of=BODY_H4,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src="规范原文：三级以下标题首行缩进 2 字符",
    ),
    Rule(
        id="TXT-25",
        of=cjk_of(BODY_TEXT),
        prop=attrgetter("ea"),
        expect="宋体",
        src="规范原文：正文小四号宋体",
    ),
    Rule(
        id="TXT-26",
        of=west_of(BODY_TEXT),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范原文：正文外文选用 Times New Roman",
    ),
    Rule(
        id="TXT-27",
        of=visible_of(BODY_TEXT),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：正文小四（12pt）",
    ),
    Rule(
        id="TXT-28",
        of=BODY_TEXT,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src="规范原文：正文每段首行缩进 2 字符",
    ),
    Rule(
        id="TXT-29",
        of=BODY_TEXT,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范样张：正文 1.5 倍行距",
    ),
    Rule(
        id="TXT-30",
        of=body_citation_runs,
        prop=attrgetter("va"),
        expect="superscript",
        src="规范原文：参考文献的引用上标",
    ),
    Rule(
        id="TXT-31",
        of=body_citation_runs,
        prop=run_font,
        expect=("Times New Roman", 12.0),
        src="规范原文：参考文献的引用小四号 Times New Roman",
    ),
    Rule(
        id="TXT-32",
        of=BODY_FORMULAS,
        prop=formula_number_verdict,
        expect="合规",
        src="规范原文：所有公式都要有半角 (章号-序号) 编号",
    ),
    Rule(
        id="TXT-33",
        of=BODY_FORMULAS,
        prop=para_align,
        expect="center",
        src="规范原文：公式号和公式一起居中对齐",
    ),
    Rule(
        id="TXT-34",
        of=formula_number_runs,
        prop=attrgetter("size"),
        expect=10.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：公式编号五号（10.5pt）",
    ),
    Rule(
        id="TXT-35",
        of=formula_number_runs,
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范原文：公式编号 Times New Roman",
    ),
    Rule(
        id="TXT-37",
        of=BODY_FIGS,
        prop=_FIG_VERDICT,
        expect="合规",
        src="规范原文：图题编号格式「图章号-序号」",
    ),
    Rule(
        id="TXT-38",
        of=FIG_ABOVE,
        prop=flag,
        expect=True,
        src="规范原文：图号和图题放在图位下方",
    ),
    Rule(
        id="TXT-39",
        of=BODY_FIGS,
        prop=para_align,
        expect="center",
        src="规范原文：图题居中",
    ),
    Rule(
        id="TXT-40",
        of=BODY_FIGS,
        prop=first_cjk_font,
        expect=("宋体", 10.5),
        src="规范原文：图题 5 号宋体",
    ),
    Rule(
        id="TXT-41",
        of=BODY_FIGS,
        prop=gap_of(_FIG_NO),
        expect=1,
        src="规范原文：图号与图题之间空一格",
    ),
    Rule(
        id="TXT-43",
        of=BODY_TABS,
        prop=_TAB_VERDICT,
        expect="合规",
        src="规范原文：表题编号格式「表章号-序号」",
    ),
    Rule(
        id="TXT-44",
        of=TAB_BELOW,
        prop=flag,
        expect=True,
        src="规范原文：表号和表题放在表格上方",
    ),
    Rule(
        id="TXT-45",
        of=BODY_TABS,
        prop=para_align,
        expect="center",
        src="规范原文：表题居中",
    ),
    Rule(
        id="TXT-46",
        of=BODY_TABS,
        prop=first_cjk_font,
        expect=("宋体", 10.5),
        src="规范原文：表题 5 号宋体",
    ),
    Rule(
        id="TXT-47",
        of=BODY_TABS,
        prop=gap_of(_TAB_NO),
        expect=1,
        src="规范原文：表号后空一格",
    ),
)
