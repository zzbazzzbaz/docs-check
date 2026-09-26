"""英文摘要规则 ABS-E-01 ~ ABS-E-22：绝大多数是一行数据，分隔符/末尾标点与存在性写代码。

对象都在 `Scope.ABS_E` 内：标题走 `select.module_titles`，正文走正文角色，Keywords 行走
`select.keywords_e`（识别忽略大小写且宽松，写错由规则报）。
"""

from __future__ import annotations

from collections.abc import Sequence
from operator import attrgetter
from typing import Any

from ..semantics import select
from ..semantics.blocks import Block, Role, Scope
from .base import Comparison, Rule, ToleranceKey
from .support import (
    blanks_after,
    content_of,
    contents,
    count,
    found,
    is_visible_run,
    is_west_run,
    last_of,
    para_align,
    para_first_line,
    para_line,
    para_text,
    prefix_of,
    prefix_text,
    present,
    separator_verdict,
    trailing_verdict,
    visible_of,
    west_of,
)


def abs_e_title(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """ABSTRACT 标题：模块标题段落中属于英文摘要区的那一个。"""
    return select.by_scope(select.module_titles(blocks), Scope.ABS_E)


def abs_e_body(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """英文摘要正文：英文摘要区内的正文角色段落。"""
    return tuple(block for block in select.by_scope(blocks, Scope.ABS_E) if block.role is Role.BODY)


# Keywords 行：前缀侧（含冒号）/ 内容侧
_PREFIX_WEST = prefix_of(select.keywords_e, is_west_run)
_PREFIX_VISIBLE = prefix_of(select.keywords_e, is_visible_run)
_CONTENT_WEST = content_of(select.keywords_e, is_west_run)
_CONTENT_VISIBLE = content_of(select.keywords_e, is_visible_run)
_CONTENTS = contents(select.keywords_e)


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="ABS-E-01",
        of=abs_e_title,
        prop=para_text,
        expect="ABSTRACT",
        src="规范原文：标题「ABSTRACT」全大写",
    ),
    Rule(
        id="ABS-E-02",
        of=west_of(abs_e_title),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范原文：ABSTRACT 用 Times New Roman",
    ),
    Rule(
        id="ABS-E-03",
        of=visible_of(abs_e_title),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：ABSTRACT 三号（16pt）",
    ),
    Rule(
        id="ABS-E-04",
        of=visible_of(abs_e_title),
        prop=attrgetter("bold"),
        expect=True,
        src="规范原文：ABSTRACT 加粗",
    ),
    Rule(
        id="ABS-E-05",
        of=abs_e_title,
        prop=para_align,
        expect="center",
        src="规范原文：ABSTRACT 居中",
    ),
    Rule(
        id="ABS-E-06",
        of=blanks_after(abs_e_title),
        prop=count,
        expect=1,
        src="规范样张：ABSTRACT 标题后 1 个空段落",
    ),
    Rule(
        id="ABS-E-07",
        of=west_of(abs_e_body),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范原文：英文摘要正文 Times New Roman",
    ),
    Rule(
        id="ABS-E-08",
        of=visible_of(abs_e_body),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：英文摘要正文小四（12pt）",
    ),
    Rule(
        id="ABS-E-09",
        of=abs_e_body,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范原文：英文摘要正文 1.5 倍行距",
    ),
    Rule(
        id="ABS-E-10",
        of=abs_e_body,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src="规范原文：英文摘要正文首行缩进 2 字符",
    ),
    Rule(
        id="ABS-E-11",
        of=blanks_after(last_of(abs_e_body)),
        prop=count,
        expect=1,
        src="规范样张：英文摘要正文后 1 个空段落",
    ),
    Rule(
        id="ABS-E-22",
        of=found(select.keywords_e),
        prop=present,
        expect=True,
        src="规范原文：英文摘要必须有「Keywords：…」行",
    ),
    Rule(
        id="ABS-E-12",
        of=select.keywords_e,
        prop=prefix_text,
        expect="Keywords：",
        src="规范原文：前缀「Keywords：」，全角冒号",
    ),
    Rule(
        id="ABS-E-13",
        of=_PREFIX_WEST,
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范原文：Keywords 前缀 Times New Roman",
    ),
    Rule(
        id="ABS-E-14",
        of=_PREFIX_VISIBLE,
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：Keywords 小四（12pt）",
    ),
    Rule(
        id="ABS-E-15",
        of=_PREFIX_VISIBLE,
        prop=attrgetter("bold"),
        expect=True,
        src="规范原文：Keywords 加粗",
    ),
    Rule(
        id="ABS-E-16",
        of=_CONTENT_WEST,
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范原文：Keywords 内容 Times New Roman",
    ),
    Rule(
        id="ABS-E-17",
        of=_CONTENT_VISIBLE,
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：Keywords 小四（12pt）",
    ),
    Rule(
        id="ABS-E-18",
        of=select.keywords_e,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范原文：Keywords 行 1.5 倍行距",
    ),
    Rule(
        id="ABS-E-19",
        of=select.keywords_e,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src="规范原文：Keywords 行首行缩进 2 字符",
    ),
    Rule(
        id="ABS-E-20",
        of=_CONTENTS,
        prop=separator_verdict,
        expect="合规",
        src="规范样张：Keywords 之间用中文分号「；」",
    ),
    Rule(
        id="ABS-E-21",
        of=_CONTENTS,
        prop=trailing_verdict,
        expect="无标点",
        src="规范原文：Keywords 末尾无标点",
    ),
)
