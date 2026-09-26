"""整体规则 GLB-01 ~ GLB-28。

跨作用域的整篇事实（分节 / 页眉页脚 / 页面设置 / 分页 / 模块完整性 / 自动编号）走
`CheckContext`——它本身就是块序列，所以块级选择器照用，另挂分节与全部段落。本模块只读
上下文，不碰 XML（分层契约）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..index import MODULE_ORDER, detected_modules, module_spans
from ..parse.model import HeaderFooter, Run, Section
from ..semantics import select
from ..semantics.blocks import Block, CheckContext, Scope
from ..semantics.matchers import has_cjk
from .base import Comparison, Rule, ToleranceKey, attrgetter
from .catalog import text
from .support import BlockSel, last_of, neighbour_flag

HEADER_TEXT = "山东石油化工学院本科毕业设计（论文）"
A4_PT = (595.28, 841.89)
MARGIN_PT = 73.7  # 2.6 cm = 1474 缇 = 73.7 pt


# ── 模块完整性（GLB-26 / GLB-27）───────────────────────────────
#
# 模块识别是**索引**的事（`index.module_spans` 是唯一的模块事实来源）；这里只判定。


def module_sequence(blocks: Sequence[Block]) -> tuple[str, ...]:
    """按出现顺序排出的模块名（目录条目与重复出现都排除）。"""
    return detected_modules(module_spans(blocks))


def module_units(blocks: Sequence[Block]) -> tuple[tuple[str, ...], ...]:
    return (module_sequence(blocks),)


def modules_present(sequence: tuple[str, ...]) -> str:
    missing = [name for name in MODULE_ORDER if name not in sequence]
    return "八模块齐全" if not missing else "未识别到" + "、".join(missing)


def module_order(sequence: tuple[str, ...]) -> str:
    expected = [name for name in MODULE_ORDER if name in sequence]
    return "顺序正确" if list(sequence) == expected else "模块顺序有误"


# ── 分节选取 ───────────────────────────────────────────────────


def _scope_sections(ctx: CheckContext, scope: Scope) -> tuple[Section, ...]:
    """含有该作用域块的分节（去重、按序）。"""
    wanted = {b.para.section for b in ctx if b.scope is scope and b.para.section is not None}
    return tuple(s for s in ctx.sections if s.index in wanted)


def _sections_from(ctx: CheckContext, scope: Scope) -> tuple[Section, ...]:
    """从该作用域起，到文末的所有分节（用于「适用范围」类规则）。"""
    indexes = [b.para.section for b in ctx if b.scope is scope and b.para.section is not None]
    if not indexes:
        return ()
    start = min(indexes)
    return tuple(s for s in ctx.sections if s.index >= start)


def _default(records: tuple[HeaderFooter, ...]) -> HeaderFooter | None:
    return next((record for record in records if record.ref_type == "default"), None)


def _distinct_parts(ctx: CheckContext, kind: str) -> tuple[HeaderFooter, ...]:
    """全篇出现的页眉 / 页脚部件（按部件去重，继承的同一部件只判一次）。"""
    seen: set[str] = set()
    out: list[HeaderFooter] = []
    for section in ctx.sections:
        records = section.headers if kind == "header" else section.footers
        record = _default(records)
        if record is None or record.part is None or record.part in seen:
            continue
        seen.add(record.part)
        out.append(record)
    return tuple(out)


def headers(ctx: CheckContext) -> tuple[HeaderFooter, ...]:
    return _distinct_parts(ctx, "header")


def page_footers(ctx: CheckContext) -> tuple[HeaderFooter, ...]:
    return tuple(record for record in _distinct_parts(ctx, "footer") if record.page_fields > 0)


def page_number_runs(ctx: CheckContext) -> tuple[Run, ...]:
    return tuple(run for footer in page_footers(ctx) for run in footer.page_number_runs)


def _cjk_ea(record: HeaderFooter) -> str | None:
    for para in record.paragraphs:
        for run in para.runs:
            if run.text.strip() and has_cjk(run.text):
                return run.ea
    return None


def _visible_size(record: HeaderFooter) -> float | None:
    for para in record.paragraphs:
        for run in para.runs:
            if run.text.strip():
                return run.size
    return None


def _footer_align(record: HeaderFooter) -> str | None:
    para = next(iter(record.page_number_paragraphs), None)
    return None if para is None else para.align


def _header_align(record: HeaderFooter) -> str | None:
    para = next((item for item in record.paragraphs if item.text.strip()), None)
    return None if para is None else para.align


# ── 适用范围判定 ───────────────────────────────────────────────


def header_applies(section: Section) -> bool:
    record = _default(section.headers)
    return record is not None and record.part is not None and bool(record.text.strip())


def footer_has_page(section: Section) -> bool:
    record = _default(section.footers)
    return record is not None and record.part is not None and record.page_fields > 0


def no_page_number(section: Section) -> bool:
    record = _default(section.footers)
    return record is None or record.part is None or record.page_fields == 0


def page_number_format(section: Section) -> str:
    return section.page_number_format or "decimal"


def paper_size(section: Section) -> tuple[float | None, float | None]:
    return (section.width_pt, section.height_pt)


# ── 分页 ───────────────────────────────────────────────────────


def _starts_new_page(sel: BlockSel) -> Any:
    return neighbour_flag(sel, before=True, pred=lambda b: b.para.section_break or b.para.has_page_break)


def new_page_verdict(pair: tuple[Block, bool]) -> str:
    block, previous_break = pair
    return "另起一页" if (block.para.has_page_break or previous_break) else "未另起一页"


def cover_break_verdict(block: Block) -> bool:
    return block.para.section_break or block.para.has_page_break


def toc_title(blocks: Sequence[Block]) -> tuple[Block, ...]:
    return select.by_scope(select.module_titles(blocks), Scope.TOC)


def refs_title(blocks: Sequence[Block]) -> tuple[Block, ...]:
    return select.by_scope(select.module_titles(blocks), Scope.REFS)


def ack_title(blocks: Sequence[Block]) -> tuple[Block, ...]:
    return select.by_scope(select.module_titles(blocks), Scope.ACK)


def app_title(blocks: Sequence[Block]) -> tuple[Block, ...]:
    return select.by_scope(select.module_titles(blocks), Scope.APPENDIX)


def first_chapter(blocks: Sequence[Block]) -> tuple[Block, ...]:
    chapters = select.chapters(blocks)
    return chapters[:1]


# ── 自动编号（GLB-28）─────────────────────────────────────────

_NUMBERING_HINT = object()  # 包里存在 numbering.xml 的兜底提示（无法判定，不是通过）


def auto_numbered(ctx: CheckContext) -> tuple[object, ...]:
    """全文（正文 / 表格 / 文本框；不含页眉页脚）使用有效自动编号的段落。"""
    items: list[object] = [para for para in ctx.paragraphs if para.numbering is not None]
    if ctx.has_numbering_part:
        items.append(_NUMBERING_HINT)
    return tuple(items)


def auto_numbering_verdict(item: object) -> str | None:
    if item is _NUMBERING_HINT:
        return None  # numbering.xml 存在：附提示，交报告「无法判定」栏
    return "使用自动编号"


REGISTRY: tuple[Rule[Any, Any], ...] = (
    Rule(
        id="GLB-26",
        of=module_units,
        prop=modules_present,
        expect="八模块齐全",
        src=text("GLB-26"),
    ),
    Rule(
        id="GLB-27",
        of=module_units,
        prop=module_order,
        expect="顺序正确",
        src=text("GLB-27"),
    ),
    Rule(
        id="GLB-28",
        of=auto_numbered,
        prop=auto_numbering_verdict,
        expect="手动编号",
        src=text("GLB-28"),
    ),
    Rule(id="GLB-01", of=headers, prop=lambda hf: hf.text.strip(), expect=HEADER_TEXT, src=text("GLB-01")),
    Rule(id="GLB-02", of=headers, prop=_cjk_ea, expect="黑体", src=text("GLB-02")),
    Rule(
        id="GLB-03",
        of=headers,
        prop=_visible_size,
        expect=10.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("GLB-03"),
    ),
    Rule(id="GLB-04", of=headers, prop=_header_align, expect="center", src=text("GLB-04")),
    Rule(
        id="GLB-05",
        of=lambda ctx: _sections_from(ctx, Scope.ABS_C),
        prop=header_applies,
        expect=True,
        src=text("GLB-05"),
    ),
    Rule(
        id="GLB-06",
        of=lambda ctx: _sections_from(ctx, Scope.BODY),
        prop=footer_has_page,
        expect=True,
        src=text("GLB-06"),
    ),
    Rule(
        id="GLB-07",
        of=lambda ctx: _sections_from(ctx, Scope.BODY),
        prop=page_number_format,
        expect="decimal",
        src=text("GLB-07"),
    ),
    Rule(id="GLB-08", of=page_footers, prop=_footer_align, expect="center", src=text("GLB-08")),
    Rule(
        id="GLB-09",
        of=page_number_runs,
        prop=attrgetter("west"),
        expect="Times New Roman",
        src=text("GLB-09"),
    ),
    Rule(
        id="GLB-10",
        of=page_number_runs,
        prop=attrgetter("size"),
        expect=10.5,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.SIZE_PT,
        src=text("GLB-10"),
    ),
    Rule(
        id="GLB-11",
        of=lambda ctx: _scope_sections(ctx, Scope.COVER),
        prop=no_page_number,
        expect=True,
        src=text("GLB-11"),
    ),
    Rule(
        id="GLB-12",
        of=lambda ctx: _scope_sections(ctx, Scope.ABS_C),
        prop=no_page_number,
        expect=True,
        src=text("GLB-12"),
    ),
    Rule(
        id="GLB-13",
        of=lambda ctx: _scope_sections(ctx, Scope.ABS_E),
        prop=no_page_number,
        expect=True,
        src=text("GLB-13"),
    ),
    Rule(
        id="GLB-14",
        of=lambda ctx: _scope_sections(ctx, Scope.TOC),
        prop=no_page_number,
        expect=True,
        src=text("GLB-14"),
    ),
    Rule(
        id="GLB-15",
        of=lambda ctx: ctx.sections,
        prop=paper_size,
        expect=A4_PT,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.PAPER_PT,
        src=text("GLB-15"),
    ),
    Rule(
        id="GLB-16",
        of=lambda ctx: ctx.sections,
        prop=attrgetter("top_pt"),
        expect=MARGIN_PT,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.MARGIN_PT,
        src=text("GLB-16"),
    ),
    Rule(
        id="GLB-17",
        of=lambda ctx: ctx.sections,
        prop=attrgetter("bottom_pt"),
        expect=MARGIN_PT,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.MARGIN_PT,
        src=text("GLB-17"),
    ),
    Rule(
        id="GLB-18",
        of=lambda ctx: ctx.sections,
        prop=attrgetter("left_pt"),
        expect=MARGIN_PT,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.MARGIN_PT,
        src=text("GLB-18"),
    ),
    Rule(
        id="GLB-19",
        of=lambda ctx: ctx.sections,
        prop=attrgetter("right_pt"),
        expect=MARGIN_PT,
        cmp=Comparison.APPROX,
        tol=ToleranceKey.MARGIN_PT,
        src=text("GLB-19"),
    ),
    Rule(
        id="GLB-20",
        of=last_of(lambda blocks: select.by_scope(blocks, Scope.COVER)),
        prop=cover_break_verdict,
        expect=True,
        src=text("GLB-20"),
    ),
    Rule(
        id="GLB-21",
        of=_starts_new_page(toc_title),
        prop=new_page_verdict,
        expect="另起一页",
        src=text("GLB-21"),
    ),
    Rule(
        id="GLB-22",
        of=_starts_new_page(first_chapter),
        prop=new_page_verdict,
        expect="另起一页",
        src=text("GLB-22"),
    ),
    Rule(
        id="GLB-23",
        of=_starts_new_page(refs_title),
        prop=new_page_verdict,
        expect="另起一页",
        src=text("GLB-23"),
    ),
    Rule(
        id="GLB-24",
        of=_starts_new_page(ack_title),
        prop=new_page_verdict,
        expect="另起一页",
        src=text("GLB-24"),
    ),
    Rule(
        id="GLB-25",
        of=_starts_new_page(app_title),
        prop=new_page_verdict,
        expect="另起一页",
        src=text("GLB-25"),
    ),
)
