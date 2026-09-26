"""目录规则 TOC-01 ~ TOC-15。

层级**只用样式名** `toc 1/2/3` 判（不是 styleId、不是编号形态）；编号后空格与文本
形状写代码（`shape_verdict`），其余都是一行数据。字体 / 加粗只判非空白字符。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..semantics import select
from ..semantics.blocks import Block, Scope
from ..semantics.matchers import is_chapter, toc_style_level
from .base import Comparison, Rule, ToleranceKey, attrgetter
from .support import (
    H1_TEXT_SHAPE,
    H2_TEXT_SHAPE,
    H3_TEXT_SHAPE,
    BlockSel,
    blanks_after,
    cjk_of,
    count,
    found,
    para_align,
    para_bold_verdict,
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
_H2_VERDICT = shape_verdict(H2_TEXT_SHAPE)
_H3_VERDICT = shape_verdict(H3_TEXT_SHAPE)


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="TOC-01",
        of=toc_title,
        prop=para_text,
        expect="目    录",
        src="规范原文：目录标题「目    录」，中间 4 个半角空格",
    ),
    Rule(
        id="TOC-02",
        of=cjk_of(toc_title),
        prop=attrgetter("ea"),
        expect="黑体",
        src="规范原文：目录标题黑体",
    ),
    Rule(
        id="TOC-03",
        of=visible_of(toc_title),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：目录标题三号（16pt）",
    ),
    Rule(
        id="TOC-04",
        of=toc_title,
        prop=para_align,
        expect="center",
        src="规范原文：目录标题居中",
    ),
    Rule(
        id="TOC-05",
        of=toc_title,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范原文：目录标题 1.5 倍行距",
    ),
    Rule(
        id="TOC-06",
        of=blanks_after(toc_title),
        prop=count,
        expect=1,
        src="规范原文：目录标题与目录条目之间空一行",
    ),
    Rule(
        id="TOC-15",
        of=found(select.toc_entries),
        prop=present,
        expect=True,
        src="规范原文：目录必须是自动生成的 TOC 域（至少有 1 个目录条目）",
    ),
    Rule(
        id="TOC-07",
        of=cjk_of(select.toc_entries),
        prop=attrgetter("ea"),
        expect="宋体",
        src="规范样张：目录条目宋体",
    ),
    Rule(
        id="TOC-08",
        of=west_of(select.toc_entries),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范样张：目录条目西文和数字 Times New Roman",
    ),
    Rule(
        id="TOC-09",
        of=visible_of(select.toc_entries),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范样张：目录条目小四（12pt）",
    ),
    Rule(
        id="TOC-10",
        of=select.toc_entries,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范样张：目录条目 1.5 倍行距",
    ),
    Rule(
        id="TOC-11",
        of=select.toc_entries,
        prop=para_bold_verdict,
        expect="不加粗",
        src="规范样张：目录条目非空白字符不加粗",
    ),
    Rule(
        id="TOC-12",
        of=toc_l1_chapter,
        prop=_H1_VERDICT,
        expect="合规",
        src="规范原文：一级目录条目编号后空 2 格",
    ),
    Rule(
        id="TOC-13",
        of=TOC_L2,
        prop=_H2_VERDICT,
        expect="合规",
        src="规范原文：二级目录条目编号后空 1 格",
    ),
    Rule(
        id="TOC-14",
        of=TOC_L3,
        prop=_H3_VERDICT,
        expect="合规",
        src="规范原文：三级目录条目编号后空 1 格",
    ),
)
