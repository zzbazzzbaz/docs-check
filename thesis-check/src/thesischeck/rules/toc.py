"""目录规则 TOC-01 ~ TOC-18。

层级**只用样式名** `toc 1/2/3` 判（不是 styleId、不是编号形态）；编号后空格与文本
形状写代码（`shape_verdict`），层级缩进读 `w:ind`，其余都是一行数据。字体 / 加粗只判
非空白字符。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..semantics import Block, Scope, is_chapter, select, toc_style_level
from .base import Comparison, Rule, ToleranceKey, attrgetter
from .catalog import text
from .support import (
    H1_TEXT_SHAPE,
    H3_TEXT_SHAPE,
    TOC_L2_TEXT_SHAPE,
    BlockSel,
    blanks_after,
    cjk_of,
    count,
    found,
    para_align,
    para_bold_verdict,
    para_first_line_or_zero,
    para_line,
    para_text,
    present,
    shape_verdict,
    visible_of,
    west_of,
)


def toc_title(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """目录标题：模块标题段落中属于目录区的那一个。"""
    return select.by_scope(select.module_titles(blocks), Scope.TOC)


def _toc_level(level: int) -> BlockSel:
    """目录条目按样式名层级过滤（`toc 1` / `toc 2` / `toc 3`）。"""

    def pick(blocks: Sequence[Block]) -> tuple[Block, ...]:
        return tuple(b for b in select.toc_entries(blocks) if toc_style_level(b.para.style) == level)

    return pick


TOC_L1 = _toc_level(1)
TOC_L2 = _toc_level(2)
TOC_L3 = _toc_level(3)


def toc_l1_chapter(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """「第X章」型一级条目（读文本，不看编号形态）。"""
    return tuple(b for b in TOC_L1(blocks) if is_chapter(b.para.text))


_H1_VERDICT = shape_verdict(H1_TEXT_SHAPE)
_H2_VERDICT = shape_verdict(TOC_L2_TEXT_SHAPE)
_H3_VERDICT = shape_verdict(H3_TEXT_SHAPE)


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="TOC-01",
        of=toc_title,
        prop=para_text,
        expect="目    录",
        src=text("TOC-01"),
    ),
    Rule(
        id="TOC-02",
        of=cjk_of(toc_title),
        prop=attrgetter("ea"),
        expect="黑体",
        src=text("TOC-02"),
    ),
    Rule(
        id="TOC-03",
        of=visible_of(toc_title),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("TOC-03"),
    ),
    Rule(
        id="TOC-04",
        of=toc_title,
        prop=para_align,
        expect="center",
        src=text("TOC-04"),
    ),
    Rule(
        id="TOC-05",
        of=toc_title,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src=text("TOC-05"),
    ),
    Rule(
        id="TOC-06",
        of=blanks_after(toc_title),
        prop=count,
        expect=1,
        src=text("TOC-06"),
    ),
    Rule(
        id="TOC-15",
        of=found(select.toc_entries),
        prop=present,
        expect=True,
        src=text("TOC-15"),
    ),
    Rule(
        id="TOC-07",
        of=cjk_of(select.toc_entries),
        prop=attrgetter("ea"),
        expect="宋体",
        src=text("TOC-07"),
    ),
    Rule(
        id="TOC-08",
        of=west_of(select.toc_entries),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src=text("TOC-08"),
    ),
    Rule(
        id="TOC-09",
        of=visible_of(select.toc_entries),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("TOC-09"),
    ),
    Rule(
        id="TOC-10",
        of=select.toc_entries,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src=text("TOC-10"),
    ),
    Rule(
        id="TOC-11",
        of=select.toc_entries,
        prop=para_bold_verdict,
        expect="不加粗",
        src=text("TOC-11"),
    ),
    Rule(
        id="TOC-12",
        of=toc_l1_chapter,
        prop=_H1_VERDICT,
        expect="合规",
        src=text("TOC-12"),
    ),
    Rule(
        id="TOC-13",
        of=TOC_L2,
        prop=_H2_VERDICT,
        expect="合规",
        src=text("TOC-13"),
    ),
    Rule(
        id="TOC-14",
        of=TOC_L3,
        prop=_H3_VERDICT,
        expect="合规",
        src=text("TOC-14"),
    ),
    Rule(
        id="TOC-16",
        of=TOC_L1,
        prop=para_first_line_or_zero,
        expect=0.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src=text("TOC-16"),
    ),
    Rule(
        id="TOC-17",
        of=TOC_L2,
        prop=para_first_line_or_zero,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src=text("TOC-17"),
    ),
    Rule(
        id="TOC-18",
        of=TOC_L3,
        prop=para_first_line_or_zero,
        expect=4.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src=text("TOC-18"),
    ),
)
