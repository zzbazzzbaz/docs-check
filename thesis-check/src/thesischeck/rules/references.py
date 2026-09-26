"""参考文献规则 REF-01 ~ REF-15、REF-21、REF-22。

标题按模块标题取；条目按**宽松锚点**取（区内非空段落，不要求以编号开头），编号格式 / 连续性 /
类型标识 / 重复 / 段落完整性写代码，其余是一行数据。`REF-10` 与 `REF-21` 共用
`matchers.looks_like_number`，互斥天然成立（README 通用判定口径第 10 条 + 需求 §3.4）。

批 2 的 `REF-14` / `REF-15` 消费整篇索引的正文引用集合（文本 `[数字]`，不是上标），
抽不到引用时显式「无法判定」。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ..index import Citation
from ..semantics import select
from ..semantics.blocks import Block, CheckContext, Scope
from ..semantics.matchers import looks_like_number
from .base import Comparison, Rule, ToleranceKey, attrgetter
from .support import (
    blanks_after,
    cjk_of,
    context_index,
    count,
    found,
    para_align,
    para_line,
    para_text,
    present,
    visible_of,
    west_of,
)

# 类型标识：题名之后的方括号字母（`[M]` / `[EB/OL]` / `[J/OL]`…）；`[数字]` 编号不匹配
_TYPE_TOKEN = re.compile(r"\[([A-Za-z][A-Za-z/]*)\]")
_ALLOWED_TYPES = frozenset({"M", "J", "N", "D", "EB/OL"})
# 编号前缀（括号可有可无、可有前导零）；只用于 REF-10 / REF-11 / REF-13 的切分
_REF_NUMBER = re.compile(r"^\[([0-9]+)\] (\S)")
_LEADING_NUMBER = re.compile(r"^\s*[\[【［(（]?\s*(\d+)")
_DROP_NUMBER = re.compile(r"^\s*[\[【［(（]?\s*\d+\s*[\]】］)）]?\s*")


def refs_title(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """参考文献标题：模块标题段落中属于参考文献区的那一个。"""
    return select.by_scope(select.module_titles(blocks), Scope.REFS)


def numbered_items(blocks: Sequence[Block]) -> tuple[Block, ...]:
    """以「看起来像编号开头」的文献条目（自动编号段让开，交 GLB-28）。"""
    return tuple(b for b in select.ref_items_no_auto(blocks) if looks_like_number(b.para.text))


def ref_number_verdict(block: Block) -> str:
    """REF-10：必须是半角 `[n]` + **恰好 1 个半角空格**，且不得有前导零。"""
    match = _REF_NUMBER.match(block.para.text)
    if match is None or match.group(1).startswith("0"):
        return "编号或空格不符"
    return "合规"


def _leading_number(text: str) -> int | None:
    match = _LEADING_NUMBER.match(text)
    return None if match is None else int(match.group(1))


def ref_continuity_verdict(items: tuple[Block, ...]) -> str:
    """REF-11：编号集合须恰为 `{1, 2, …, N}`（`N` = 有编号的条目数）；不排序、不修复。"""
    numbers: list[int] = []
    for block in items:
        number = _leading_number(block.para.text)
        if number is None:
            return "存在无法解析的编号"
        numbers.append(number)
    return "合规" if sorted(numbers) == list(range(1, len(numbers) + 1)) else "编号不连续"


def ref_type_verdict(block: Block) -> str:
    """REF-12：题名之后必须带五类之一的类型标识。"""
    tokens = _TYPE_TOKEN.findall(block.para.text)
    if not tokens:
        return "缺文献类型标识"
    return "合规" if all(token in _ALLOWED_TYPES for token in tokens) else "类型标识不在五类内"


def _without_number(text: str) -> str:
    return _DROP_NUMBER.sub("", text.strip(), count=1).strip()


def ref_continuity(blocks: Sequence[Block]) -> tuple[tuple[Block, ...], ...]:
    items = numbered_items(blocks)
    return (items,) if items else ()


def ref_duplication(blocks: Sequence[Block]) -> tuple[tuple[Block, ...], ...]:
    return (select.ref_items(blocks),)


def ref_duplicate_verdict(items: tuple[Block, ...]) -> str:
    """REF-13：去掉编号与首尾空白后，文本**完全一致**即为重复条目。"""
    seen = [_without_number(block.para.text) for block in items]
    return "合规" if len(set(seen)) == len(seen) else "存在重复条目"


def ref_integrity_verdict(block: Block) -> str:
    """REF-21：条目内部不得手动换行；未以编号开头的段落由本规则报（与 REF-10 互斥）。"""
    if "\n" in block.para.text:
        return "条目内出现手动换行"
    return "合规" if looks_like_number(block.para.text) else "未以编号开头"


# ── 批 2：正文引用与顺序（REF-14 / REF-15，消费整篇索引）──────


def _entry_numbers(blocks: Sequence[Block]) -> tuple[int, ...]:
    numbers = (_leading_number(block.para.text) for block in numbered_items(blocks))
    return tuple(number for number in numbers if number is not None)


def citation_payload(ctx: CheckContext) -> tuple[tuple[tuple[int, ...], tuple[Citation, ...] | None], ...]:
    """（条目编号, 正文引用标注）；引用为 `None` 表示正文区定位不到（无法判定）。"""
    return ((_entry_numbers(ctx), context_index(ctx).citations),)


def citation_coverage_verdict(payload: tuple[tuple[int, ...], tuple[Citation, ...] | None]) -> str | None:
    """REF-14：`R \\ C`（有条目、正文没引用）报出；`C \\ R`（悬空引用）不报。"""
    numbers, citations = payload
    if citations is None:
        return None
    cited = {citation.no for citation in citations}
    missing = [number for number in numbers if number not in cited]
    return "合规" if not missing else "正文未引用：" + "、".join(f"[{number}]" for number in missing)


def citation_order_verdict(payload: tuple[tuple[int, ...], tuple[Citation, ...] | None]) -> str | None:
    """REF-15：按首次出现顺序与 `1…N` 比对，报**首个倒置位置**。"""
    _numbers, citations = payload
    if citations is None:
        return None
    for position, citation in enumerate(citations, 1):
        if citation.no != position:
            return f"第 {position} 个引用是 [{citation.no}]，与从 1 起的顺序不符"
    return "合规"


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="REF-22",
        of=found(select.ref_items),
        prop=present,
        expect=True,
        src="规范原文：参考文献区必须至少有 1 条文献条目",
    ),
    Rule(id="REF-01", of=refs_title, prop=para_text, expect="参考文献", src="规范原文：标题「参考文献」"),
    Rule(
        id="REF-02",
        of=cjk_of(refs_title),
        prop=attrgetter("ea"),
        expect="黑体",
        src="规范原文：一级标题黑体",
    ),
    Rule(
        id="REF-03",
        of=visible_of(refs_title),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范原文：一级标题三号（16pt）",
    ),
    Rule(id="REF-04", of=refs_title, prop=para_align, expect="center", src="规范原文：一级标题居中"),
    Rule(
        id="REF-05",
        of=blanks_after(refs_title),
        prop=count,
        expect=1,
        src="规范原文：标题后空 1 行",
    ),
    Rule(
        id="REF-06",
        of=cjk_of(select.ref_items),
        prop=attrgetter("ea"),
        expect="宋体",
        src="规范样张：文献条目宋体",
    ),
    Rule(
        id="REF-07",
        of=west_of(select.ref_items),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src="规范样张：文献条目字母数字 Times New Roman",
    ),
    Rule(
        id="REF-08",
        of=visible_of(select.ref_items),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src="规范样张：文献条目小四（12pt）",
    ),
    Rule(
        id="REF-09",
        of=select.ref_items,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src="规范样张：文献条目 1.5 倍行距",
    ),
    Rule(
        id="REF-10",
        of=numbered_items,
        prop=ref_number_verdict,
        expect="合规",
        src="规范原文：编号「[n]」后恰好 1 个半角空格",
    ),
    Rule(
        id="REF-11",
        of=ref_continuity,
        prop=ref_continuity_verdict,
        expect="合规",
        src="规范原文：编号从 1 起连续，不跳号、不重复",
    ),
    Rule(
        id="REF-12",
        of=select.ref_items,
        prop=ref_type_verdict,
        expect="合规",
        src="规范原文：文献类型标识只能是 [M] [J] [N] [D] [EB/OL]",
    ),
    Rule(
        id="REF-13",
        of=ref_duplication,
        prop=ref_duplicate_verdict,
        expect="合规",
        src="规范原文：同一条文献只出现一次",
    ),
    Rule(
        id="REF-14",
        of=citation_payload,
        prop=citation_coverage_verdict,
        expect="合规",
        src="规范原文：所有参考文献必须都在正文中有引用",
    ),
    Rule(
        id="REF-15",
        of=citation_payload,
        prop=citation_order_verdict,
        expect="合规",
        src="规范原文：按在正文中出现的先后次序排列",
    ),
    Rule(
        id="REF-21",
        of=select.ref_items_no_auto,
        prop=ref_integrity_verdict,
        expect="合规",
        src="规范原文：一条文献占且仅占 1 个段落，不手动换行",
    ),
)
