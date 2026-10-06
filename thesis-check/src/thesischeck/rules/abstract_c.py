"""中文摘要规则 ABS-C-01 ~ ABS-C-25：绝大多数是一行数据，分隔符/末尾标点/个数与存在性写代码。

对象都在 `Scope.ABS_C` 内：标题走 `select.module_titles`，正文走正文角色，关键词行走
`select.keywords_c`（识别宽松，写错由规则报）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..semantics import Block, Role, Scope, select
from .base import Comparison, Rule, ToleranceKey, attrgetter
from .catalog import text
from .support import (
    blanks_after,
    cjk_of,
    content_of,
    contents,
    count,
    count_keywords,
    found,
    is_cjk_run,
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


def abs_c_title(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """中文摘要标题：模块标题段落中属于中文摘要区的那一个。"""
    return select.by_scope(select.module_titles(blocks), Scope.ABS_C)


def abs_c_body(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """中文摘要正文：中文摘要区内的正文角色段落（标题与关键词行都不是正文角色）。"""
    return tuple(block for block in select.by_scope(blocks, Scope.ABS_C) if block.role is Role.BODY)


# 关键词行：前缀侧（含冒号）/ 内容侧，中文 / 西文 / 可见三种 run 口径各取一次
_PREFIX_CJK = prefix_of(select.keywords_c, is_cjk_run)
_PREFIX_VISIBLE = prefix_of(select.keywords_c, is_visible_run)
_CONTENT_CJK = content_of(select.keywords_c, is_cjk_run)
_CONTENT_WEST = content_of(select.keywords_c, is_west_run)
_CONTENT_VISIBLE = content_of(select.keywords_c, is_visible_run)
_CONTENTS = contents(select.keywords_c)


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="ABS-C-01",
        of=abs_c_title,
        prop=para_text,
        expect="摘    要",
        src=text("ABS-C-01"),
    ),
    Rule(
        id="ABS-C-02",
        of=cjk_of(abs_c_title),
        prop=attrgetter("ea"),
        expect="黑体",
        src=text("ABS-C-02"),
    ),
    Rule(
        id="ABS-C-03",
        of=visible_of(abs_c_title),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("ABS-C-03"),
    ),
    Rule(
        id="ABS-C-04",
        of=abs_c_title,
        prop=para_align,
        expect="center",
        src=text("ABS-C-04"),
    ),
    Rule(
        id="ABS-C-05",
        of=blanks_after(abs_c_title),
        prop=count,
        expect=1,
        src=text("ABS-C-05"),
    ),
    Rule(
        id="ABS-C-06",
        of=cjk_of(abs_c_body),
        prop=attrgetter("ea"),
        expect="宋体",
        src=text("ABS-C-06"),
    ),
    Rule(
        id="ABS-C-07",
        of=west_of(abs_c_body),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src=text("ABS-C-07"),
    ),
    Rule(
        id="ABS-C-08",
        of=visible_of(abs_c_body),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("ABS-C-08"),
    ),
    Rule(
        id="ABS-C-09",
        of=abs_c_body,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src=text("ABS-C-09"),
    ),
    Rule(
        id="ABS-C-10",
        of=abs_c_body,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src=text("ABS-C-10"),
    ),
    Rule(
        id="ABS-C-11",
        of=blanks_after(last_of(abs_c_body)),
        prop=count,
        expect=1,
        src=text("ABS-C-11"),
    ),
    Rule(
        id="ABS-C-25",
        of=found(select.keywords_c),
        prop=present,
        expect=True,
        src=text("ABS-C-25"),
    ),
    Rule(
        id="ABS-C-12",
        of=select.keywords_c,
        prop=prefix_text,
        expect="关键词：",
        src=text("ABS-C-12"),
    ),
    Rule(
        id="ABS-C-13",
        of=_PREFIX_CJK,
        prop=attrgetter("ea"),
        expect="宋体",
        src=text("ABS-C-13"),
    ),
    Rule(
        id="ABS-C-14",
        of=_PREFIX_VISIBLE,
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("ABS-C-14"),
    ),
    Rule(
        id="ABS-C-15",
        of=_PREFIX_VISIBLE,
        prop=attrgetter("bold"),
        expect=True,
        src=text("ABS-C-15"),
    ),
    Rule(
        id="ABS-C-16",
        of=_CONTENT_CJK,
        prop=attrgetter("ea"),
        expect="宋体",
        src=text("ABS-C-16"),
    ),
    Rule(
        id="ABS-C-17",
        of=_CONTENT_WEST,
        prop=attrgetter("west"),
        expect="Times New Roman",
        src=text("ABS-C-17"),
    ),
    Rule(
        id="ABS-C-18",
        of=_CONTENT_VISIBLE,
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("ABS-C-18"),
    ),
    Rule(
        id="ABS-C-19",
        of=select.keywords_c,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src=text("ABS-C-19"),
    ),
    Rule(
        id="ABS-C-20",
        of=select.keywords_c,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src=text("ABS-C-20"),
    ),
    Rule(
        id="ABS-C-21",
        of=select.keywords_c,
        prop=para_align,
        expect="both",
        src=text("ABS-C-21"),
    ),
    Rule(
        id="ABS-C-22",
        of=_CONTENTS,
        prop=separator_verdict,
        expect="合规",
        src=text("ABS-C-22"),
    ),
    Rule(
        id="ABS-C-23",
        of=_CONTENTS,
        prop=trailing_verdict,
        expect="无标点",
        src=text("ABS-C-23"),
    ),
    Rule[Any, Any](
        id="ABS-C-24",
        of=_CONTENTS,
        prop=count_keywords,
        expect=(3, 5),
        cmp=Comparison.COUNT_RANGE,
        src=text("ABS-C-24"),
    ),
)
