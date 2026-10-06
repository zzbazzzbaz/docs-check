"""具名选择器：**对象识别的唯一出处**。

规则只从选择器取对象，不自己写判据——同一条口径只实现一次（"只判中文字符"
"只判字母数字""编号段让开"都落在这里）。所有选择器都是纯函数：输入块序列，
输出块或 run。

「编号让开」是需求 §3.4 的降级实现：有**有效自动编号**（`para.numbering is not None`）
的段落不进依赖编号文本的规则，由 `GLB-28` 单独报；这是**选择器过滤**，不是引擎抑制机制。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..parse import Run
from .blocks import Block
from .matchers import (
    formula_no,
    has_ascii_alnum,
    has_cjk,
    is_appendix_sub,
    is_chapter,
    is_citation,
    is_continued_table_caption,
    is_toc_entry_style,
)
from .roles import Role
from .scope import Scope

BlockSeq = Sequence[Block]
_BlockPred = Callable[[Block], bool]
_RunPred = Callable[[Run], bool]


def by_role(blocks: BlockSeq, role: Role) -> tuple[Block, ...]:
    return tuple(b for b in blocks if b.role is role)


def by_scope(blocks: BlockSeq, scope: Scope) -> tuple[Block, ...]:
    return tuple(b for b in blocks if b.scope is scope)


def _select(blocks: BlockSeq, pred: _BlockPred) -> tuple[Block, ...]:
    return tuple(b for b in blocks if pred(b))


# ── 按角色 ──────────────────────────────────────────────────────


def module_titles(blocks: BlockSeq) -> tuple[Block, ...]:
    return by_role(blocks, Role.TITLE)


def body_paragraphs(blocks: BlockSeq) -> tuple[Block, ...]:
    """正文段落：正文区内的正文角色、非空、非表格、不承载图片 / 公式。"""
    return _select(
        blocks,
        lambda b: (
            b.role is Role.BODY and b.scope is Scope.BODY and not b.para.in_table and not b.para.objects.any
        ),
    )


def _headings(blocks: BlockSeq, role: Role) -> tuple[Block, ...]:
    """按角色取标题（含非正文作用域，如附录二级标题）；规则如需限定作用域自行叠加 `by_scope`。"""
    return by_role(blocks, role)


def h1(blocks: BlockSeq) -> tuple[Block, ...]:
    return _headings(blocks, Role.H1)


def h2(blocks: BlockSeq) -> tuple[Block, ...]:
    return _headings(blocks, Role.H2)


def h3(blocks: BlockSeq) -> tuple[Block, ...]:
    return _headings(blocks, Role.H3)


def h4(blocks: BlockSeq) -> tuple[Block, ...]:
    """三级以下标题（按大纲级别）。"""
    return _headings(blocks, Role.H4)


def h4_no_auto(blocks: BlockSeq) -> tuple[Block, ...]:
    """三级以下标题，且**没有**有效自动编号（`TXT-19` 等编号类规则用它）。"""
    return tuple(b for b in h4(blocks) if b.para.numbering is None)


def captions_fig(blocks: BlockSeq) -> tuple[Block, ...]:
    return by_role(blocks, Role.CAPTION_FIG)


def captions_tab(blocks: BlockSeq) -> tuple[Block, ...]:
    """**普通**表题（`^表\\d+-\\d+`）。`续表` 是独立对象，不套用普通表题规则。

    续表由 `TXT-50` 判（需分页信息，本期不做）；这里排除它，避免 `assign_role`
    把「续表X-Y」也当成表题后，被 `TXT-43/45/47` 误报。
    """
    return tuple(b for b in by_role(blocks, Role.CAPTION_TAB) if not is_continued_table_caption(b.para.text))


def continued_table_captions(blocks: BlockSeq) -> tuple[Block, ...]:
    """续表题（`^续表\\d+-\\d+`）；本期无规则使用（`TXT-50` 不做），仅为识别留存。"""
    return tuple(b for b in by_role(blocks, Role.CAPTION_TAB) if is_continued_table_caption(b.para.text))


def is_formula_paragraph(block: Block) -> bool:
    """**独占一行**的公式对象：段落里除公式对象外没有中文正文。

    行内公式、或整段「式中…」说明（文字全裹在对象里）属**正文**，不算公式段落；
    `TXT-32/33` 只判真正的公式，不把它们当成「缺编号的公式」。
    """
    return block.role is Role.FORMULA and not has_cjk(block.para.text)


def formula_paragraphs(blocks: BlockSeq) -> tuple[Block, ...]:
    return tuple(b for b in blocks if is_formula_paragraph(b))


def formula_groups(blocks: BlockSeq) -> tuple[tuple[Block, ...], ...]:
    """把正文里**相邻的**公式段落合并成一个「公式单元」。

    一个公式常被拆成多段对象：跨行公式，或「公式 + 式中说明」共用 1 个编号。
    编号与对齐按单元判，续行 / 说明不会各自被当成独立公式。
    """
    groups: list[list[Block]] = []
    current: list[Block] = []
    for block in blocks:
        if block.scope is Scope.BODY and is_formula_paragraph(block):
            current.append(block)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return tuple(tuple(group) for group in groups)


def formula_align_targets(blocks: BlockSeq) -> tuple[Block, ...]:
    """`TXT-33` 判哪些段落：单元里**带编号**的段都要居中；整单元没编号则判首段。"""
    targets: list[Block] = []
    for group in formula_groups(blocks):
        numbered = [b for b in group if formula_no(b.para.text) is not None]
        targets.extend(numbered or group[:1])
    return tuple(targets)


def ref_items(blocks: BlockSeq) -> tuple[Block, ...]:
    return by_role(blocks, Role.REF_ITEM)


def ref_items_no_auto(blocks: BlockSeq) -> tuple[Block, ...]:
    """文献条目，且**没有**有效自动编号（`REF-10` / `REF-11` 用它）。"""
    return tuple(b for b in ref_items(blocks) if b.para.numbering is None)


def keywords_c(blocks: BlockSeq) -> tuple[Block, ...]:
    return _select(blocks, lambda b: b.role is Role.KEYWORDS and b.scope is Scope.ABS_C)


def keywords_e(blocks: BlockSeq) -> tuple[Block, ...]:
    return _select(blocks, lambda b: b.role is Role.KEYWORDS and b.scope is Scope.ABS_E)


def empty_blocks(blocks: BlockSeq) -> tuple[Block, ...]:
    return by_role(blocks, Role.EMPTY)


def unknown_blocks(blocks: BlockSeq) -> tuple[Block, ...]:
    """未识别结构：进报告，不是通过。"""
    return by_role(blocks, Role.UNKNOWN)


# ── 按文本（识别锚点宽松，与判定正交）────────────────────────────


def chapters(blocks: BlockSeq) -> tuple[Block, ...]:
    """正文区文本以 `第X章` 开头的段落（**不依赖大纲级别**，`TXT-51` 用它）。"""
    return _select(blocks, lambda b: b.scope is Scope.BODY and is_chapter(b.para.text))


def appendix_subs(blocks: BlockSeq) -> tuple[Block, ...]:
    """附录子标题：`附录 + 非空白字符`（`附录a` / `附录一` / `附录Ａ` 都算，不看级别）。"""
    return _select(blocks, lambda b: b.scope is Scope.APPENDIX and is_appendix_sub(b.para.text))


def appendix_subs_no_auto(blocks: BlockSeq) -> tuple[Block, ...]:
    """附录子标题，且**没有**有效自动编号（`APP-06` 用它）。"""
    return tuple(b for b in appendix_subs(blocks) if b.para.numbering is None)


def toc_entries(blocks: BlockSeq) -> tuple[Block, ...]:
    """目录条目：目录区内样式名为 `toc 1/2/3` 的段落（层级看样式名）。"""
    return _select(
        blocks,
        lambda b: b.scope is Scope.TOC and is_toc_entry_style(b.para.style),
    )


# ── 按字符（run 级）─────────────────────────────────────────────


def _runs(blocks: BlockSeq, pred: _RunPred) -> tuple[Run, ...]:
    return tuple(run for b in blocks for run in b.para.runs if pred(run))


def cjk_runs(blocks: BlockSeq) -> tuple[Run, ...]:
    """含中文字符的 run（只判中文字体用）。"""
    return _runs(blocks, lambda r: has_cjk(r.text))


def west_runs(blocks: BlockSeq) -> tuple[Run, ...]:
    """含 ASCII 字母或数字的 run（只判字母数字，排除标点）。"""
    return _runs(blocks, lambda r: has_ascii_alnum(r.text))


def superscript_runs(blocks: BlockSeq) -> tuple[Run, ...]:
    return _runs(blocks, lambda r: r.va == "superscript")


def citation_runs(blocks: BlockSeq) -> tuple[Run, ...]:
    """引用标注 run：**按文本 `[数字]` 认**，不看是否上标（`TXT-30` 才判上标）。"""
    return _runs(blocks, lambda r: is_citation(r.text))


def caption_runs(blocks: BlockSeq) -> tuple[Run, ...]:
    """图题 / 表题里的 run。"""
    captions = tuple(b for b in blocks if b.role in (Role.CAPTION_FIG, Role.CAPTION_TAB))
    return _runs(captions, lambda _r: True)
