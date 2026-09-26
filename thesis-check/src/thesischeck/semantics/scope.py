"""8 个作用域的分区：封面 → 中文摘要 → 英文摘要 → 目录 → 正文 → 参考文献 → 致谢 → 附录。

边界按关键文本识别（`matchers.key_text` 去空白后比较）。两条纪律：

- **排除目录条目样式**（`toc 1/2/3`）的段落再找边界：目录里的「第一章 引言」不是正文起点；
  但目录标题那一段本身可以当边界——它往往就是 TOC 域的 begin 段，按域区间排会把它一起排掉。
- **找不到边界 = 该模块缺失**，不猜。缺失由 `GLB-26` 报，本层不补。

区间是段落下标（含端点），**首尾相接、互不重叠、覆盖全篇**；`COVER` 是第一个边界之前的一切。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from ..parse.model import Para
from .matchers import is_appendix_title, is_chapter, is_toc_entry_style, key_text


class Scope(StrEnum):
    COVER = "cover"
    ABS_C = "abs_c"
    ABS_E = "abs_e"
    TOC = "toc"
    BODY = "body"
    REFS = "refs"
    ACK = "ack"
    APPENDIX = "appendix"


# 有显式边界的模块，顺序即文档顺序；封面无边界文本，是第一个边界之前的区间
_ORDER: tuple[Scope, ...] = (
    Scope.ABS_C,
    Scope.ABS_E,
    Scope.TOC,
    Scope.BODY,
    Scope.REFS,
    Scope.ACK,
    Scope.APPENDIX,
)


def _matches(scope: Scope, text: str) -> bool:
    key = key_text(text)
    if scope is Scope.ABS_C:
        return key == "摘要"
    if scope is Scope.ABS_E:
        return key.upper() == "ABSTRACT"
    if scope is Scope.TOC:
        return key == "目录"
    if scope is Scope.BODY:
        return is_chapter(key)
    if scope is Scope.REFS:
        return key == "参考文献"
    if scope is Scope.ACK:
        return key == "致谢"
    return is_appendix_title(key)


@dataclass(frozen=True, slots=True)
class ScopeRange:
    """一个作用域覆盖的段落下标区间（含端点）。"""

    scope: Scope
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start + 1

    def __contains__(self, index: object) -> bool:
        return isinstance(index, int) and self.start <= index <= self.end


def partition(paragraphs: Sequence[Para]) -> tuple[ScopeRange, ...]:
    """把段落序列切成连续的作用域区间。"""
    n = len(paragraphs)
    if n == 0:
        return ()
    bounds: list[tuple[Scope, int]] = []
    last = -1
    for scope in _ORDER:
        hit = next(
            (
                i
                for i in range(last + 1, n)
                if not is_toc_entry_style(paragraphs[i].style) and _matches(scope, paragraphs[i].text)
            ),
            None,
        )
        if hit is not None:
            bounds.append((scope, hit))
            last = hit
    # COVER 从 0 起；每个区间的终点是下一个边界的前一段，最后一段到文末
    marks: list[tuple[Scope, int]] = [(Scope.COVER, 0), *bounds]
    ranges: list[ScopeRange] = []
    for k, (scope, start) in enumerate(marks):
        end = marks[k + 1][1] - 1 if k + 1 < len(marks) else n - 1
        if end >= start:
            ranges.append(ScopeRange(scope=scope, start=start, end=end))
    return tuple(ranges)


def scope_map(paragraphs: Sequence[Para]) -> tuple[Scope, ...]:
    """每个段落的所属作用域（与段落数等长），供 `blocks.tag_blocks` 使用。"""
    out: list[Scope] = []
    for scope_range in partition(paragraphs):
        out.extend([scope_range.scope] * scope_range.size)
    return tuple(out)
