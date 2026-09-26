"""致谢规则 ACK-01 ~ ACK-12。

标题按模块标题取；正文按致谢区内的正文角色段落取（识别宽松，写错由规则报）。字体 / 字号 /
行距 / 缩进 / 对齐口径与摘要正文一致：只判中文字符所在的 run、西文只判 ASCII 字母数字。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..semantics import select
from ..semantics.blocks import Block, Role, Scope
from .base import Comparison, Rule, ToleranceKey, attrgetter
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


def ack_title(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """致谢标题：模块标题段落中属于致谢区的那一个。"""
    return select.by_scope(select.module_titles(blocks), Scope.ACK)


def ack_body(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """致谢正文：致谢区内的正文角色段落（标题不是正文角色）。"""
    return tuple(block for block in select.by_scope(blocks, Scope.ACK) if block.role is Role.BODY)


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="ACK-01",
        of=ack_title,
        prop=para_text,
        expect="致    谢",
        src="规范原文：标题「致    谢」，中间 4 个半角空格",
    ),
    Rule(
        id="ACK-02",
        of=cjk_of(ack_title),
        prop=attrgetter("ea"),
        expect="黑体",
        src="规范原文：一级标题黑体",
    ),
    Rule(
        id="ACK-03",
        of=visible_of(ack_title),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：一级标题三号（16pt）",
    ),
    Rule(id="ACK-04", of=ack_title, prop=para_align, expect="center", src="规范样张：一级标题居中"),
    Rule(
        id="ACK-05",
        of=blanks_after(ack_title),
        prop=count,
        expect=1,
        src="规范原文：标题后空 1 行",
    ),
    Rule(
        id="ACK-12",
        of=found(ack_body),
        prop=present,
        expect=True,
        src="规范原文：致谢区必须有致谢正文（至少 1 个非空段落）",
    ),
    Rule(
        id="ACK-06",
        of=cjk_of(ack_body),
        prop=attrgetter("ea"),
        expect="宋体",
        src="规范样张：致谢正文宋体",
    ),
    Rule(
        id="ACK-07",
        of=west_of(ack_body),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范样张：致谢正文字母数字 Times New Roman",
    ),
    Rule(
        id="ACK-08",
        of=visible_of(ack_body),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范样张：致谢正文小四（12pt）",
    ),
    Rule(
        id="ACK-09",
        of=ack_body,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范样张：致谢正文 1.5 倍行距",
    ),
    Rule(
        id="ACK-10",
        of=ack_body,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src="规范样张：致谢正文首行缩进 2 字符",
    ),
    Rule(
        id="ACK-11",
        of=ack_body,
        prop=para_align,
        expect="both",
        src="规范样张：致谢正文两端对齐",
    ),
)
