"""L3 整篇索引：跨作用域事实的**唯一收集处**（`DocumentIndex`）。

只收集事实，不做判定：

- `modules`：模块 → 块区间（8 个模块，含封面）
- `chapters`：章 → 块区间（正文区里文本以 `第…章` 开头的全部段落）
- `floats`：图 / 表 / 公式登记（章号-序号 → 段号）
- `citations`：正文引用标注（编号 + 首次出现顺序）
- `toc_entries`：目录条目（层级 / 文本）

两条纪律（规则文档 `9-整体`「跨作用域规则」）：

1. **宽松收集，规则负责收缩**——例如章候选不要求大纲级别，`outline` / `style` / `is_heading1`
   一并带上；若用"大纲级别"当收集条件，级别写错就收集不到，连续性规则反而静默通过。
2. **取不到就显式「无法判定」**——定位不到正文区时 `citations` 为 `None`，不静默给空集合。

本层不 import lxml（分层契约），也不做任何合规判断。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..parse.model import Document, Para
from ..semantics.blocks import Block
from ..semantics.matchers import (
    chapter_no,
    citation_numbers,
    figure_no,
    formula_no,
    is_appendix_title,
    is_chapter,
    is_toc_entry_style,
    key_text,
    table_no,
)

# 固定顺序：封面在前，其余与文档顺序一致（`GLB-27` 比的就是这个顺序）
MODULE_ORDER: tuple[str, ...] = (
    "封面",
    "中文摘要",
    "英文摘要",
    "目录",
    "正文",
    "参考文献",
    "致谢",
    "附录",
)

COVER_TITLE = "本科生毕业设计（论文）"

# 模块的关键文本（识别锚点，去空白后比较）；`GLB-26` / `GLB-27` 与索引共用这一份
_MODULE_KEYWORDS: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("封面", lambda text: text == COVER_TITLE),
    ("中文摘要", lambda text: text == "摘要"),
    ("英文摘要", lambda text: text.upper() == "ABSTRACT"),
    ("目录", lambda text: text == "目录"),
    ("正文", is_chapter),
    ("参考文献", lambda text: text == "参考文献"),
    ("致谢", lambda text: text == "致谢"),
    ("附录", is_appendix_title),
)
_KEYWORD: dict[str, Callable[[str], bool]] = dict(_MODULE_KEYWORDS)

# 目录条目样式名 `toc N`：**宽松**收任意层级，1/2/3 之外的层级由索引自检报出
_TOC_STYLE = re.compile(r"^toc\s*(\d+)$")


def matches_module(name: str, text: str) -> bool:
    """文本是否是某模块的关键文本（识别用，去空白后比较；不要求空格 / 样式正确）。"""
    predicate = _KEYWORD.get(name)
    return predicate is not None and predicate(key_text(text))


@dataclass(frozen=True, slots=True)
class ModuleSpan:
    """一个模块覆盖的块区间（含端点）。

    `title_found` 表示该模块的关键文本确实识别到了；封面缺失关键文本时仍保留一个隐式区间，
    这样区间始终首尾相接、覆盖全篇（区间连续是索引自检的不变量）。
    """

    name: str
    start: int
    end: int
    title_found: bool


def module_spans(blocks: Sequence[Block]) -> tuple[ModuleSpan, ...]:
    """按关键文本识别 8 个模块，返回**按出现顺序**排列的区间。

    每个模块取文档里**第一处**关键文本（排除 `toc N` 目录条目）；不设"上一模块之后的游标"，
    所以乱序的模块也能各自被收进来，交给 `GLB-27` 判，而不是被前面的模块吞掉。
    """
    total = len(blocks)
    if total == 0:
        return ()
    hits: list[tuple[int, str]] = []
    for name in MODULE_ORDER:
        hit = next(
            (
                i
                for i, block in enumerate(blocks)
                if matches_module(name, block.para.text) and not is_toc_entry_style(block.para.style)
            ),
            None,
        )
        if hit is not None:
            hits.append((hit, name))
    hits.sort(key=lambda item: item[0])
    if not hits:
        return (ModuleSpan(name="封面", start=0, end=total - 1, title_found=False),)
    spans: list[ModuleSpan] = []
    if hits[0][1] != "封面":
        # 封面关键文本缺失（或不在最前）：把第一个边界之前的一切归给封面
        spans.append(ModuleSpan(name="封面", start=0, end=hits[0][0] - 1, title_found=False))
    for position, (hit, name) in enumerate(hits):
        start = 0 if not spans else hit
        end = hits[position + 1][0] - 1 if position + 1 < len(hits) else total - 1
        spans.append(ModuleSpan(name=name, start=start, end=end, title_found=True))
    return tuple(spans)


def detected_modules(spans: Sequence[ModuleSpan]) -> tuple[str, ...]:
    """识别到关键文本的模块名，按出现顺序（`GLB-26` / `GLB-27` 消费它）。"""
    return tuple(span.name for span in spans if span.title_found)


@dataclass(frozen=True, slots=True)
class Chapter:
    """一个章候选。区间到下一章候选之前为止。

    `outline` / `style` / `is_heading1` 一并带上，是否真的是标题由规则收缩。
    """

    no: int
    text: str
    start: int
    end: int
    outline: int | None
    style: str | None
    is_heading1: bool


@dataclass(frozen=True, slots=True)
class FloatRef:
    """一条图 / 表 / 公式登记。公式段没有编号时 `no` 为 `None`（无法判定，不是"没有"）。"""

    kind: str
    no: str | None
    para: int


@dataclass(frozen=True, slots=True)
class Floats:
    """图 / 表 / 公式登记与公式对象计数。"""

    figures: tuple[FloatRef, ...]
    tables: tuple[FloatRef, ...]
    formulas: tuple[FloatRef, ...]
    formula_objects: int


@dataclass(frozen=True, slots=True)
class Citation:
    """一条正文引用标注：编号 + 所在段 + 首次出现次序（1 起）。"""

    no: int
    para: int
    order: int


@dataclass(frozen=True, slots=True)
class TocEntry:
    """一条目录条目：层级（看样式名）+ 原始文本（含页码）+ 所在段。"""

    level: int
    text: str
    para: int


@dataclass(frozen=True, slots=True)
class DocumentIndex:
    """整篇只读索引。`citations` 为 `None` 表示**无法判定**（定位不到正文区）。"""

    modules: tuple[ModuleSpan, ...]
    chapters: tuple[Chapter, ...]
    floats: Floats
    citations: tuple[Citation, ...] | None
    toc_entries: tuple[TocEntry, ...]


def _chapters(blocks: Sequence[Block], body: ModuleSpan | None) -> tuple[Chapter, ...]:
    if body is None:
        return ()
    found: list[tuple[int, str, int, int | None, str | None]] = []
    for i in range(body.start, body.end + 1):
        block = blocks[i]
        if is_toc_entry_style(block.para.style):
            continue
        key = key_text(block.para.text)
        no = chapter_no(key)
        if no is None:
            continue
        found.append((no, key[:24], i, block.para.outline, block.para.style))
    out: list[Chapter] = []
    for position, (no, text, start, outline, style) in enumerate(found):
        end = found[position + 1][2] - 1 if position + 1 < len(found) else body.end
        out.append(
            Chapter(
                no=no,
                text=text,
                start=start,
                end=end,
                outline=outline,
                style=style,
                is_heading1=outline == 0,
            )
        )
    return tuple(out)


def _floats(paragraphs: Sequence[Para]) -> Floats:
    figures: list[FloatRef] = []
    tables: list[FloatRef] = []
    formulas: list[FloatRef] = []
    objects = 0
    for para in paragraphs:
        figure = figure_no(para.text)
        if figure is not None:
            figures.append(FloatRef(kind="figure", no=f"{figure[0]}-{figure[1]}", para=para.id))
        table = table_no(para.text)
        if table is not None:
            tables.append(FloatRef(kind="table", no=f"{table[0]}-{table[1]}", para=para.id))
        if para.objects.ole or para.objects.omath:
            objects += para.objects.ole + para.objects.omath
            formula = formula_no(para.text)
            number = f"{formula[0]}-{formula[1]}" if formula is not None else None
            formulas.append(FloatRef(kind="formula", no=number, para=para.id))
    return Floats(
        figures=tuple(figures),
        tables=tuple(tables),
        formulas=tuple(formulas),
        formula_objects=objects,
    )


def _citations(blocks: Sequence[Block], body: ModuleSpan | None) -> tuple[Citation, ...] | None:
    """正文区的引用标注：**按文本 `[数字]` 认，不看是否上标**（`FR-8.4` 的修正）。

    用上标当锚点再判上标是恒真式（`TXT-30` 判的就是上标），所以识别锚点改为文本形状
    （`matchers.is_citation` 的超集），`TXT-30` 再从集合里挑没上标的报。
    """
    if body is None:
        return None  # 定位不到正文区 = 无法判定，宁可显式给出，也不当作「没有引用」
    seen: dict[int, int] = {}
    out: list[Citation] = []
    for i in range(body.start, body.end + 1):
        for run in blocks[i].para.runs:
            for number in citation_numbers(run.text):
                if number not in seen:
                    seen[number] = len(seen) + 1
                    out.append(Citation(no=number, para=i, order=seen[number]))
    return tuple(out)


def _toc_entries(blocks: Sequence[Block], toc: ModuleSpan | None) -> tuple[TocEntry, ...]:
    if toc is None:
        return ()
    out: list[TocEntry] = []
    for i in range(toc.start, toc.end + 1):
        match = _TOC_STYLE.match((blocks[i].para.style or "").strip().lower())
        if match is not None:
            out.append(TocEntry(level=int(match.group(1)), text=blocks[i].para.text, para=i))
    return tuple(out)


def index_from(paragraphs: Sequence[Para], blocks: Sequence[Block]) -> DocumentIndex:
    """从**正文故事区段落**与块序列收集整篇事实。

    规则层手里只有 `CheckContext`（块序列 + 全部段落），没有 `Document`，所以事实收集的
    入口按"段落 + 块"暴露；`build_index` 只是它的 `Document` 版包装。
    """
    modules = module_spans(blocks)
    body = next((span for span in modules if span.name == "正文"), None)
    toc = next((span for span in modules if span.name == "目录"), None)
    return DocumentIndex(
        modules=modules,
        chapters=_chapters(blocks, body),
        floats=_floats(paragraphs),
        citations=_citations(blocks, body),
        toc_entries=_toc_entries(blocks, toc),
    )


def build_index(doc: Document, blocks: Sequence[Block]) -> DocumentIndex:
    """收集整篇事实（`doc.paragraphs` 即正文故事区的全部段落）。"""
    return index_from(doc.paragraphs, blocks)
