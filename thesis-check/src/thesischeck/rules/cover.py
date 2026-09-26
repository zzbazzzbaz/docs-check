"""封面规则 COV-01 ~ COV-16：一行数据一条，只有「五行一致」写了代码。

对象一律在 `Scope.COVER` 内按**宽松文本锚点**找（`key_text` 去空白后比较），
写错空格 / 文本由文本规则报，不由识别器过滤掉。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..parse.model import Run
from ..semantics import select
from ..semantics.blocks import Block, Scope
from ..semantics.matchers import key_text
from .base import Comparison, Rule, ToleranceKey, attrgetter
from .support import (
    cjk_of,
    content_of,
    is_cjk_run,
    is_visible_run,
    para_align,
    prefix_of,
    split_text,
    visible_of,
)

_COVER_MAIN = "本科生毕业设计（论文）"
_INFO_PREFIXES = ("学生姓名", "学号", "院系", "专业年级", "指导教师")
_INFO_PROPS = ("中文字体", "字号", "加粗")


# ── 对象识别 ────────────────────────────────────────────────────


def cover_main_line(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """「本科生毕业设计（论文）」行：去空白后等于该文本。"""
    return tuple(
        block for block in select.by_scope(blocks, Scope.COVER) if key_text(block.para.text) == _COVER_MAIN
    )


def cover_title_line(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """题目行：去空白后以「题目」开头（冒号全/半角都先认下）。"""
    return tuple(
        block
        for block in select.by_scope(blocks, Scope.COVER)
        if key_text(block.para.text).startswith("题目")
    )


def cover_info_lines(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """信息行：行首为五个标签之一（去空白后比较）。"""
    out: list[Block] = []
    for block in select.by_scope(blocks, Scope.COVER):
        key = key_text(block.para.text)
        if any(key.startswith(prefix) for prefix in _INFO_PREFIXES):
            out.append(block)
    return tuple(out)


def cover_date_line(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """日期行：去空白后同时含「年」「月」「日」。"""
    return tuple(
        block
        for block in select.by_scope(blocks, Scope.COVER)
        if all(mark in key_text(block.para.text) for mark in "年月日")
    )


def cover_label_text(block: Block) -> str:
    return split_text(block.para.text)[0]


# 题目标签 / 内容两侧的 run（前缀侧含冒号，内容侧在冒号后）
_LABEL_CJK = prefix_of(cover_title_line, is_cjk_run)
_LABEL_VISIBLE = prefix_of(cover_title_line, is_visible_run)
_CONTENT_CJK = content_of(cover_title_line, is_cjk_run)
_CONTENT_VISIBLE = content_of(cover_title_line, is_visible_run)


# ── 五行一致（COV-13，唯一写代码的封面规则）──────────────────────


def line_signature(block: Block) -> tuple[str | None, float | None, bool | None] | None:
    """一个信息行的（中文字体, 字号, 加粗）：取第一个中文 run，退化到第一个可见 run。"""
    run: Run | None = next((item for item in block.para.runs if is_cjk_run(item)), None)
    if run is None:
        run = next((item for item in block.para.runs if is_visible_run(item)), None)
    return None if run is None else (run.ea, run.size, run.bold)


def cover_info_consistency(blocks: Sequence[Block]) -> tuple[tuple[Block, ...], ...]:
    lines = cover_info_lines(blocks)
    return (lines,) if lines else ()


def info_consistency(lines: tuple[Block, ...]) -> str | None:
    signatures = [line_signature(block) for block in lines]
    if not signatures or any(signature is None for signature in signatures):
        return None
    concrete = [signature for signature in signatures if signature is not None]
    first = concrete[0]
    for order, signature in enumerate(concrete[1:], start=2):
        if signature != first:
            differing = [
                name for name, left, right in zip(_INFO_PROPS, first, signature, strict=True) if left != right
            ]
            return f"第{order}行与第1行的{('、'.join(differing))}不一致"
    return "一致"


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="COV-01",
        of=cjk_of(cover_main_line),
        prop=attrgetter("ea"),
        expect="方正小标宋简体",
        src="规范原文：本科生毕业设计（论文）用方正小标宋简体",
    ),
    Rule(
        id="COV-02",
        of=visible_of(cover_main_line),
        prop=attrgetter("size"),
        expect=36.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：小初（36pt），空 run 不算",
    ),
    Rule(
        id="COV-03",
        of=cover_main_line,
        prop=para_align,
        expect="center",
        src="规范原文：居中",
    ),
    Rule(
        id="COV-04",
        of=cover_title_line,
        prop=cover_label_text,
        expect="题    目：",
        src="规范样张：题目标签「题    目：」（4 个半角空格 + 全角冒号）",
    ),
    Rule(
        id="COV-05",
        of=_LABEL_CJK,
        prop=attrgetter("ea"),
        expect="仿宋",
        src="用户确认：题目标签仿宋",
    ),
    Rule(
        id="COV-06",
        of=_LABEL_VISIBLE,
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="用户确认：题目标签三号（16pt）",
    ),
    Rule(
        id="COV-07",
        of=_LABEL_VISIBLE,
        prop=attrgetter("bold"),
        expect=True,
        src="用户确认：题目标签加粗",
    ),
    Rule(
        id="COV-08",
        of=_CONTENT_CJK,
        prop=attrgetter("ea"),
        expect="黑体",
        src="规范原文：题目内容黑体",
    ),
    Rule(
        id="COV-09",
        of=_CONTENT_VISIBLE,
        prop=attrgetter("size"),
        expect=18.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：题目内容小二（18pt）",
    ),
    Rule(
        id="COV-10",
        of=cjk_of(cover_info_lines),
        prop=attrgetter("ea"),
        expect="仿宋",
        src="规范原文：信息行仿宋",
    ),
    Rule(
        id="COV-11",
        of=visible_of(cover_info_lines),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：信息行三号（16pt）",
    ),
    Rule(
        id="COV-12",
        of=visible_of(cover_info_lines),
        prop=attrgetter("bold"),
        expect=True,
        src="规范原文：信息行加粗",
    ),
    Rule(
        id="COV-13",
        of=cover_info_consistency,
        prop=info_consistency,
        expect="一致",
        src="规范原文：学生姓名、学号、院系、专业年级、指导教师要求一致",
    ),
    Rule(
        id="COV-14",
        of=cjk_of(cover_date_line),
        prop=attrgetter("ea"),
        expect="仿宋",
        src="规范原文：日期行仿宋",
    ),
    Rule(
        id="COV-15",
        of=visible_of(cover_date_line),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：日期行三号（16pt）",
    ),
    Rule(
        id="COV-16",
        of=visible_of(cover_date_line),
        prop=attrgetter("bold"),
        expect=True,
        src="规范原文：日期行加粗",
    ),
)
