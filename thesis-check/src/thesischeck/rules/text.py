"""正文规则 TXT-01 ~ TXT-52（49 条：批 1 的 46 条 + 批 2 的 TXT-36/42/48/49/52；
剔除渲染通道 1 条 TXT-50）。

标题对象：一级按**文本** `第X章`（宽松锚点，不依赖大纲级别）取，二 / 三 / 三级以下按
**大纲级别 / 样式名**取；属性一律走有效格式。编号形态与空格、题注位置、公式编号、
存在性写代码，其余都是一行数据。

批 2 的三条跨作用域规则（`TXT-36/42/48` 必须有引用、`TXT-49` 三线表、`TXT-52` 公式编号）
消费 `index` 的整篇事实，但只从只读上下文收集，不碰 XML。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ..index import Chapter, FloatRef
from ..parse import Cell, Run, Table
from ..semantics import Block, CheckContext, Scope, chapter_no, is_citation, select
from .base import Comparison, Rule, ToleranceKey, attrgetter
from .catalog import text
from .support import (
    H1_TEXT_SHAPE,
    H2_TEXT_SHAPE,
    H3_TEXT_SHAPE,
    BlockSel,
    blanks_after,
    cjk_of,
    context_index,
    count,
    first_cjk_font,
    flag,
    float_position,
    formula_align,
    found,
    gap_of,
    index_of,
    para_align,
    para_first_line,
    para_line,
    run_font,
    shape_verdict,
    visible_of,
    west_of,
)

_H4_SHAPE = re.compile(r"（\d+）.*")
_FIG_FORMAT = re.compile(r"图\d+-\d+.*")
_TAB_FORMAT = re.compile(r"表\d+-\d+.*")
_FIG_NO = re.compile(r"^图\s*\d+\s*-\s*\d+")
_TAB_NO = re.compile(r"^表\s*\d+\s*-\s*\d+")
_FORMULA_NO = re.compile(r"\(\d+-\d+\)")


# ── 对象识别（正文作用域内）─────────────────────────────────────


def _in_body(sel: BlockSel) -> BlockSel:
    def pick(blocks: Sequence[Block]) -> tuple[Block, ...]:
        return select.by_scope(sel(blocks), Scope.BODY)

    return pick


BODY_H1 = select.chapters
BODY_H2 = _in_body(select.h2)
BODY_H3 = _in_body(select.h3)
BODY_H4 = _in_body(select.h4)
BODY_H4_MANUAL = _in_body(select.h4_no_auto)  # 编号由手打：自动编号段让开（GLB-28）
BODY_TEXT = select.body_paragraphs
BODY_FIGS = _in_body(select.captions_fig)
BODY_TABS = _in_body(select.captions_tab)
BODY_FORMULAS = _in_body(select.formula_paragraphs)


def body_citation_runs(blocks: Sequence[Block]) -> tuple[Run, ...]:
    """正文区里的引用标注 run（按文本 `[n]` 认，是否上标由 TXT-30 判）。"""
    return tuple(
        run
        for block in select.by_scope(blocks, Scope.BODY)
        for run in block.para.runs
        if is_citation(run.text)
    )


def formula_number_runs(blocks: Sequence[Block]) -> tuple[Run, ...]:
    """公式段落里带半角 `(章号-序号)` 的 run。"""
    return tuple(
        run for block in BODY_FORMULAS(blocks) for run in block.para.runs if _FORMULA_NO.search(run.text)
    )


def _has_figure_image(block: Block) -> bool:
    return bool(block.para.objects.inline_images or block.para.objects.floating_images)


def _body_figure(block: Block) -> bool:
    return block.scope is Scope.BODY and _has_figure_image(block)


def _body_table(block: Block) -> bool:
    return block.scope is Scope.BODY and block.para.in_table


FIG_ABOVE = float_position(BODY_FIGS, target=_body_figure, below=False)
TAB_BELOW = float_position(BODY_TABS, target=_body_table, below=True)


# ── 写代码的判定 ────────────────────────────────────────────────


def chapter_verdict(chapters: tuple[Block, ...]) -> str:
    """TXT-51：第一~第五章是否齐全（宽松锚点收集，不依赖大纲级别）。"""
    found_numbers = {no for block in chapters if (no := chapter_no(block.para.text)) is not None}
    missing = [zh for zh, no in zip("一二三四五", range(1, 6), strict=True) if no not in found_numbers]
    return "五章齐全" if not missing else "未识别到第" + "、第".join(missing) + "章"


def chapter_page_breaks(blocks: Sequence[Block]) -> tuple[tuple[Block, bool], ...]:
    """TXT-07：第二~第五章是否另起一页（段前分页 / 分页符 / 前一节以分节符结束）。"""
    out: list[tuple[Block, bool]] = []
    for block in select.chapters(blocks):
        number = chapter_no(block.para.text)
        if number is None or not 2 <= number <= 5:
            continue
        index = index_of(blocks, block)
        previous = blocks[index - 1] if index > 0 else None
        started = block.para.has_page_break or (previous is not None and previous.para.section_break)
        out.append((block, started))
    return tuple(out)


def formula_number_verdict(group: tuple[Block, ...]) -> str:
    """TXT-32：一个公式**单元**里必须有半角圆括号、半角 `-` 的 `(章号-序号)`。

    单元 = 相邻的公式对象段（跨行公式 / 「公式 + 式中说明」只算一个公式）。
    """
    return "合规" if any(_FORMULA_NO.search(block.para.text) for block in group) else "公式缺编号"


# ── 第二批（FR-8）：三线表 / 公式编号 / 必须有引用 ─────────────


def tables(ctx: CheckContext) -> tuple[Table, ...]:
    return ctx.tables


def _horizontal_boundary(rows: tuple[tuple[Cell, ...], ...], edge: int) -> bool:
    """第 `edge` 行与第 `edge+1` 行之间是否有横线（1 起；两侧任一无 ``none`` 即算）。"""
    above, below = rows[edge - 1], rows[edge]
    return any(cell.borders.bottom for cell in above) or any(cell.borders.top for cell in below)


def three_line_result(table: Table) -> str:
    """TXT-49 判定：只有上框线、下框线、表头行下框线；无竖线、无其他内横线。"""
    rows = table.rows
    if not rows:
        return "合规"
    problems: list[str] = []
    if any(cell.borders.left or cell.borders.right for row in rows for cell in row):
        problems.append("存在竖线")
    if not any(cell.borders.top for cell in rows[0]):
        problems.append("缺上框线")
    if not any(cell.borders.bottom for cell in rows[-1]):
        problems.append("缺下框线")
    if table.n_rows > 1 and not _horizontal_boundary(rows, 1):
        problems.append("缺表头行下框线")
    if any(_horizontal_boundary(rows, edge) for edge in range(2, table.n_rows)):
        problems.append("存在多余内横线")
    return "合规" if not problems else "；".join(problems)


def three_line_verdict(table: Table) -> str | None:
    """表格线只可能来自条件格式时，缺线不是确定结论（`None` = 无法判定，不是不符合）。"""
    result = three_line_result(table)
    if result != "合规" and table.style_conditional_borders:
        return None
    return result


def _containing_chapter(chapters: tuple[Chapter, ...], para: int) -> Chapter | None:
    return next((chapter for chapter in chapters if chapter.start <= para <= chapter.end), None)


def formula_numbering_verdict(payload: tuple[tuple[Chapter, ...], tuple[FloatRef, ...]]) -> str | None:
    """TXT-52：章号 = 公式所属一级标题的章号；每章内序号恰为 `1…N`（不跳号、不重复）。"""
    chapters, formulas = payload
    if not formulas:
        return "合规"
    if not chapters:
        return None  # 定位不到一级标题，所属章无法确定
    problems: list[str] = []
    groups: dict[int, list[int]] = {}
    chapter_numbers: dict[int, int] = {}
    for ref in formulas:
        if ref.no is None:
            return None
        number, sequence = (int(part) for part in ref.no.split("-"))
        chapter = _containing_chapter(chapters, ref.para)
        if chapter is None:
            return None
        if number != chapter.no:
            problems.append(f"编号 {ref.no} 的章号 {number} 与所属第{chapter.no}章不符")
        groups.setdefault(chapter.start, []).append(sequence)
        chapter_numbers[chapter.start] = chapter.no
    for start, sequences in sorted(groups.items()):
        if sorted(sequences) != list(range(1, len(sequences) + 1)):
            problems.append(f"第{chapter_numbers[start]}章公式序号为 {sorted(sequences)}")
    return "合规" if not problems else "；".join(problems)


def formula_numbering(ctx: CheckContext) -> tuple[tuple[tuple[Chapter, ...], tuple[FloatRef, ...]], ...]:
    index = context_index(ctx)
    formulas = tuple(ref for ref in index.floats.formulas if ref.no is not None)
    return ((index.chapters, formulas),)


def reference_text(ctx: CheckContext) -> str:
    """正文区普通段落文本（题注 / 公式段 / 表格内 / 目录区已由选择器排除）。"""
    return "\n".join(block.para.text for block in select.body_paragraphs(ctx))


def _reference_units(ctx: CheckContext, refs: tuple[FloatRef, ...]) -> tuple[tuple[FloatRef, str], ...]:
    text = reference_text(ctx)
    return tuple((ref, text) for ref in refs if ref.no is not None)


def formula_units(ctx: CheckContext) -> tuple[tuple[FloatRef, str], ...]:
    return _reference_units(ctx, context_index(ctx).floats.formulas)


def figure_units(ctx: CheckContext) -> tuple[tuple[FloatRef, str], ...]:
    return _reference_units(ctx, context_index(ctx).floats.figures)


def table_units(ctx: CheckContext) -> tuple[tuple[FloatRef, str], ...]:
    return _reference_units(ctx, context_index(ctx).floats.tables)


def _reference_pattern(label: str, no: str) -> str:
    chapter, sequence = no.split("-")
    return rf"{label}\s*{chapter}\s*-\s*{sequence}"


def figure_reference_verdict(pair: tuple[FloatRef, str]) -> str:
    ref, text = pair
    if ref.no is None:
        return "合规"
    return "合规" if re.search(_reference_pattern("图", ref.no), text) else "正文缺少对该图的引用"


def table_reference_verdict(pair: tuple[FloatRef, str]) -> str:
    ref, text = pair
    if ref.no is None:
        return "合规"
    return "合规" if re.search(_reference_pattern("表", ref.no), text) else "正文缺少对该表的引用"


def formula_reference_verdict(pair: tuple[FloatRef, str]) -> str:
    """公式引用：`式(n-m)` 或 `(n-m)`（全 / 半角括号都认）。"""
    ref, text = pair
    if ref.no is None:
        return "合规"
    chapter, sequence = ref.no.split("-")
    pattern = rf"[（(]\s*{chapter}\s*-\s*{sequence}\s*[）)]"
    return "合规" if re.search(pattern, text) else "正文缺少对该公式的引用"


_H1_VERDICT = shape_verdict(H1_TEXT_SHAPE)
_H2_VERDICT = shape_verdict(H2_TEXT_SHAPE)
_H3_VERDICT = shape_verdict(H3_TEXT_SHAPE)
_H4_VERDICT = shape_verdict(_H4_SHAPE)
_FIG_VERDICT = shape_verdict(_FIG_FORMAT)
_TAB_VERDICT = shape_verdict(_TAB_FORMAT)


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="TXT-51",
        of=found(select.chapters),
        prop=chapter_verdict,
        expect="五章齐全",
        src=text("TXT-51"),
    ),
    Rule(
        id="TXT-01",
        of=BODY_H1,
        prop=_H1_VERDICT,
        expect="合规",
        src=text("TXT-01"),
    ),
    Rule(
        id="TXT-02",
        of=cjk_of(BODY_H1),
        prop=attrgetter("ea"),
        expect="黑体",
        src=text("TXT-02"),
    ),
    Rule(
        id="TXT-03",
        of=visible_of(BODY_H1),
        prop=attrgetter("size"),
        expect=16.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("TXT-03"),
    ),
    Rule(
        id="TXT-04",
        of=BODY_H1,
        prop=para_align,
        expect="center",
        src=text("TXT-04"),
    ),
    Rule(
        id="TXT-05",
        of=BODY_H1,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src=text("TXT-05"),
    ),
    Rule(
        id="TXT-06",
        of=blanks_after(BODY_H1),
        prop=count,
        expect=1,
        src=text("TXT-06"),
    ),
    Rule(
        id="TXT-07",
        of=chapter_page_breaks,
        prop=flag,
        expect=True,
        src=text("TXT-07"),
    ),
    Rule(
        id="TXT-08",
        of=BODY_H2,
        prop=_H2_VERDICT,
        expect="合规",
        src=text("TXT-08"),
    ),
    Rule(
        id="TXT-09",
        of=cjk_of(BODY_H2),
        prop=attrgetter("ea"),
        expect="黑体",
        src=text("TXT-09"),
    ),
    Rule(
        id="TXT-10",
        of=visible_of(BODY_H2),
        prop=attrgetter("size"),
        expect=14.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("TXT-10"),
    ),
    Rule(
        id="TXT-11",
        of=west_of(BODY_H2),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src=text("TXT-11"),
    ),
    Rule(
        id="TXT-12",
        of=BODY_H2,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src=text("TXT-12"),
    ),
    Rule(
        id="TXT-13",
        of=BODY_H3,
        prop=_H3_VERDICT,
        expect="合规",
        src=text("TXT-13"),
    ),
    Rule(
        id="TXT-14",
        of=cjk_of(BODY_H3),
        prop=attrgetter("ea"),
        expect="黑体",
        src=text("TXT-14"),
    ),
    Rule(
        id="TXT-15",
        of=visible_of(BODY_H3),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("TXT-15"),
    ),
    Rule(
        id="TXT-16",
        of=west_of(BODY_H3),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src=text("TXT-16"),
    ),
    Rule(
        id="TXT-17",
        of=BODY_H3,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src=text("TXT-17"),
    ),
    Rule(
        id="TXT-18",
        of=BODY_H3,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src=text("TXT-18"),
    ),
    Rule(
        id="TXT-19",
        of=BODY_H4_MANUAL,
        prop=_H4_VERDICT,
        expect="合规",
        src=text("TXT-19"),
    ),
    Rule(
        id="TXT-20",
        of=cjk_of(BODY_H4),
        prop=attrgetter("ea"),
        expect="宋体",
        src=text("TXT-20"),
    ),
    Rule(
        id="TXT-21",
        of=visible_of(BODY_H4),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("TXT-21"),
    ),
    Rule(
        id="TXT-22",
        of=west_of(BODY_H4),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src=text("TXT-22"),
    ),
    Rule(
        id="TXT-23",
        of=BODY_H4,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src=text("TXT-23"),
    ),
    Rule(
        id="TXT-24",
        of=BODY_H4,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src=text("TXT-24"),
    ),
    Rule(
        id="TXT-25",
        of=cjk_of(BODY_TEXT),
        prop=attrgetter("ea"),
        expect="宋体",
        src=text("TXT-25"),
    ),
    Rule(
        id="TXT-26",
        of=west_of(BODY_TEXT),
        prop=attrgetter("west"),
        expect="Times New Roman",
        src=text("TXT-26"),
    ),
    Rule(
        id="TXT-27",
        of=visible_of(BODY_TEXT),
        prop=attrgetter("size"),
        expect=12.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("TXT-27"),
    ),
    Rule(
        id="TXT-28",
        of=BODY_TEXT,
        prop=para_first_line,
        expect=2.0,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.INDENT_CHARS,
        src=text("TXT-28"),
    ),
    Rule(
        id="TXT-29",
        of=BODY_TEXT,
        prop=para_line,
        expect=1.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.LINE,
        src=text("TXT-29"),
    ),
    Rule(
        id="TXT-30",
        of=body_citation_runs,
        prop=attrgetter("va"),
        expect="superscript",
        src=text("TXT-30"),
    ),
    Rule(
        id="TXT-31",
        of=body_citation_runs,
        prop=run_font,
        expect=("Times New Roman", 12.0),
        src=text("TXT-31"),
    ),
    Rule(
        id="TXT-32",
        of=select.formula_groups,
        prop=formula_number_verdict,
        expect="合规",
        src=text("TXT-32"),
    ),
    Rule(
        id="TXT-33",
        of=select.formula_align_targets,
        prop=formula_align,
        expect="center",
        src=text("TXT-33"),
    ),
    Rule(
        id="TXT-34",
        of=formula_number_runs,
        prop=attrgetter("size"),
        expect=10.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("TXT-34"),
    ),
    Rule(
        id="TXT-35",
        of=formula_number_runs,
        prop=attrgetter("west"),
        expect="Times New Roman",
        src=text("TXT-35"),
    ),
    Rule(
        id="TXT-36",
        of=formula_units,
        prop=formula_reference_verdict,
        expect="合规",
        src=text("TXT-36"),
    ),
    Rule(
        id="TXT-52",
        of=formula_numbering,
        prop=formula_numbering_verdict,
        expect="合规",
        src=text("TXT-52"),
    ),
    Rule(
        id="TXT-37",
        of=BODY_FIGS,
        prop=_FIG_VERDICT,
        expect="合规",
        src=text("TXT-37"),
    ),
    Rule(
        id="TXT-38",
        of=FIG_ABOVE,
        prop=flag,
        expect=True,
        src=text("TXT-38"),
    ),
    Rule(
        id="TXT-39",
        of=BODY_FIGS,
        prop=para_align,
        expect="center",
        src=text("TXT-39"),
    ),
    Rule(
        id="TXT-40",
        of=BODY_FIGS,
        prop=first_cjk_font,
        expect=("宋体", 10.5),
        src=text("TXT-40"),
    ),
    Rule(
        id="TXT-41",
        of=BODY_FIGS,
        prop=gap_of(_FIG_NO),
        expect=1,
        src=text("TXT-41"),
    ),
    Rule(
        id="TXT-42",
        of=figure_units,
        prop=figure_reference_verdict,
        expect="合规",
        src=text("TXT-42"),
    ),
    Rule(
        id="TXT-43",
        of=BODY_TABS,
        prop=_TAB_VERDICT,
        expect="合规",
        src=text("TXT-43"),
    ),
    Rule(
        id="TXT-44",
        of=TAB_BELOW,
        prop=flag,
        expect=True,
        src=text("TXT-44"),
    ),
    Rule(
        id="TXT-45",
        of=BODY_TABS,
        prop=para_align,
        expect="center",
        src=text("TXT-45"),
    ),
    Rule(
        id="TXT-46",
        of=BODY_TABS,
        prop=first_cjk_font,
        expect=("宋体", 10.5),
        src=text("TXT-46"),
    ),
    Rule(
        id="TXT-47",
        of=BODY_TABS,
        prop=gap_of(_TAB_NO),
        expect=1,
        src=text("TXT-47"),
    ),
    Rule(
        id="TXT-48",
        of=table_units,
        prop=table_reference_verdict,
        expect="合规",
        src=text("TXT-48"),
    ),
    Rule(
        id="TXT-49",
        of=tables,
        prop=three_line_verdict,
        expect="合规",
        src=text("TXT-49"),
    ),
)
