"""附录规则 APP-01 ~ APP-18。

标题按模块标题取；子标题按**文本**「附录 + 非空白字符」识别（识别与判定正交：级别 /
大小写写错仍会被识别，由 APP-13 / APP-06 报）；附录正文先排除子标题与图表题注，再套规则。
"""

from __future__ import annotations

from collections.abc import Sequence
from operator import attrgetter
from typing import Any

from ..semantics import select
from ..semantics.blocks import Block, Role, Scope
from ..semantics.matchers import key_text
from ..semantics.roles import heading_level
from .base import Comparison, Rule, ToleranceKey
from .support import (
    blanks_after,
    cjk_of,
    count,
    found,
    para_align,
    para_first_line,
    para_line,
    para_text,
    present,
    visible_of,
    west_of,
)


def app_title(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """附录标题：模块标题段落中属于附录区的那一个。"""
    return select.by_scope(select.module_titles(blocks), Scope.APPENDIX)


def app_body(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """附录正文：附录区内的正文角色段落（子标题是 H2、题注另有角色，都不算）。"""
    return tuple(block for block in select.by_scope(blocks, Scope.APPENDIX) if block.role is Role.BODY)


def app_numbering(blocks: Sequence[Block]) -> tuple[tuple[Block, ...], ...]:
    subs = select.appendix_subs_no_auto(blocks)
    return (subs,) if subs else ()


def app_numbering_verdict(subs: tuple[Block, ...]) -> str:
    """APP-06：编号须为 `A, B, C, …` 的连续前缀（大写、不跳号、不重复）。"""
    letters = [_sub_letter(block) for block in subs]
    expected = [chr(ord("A") + offset) for offset in range(len(letters))]
    return "合规" if letters == expected else "编号不连续"


def _sub_letter(block: Block) -> str:
    key = key_text(block.para.text)
    return key[2] if len(key) > 2 else ""


def app_outline_level(block: Block) -> int:
    """APP-13：大纲级别（2 级 = heading 2）；没有任何标题级别记为 0（不是 2）。"""
    return heading_level(block.para) or 0


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="APP-18",
        of=found(select.appendix_subs),
        prop=present,
        expect=True,
        src="规范原文：附录区至少要有 1 个附录子标题",
    ),
    Rule(
        id="APP-01",
        of=app_title,
        prop=para_text,
        expect="附    录",
        src="规范原文：标题「附    录」，中间 4 个半角空格",
    ),
    Rule(
        id="APP-02",
        of=cjk_of(app_title),
        prop=attrgetter("ea"),
        expect="黑体",
        src="规范原文：一级标题黑体",
    ),
    Rule(
        id="APP-03",
        of=visible_of(app_title),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：一级标题三号（16pt）",
    ),
    Rule(id="APP-04", of=app_title, prop=para_align, expect="center", src="规范样张：一级标题居中"),
    Rule(
        id="APP-05",
        of=blanks_after(app_title),
        prop=count,
        expect=1,
        src="规范原文：标题后空 1 行",
    ),
    Rule(
        id="APP-06",
        of=app_numbering,
        prop=app_numbering_verdict,
        expect="合规",
        src="规范原文：附录用大写字母 A、B、C 连续编号",
    ),
    Rule(
        id="APP-13",
        of=select.appendix_subs,
        prop=app_outline_level,
        expect=2,
        src="规范样张：附录子标题为 2 级（heading 2）",
    ),
    Rule(
        id="APP-14",
        of=cjk_of(select.appendix_subs),
        prop=attrgetter("ea"),
        expect="黑体",
        src="规范样张：附录子标题黑体",
    ),
    Rule(
        id="APP-15",
        of=visible_of(select.appendix_subs),
        prop=attrgetter("size"),
        expect=14.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范样张：附录子标题四号（14pt）",
    ),
    Rule(
        id="APP-16",
        of=west_of(select.appendix_subs),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范样张：附录子标题字母数字 Times New Roman",
    ),
    Rule(
        id="APP-17",
        of=select.appendix_subs,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范样张：附录子标题 1.5 倍行距",
    ),
    Rule(
        id="APP-07",
        of=cjk_of(app_body),
        prop=attrgetter("ea"),
        expect="宋体",
        src="规范样张：附录正文宋体",
    ),
    Rule(
        id="APP-08",
        of=west_of(app_body),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范样张：附录正文字母数字 Times New Roman",
    ),
    Rule(
        id="APP-09",
        of=visible_of(app_body),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范样张：附录正文小四（12pt）",
    ),
    Rule(
        id="APP-10",
        of=app_body,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范样张：附录正文 1.5 倍行距",
    ),
    Rule(
        id="APP-11",
        of=app_body,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src="规范样张：附录正文首行缩进 2 字符",
    ),
    Rule(
        id="APP-12",
        of=app_body,
        prop=para_align,
        expect="both",
        src="规范样张：附录正文两端对齐",
    ),
)
