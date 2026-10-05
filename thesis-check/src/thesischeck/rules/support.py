"""规则层共用小工具：run 选择、冒号切分、空段计数与关键词内容判定。

只组合 `semantics` 的选择器与匹配器，**不新增对象判据**（`NFR-4.3`）。作用域规则
（封面 / 摘要）都从这里取对象定位与文本切分；判定值本身仍是各规则里的数据。
跨作用域规则（批 2）从 `context_index` 取整篇只读索引，本模块只做入口转接。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from ..index import DocumentIndex, index_from
from ..parse.model import LineRule, Para, Run, Story
from ..semantics.blocks import Block, CheckContext, Role
from ..semantics.matchers import has_ascii_alnum, has_cjk

BlockSel = Callable[[Sequence[Block]], tuple[Block, ...]]
RunSel = Callable[[Sequence[Block]], tuple[Run, ...]]
TextSel = Callable[[Sequence[Block]], tuple[str, ...]]
_PairSel = Callable[[Sequence[Block]], tuple[tuple[Block, bool], ...]]
_RunPred = Callable[[Run], bool]

_COLONS = "：:"
_OTHER_SEPARATORS = ",;，、"
_PUNCT = frozenset("。；，、,;.：:！？!?…．")

# 「不是倍率行距」（`lineRule=exact` / `atLeast`）：与任何倍率期望都不相等，
# 从而被 APPROX 判为不通过，而不是被当成"取不到值"记无法判定（需求 FR-3.5）。
NOT_MULTIPLE = float("nan")

# 标题文本形状：编号 + 规定的半角空格数（识别宽松、判定严格，识别由选择器负责）
H1_TEXT_SHAPE = re.compile(r"第[一二三四五六七八九十]+章 {2}\S.*")
H2_TEXT_SHAPE = re.compile(r"\d+\.\d+ \S.*")
H3_TEXT_SHAPE = re.compile(r"\d+\.\d+\.\d+ \S.*")

# 目录二级条目形状：`N.N`（编号后空 1 格）或附录子条目「附录X…」。
# 附录子标题在目录里同为二级条目（`8-附录` APP-13），编号形态是 `附录A` 而非 `N.N`；
# 编号与题名之间的空格规范未要求（样张「附录A名词术语及缩略词」A 后无空格，见 `8-附录` APP-06），
# 故附录分支只认「附录 + 非空白字符」，不判空格。
TOC_L2_TEXT_SHAPE = re.compile(r"(?:\d+\.\d+ |附\s*录\s*)\S.*")


# ── run 谓词（字体槽 / 空白口径的唯一出处）─────────────────────────


def is_cjk_run(run: Run) -> bool:
    """含中文字符的非空白 run（判中文字体用）。"""
    return bool(run.text.strip()) and has_cjk(run.text)


def is_west_run(run: Run) -> bool:
    """含 ASCII 字母或数字的 run（判西文/数字字体用，排除标点）。"""
    return has_ascii_alnum(run.text)


def is_visible_run(run: Run) -> bool:
    """有可见字符的 run（字号 / 加粗用；空 run 不算）。"""
    return bool(run.text.strip())


def runs_of(sel: BlockSel, pred: _RunPred | None = None) -> RunSel:
    """`sel` 选中段落里满足 `pred` 的 run（`pred=None` 表示全部）。"""

    def pick(blocks: Sequence[Block]) -> tuple[Run, ...]:
        return tuple(run for block in sel(blocks) for run in block.para.runs if pred is None or pred(run))

    return pick


def cjk_of(sel: BlockSel) -> RunSel:
    return runs_of(sel, is_cjk_run)


def west_of(sel: BlockSel) -> RunSel:
    return runs_of(sel, is_west_run)


def visible_of(sel: BlockSel) -> RunSel:
    return runs_of(sel, is_visible_run)


# ── 冒号切分：前缀（含冒号）/ 内容 ────────────────────────────────


def colon_index(text: str) -> int | None:
    for index, char in enumerate(text):
        if char in _COLONS:
            return index
    return None


def split_text(text: str) -> tuple[str, str]:
    """以首个冒号（含）为界切成（前缀, 内容）；无冒号时整段算前缀。"""
    position = colon_index(text)
    if position is None:
        return text, ""
    return text[: position + 1], text[position + 1 :]


def split_run_spans(para: Para) -> tuple[tuple[Run, ...], tuple[Run, ...]]:
    """把 run 按首个冒号切到（前缀侧, 内容侧）；跨冒号的 run 两侧都算。"""
    position = colon_index("".join(run.text for run in para.runs))
    if position is None:
        return para.runs, ()
    prefix: list[Run] = []
    content: list[Run] = []
    offset = 0
    for run in para.runs:
        end = offset + len(run.text)
        if offset <= position:
            prefix.append(run)
        if end > position + 1:
            content.append(run)
        offset = end
    return tuple(prefix), tuple(content)


def _span_of(sel: BlockSel, side: int, pred: _RunPred | None) -> RunSel:
    def pick(blocks: Sequence[Block]) -> tuple[Run, ...]:
        out: list[Run] = []
        for block in sel(blocks):
            for run in split_run_spans(block.para)[side]:
                if pred is None or pred(run):
                    out.append(run)
        return tuple(out)

    return pick


def prefix_of(sel: BlockSel, pred: _RunPred | None = None) -> RunSel:
    """对象的前缀侧（冒号含）run。"""
    return _span_of(sel, 0, pred)


def content_of(sel: BlockSel, pred: _RunPred | None = None) -> RunSel:
    """对象的内容侧（冒号后）run。"""
    return _span_of(sel, 1, pred)


def contents(sel: BlockSel) -> TextSel:
    """对象内容（冒号之后的原始文本）。"""

    def pick(blocks: Sequence[Block]) -> tuple[str, ...]:
        return tuple(split_text(block.para.text)[1] for block in sel(blocks))

    return pick


# ── 文本谓词：关键词分隔符 / 末尾标点 / 个数 ─────────────────────


def separator_verdict(content: str) -> str:
    """关键词分隔符：只许中文分号，且不得有空关键词。"""
    if any(char in content for char in _OTHER_SEPARATORS):
        return "发现其他分隔符"
    if any(not part.strip() for part in content.split("；")):
        return "存在空关键词"
    return "合规"


def trailing_verdict(content: str) -> str:
    trimmed = content.rstrip()
    if not trimmed:
        return "内容为空"
    return "末尾有标点" if trimmed[-1] in _PUNCT else "无标点"


def count_keywords(content: str) -> tuple[str, ...]:
    return tuple(content.split("；"))


# ── 段落属性与结构 ───────────────────────────────────────────────


def para_text(block: Block) -> str:
    """标题 / 条目的纯文本：去掉首尾的换行与空白。

    标题段落常以 `<w:br w:type="page"/>` 分页开头，`para.text` 会带一个前导换行，
    那不该算进标题文字（"\\nABSTRACT" 仍是 "ABSTRACT"）。
    """
    return block.para.text.strip()


def prefix_text(block: Block) -> str:
    return split_text(block.para.text)[0]


def para_align(block: Block) -> str | None:
    return block.para.align


def para_line(block: Block) -> float | None:
    """行距倍率；**非倍率行距**（`exact` / `atLeast`）返回 `NOT_MULTIPLE` 直接判不合格。

    全库唯一的行距判定（`FR-3.5`）：读 `para.line_rule`，`auto` 才比 `line_multiple`。
    """
    if block.para.line_rule is not LineRule.AUTO:
        return NOT_MULTIPLE
    return block.para.line_multiple


def para_bold_verdict(block: Block) -> str:
    """非空白字符是否加粗（字体 / 加粗类只判非空白字符）；缺省不算加粗。"""
    return "加粗" if any(run.text.strip() and run.bold is True for run in block.para.runs) else "不加粗"


def first_cjk_font(block: Block) -> tuple[str | None, float | None] | None:
    """段落里第一个中文 run 的（中文字体, 字号）；无中文 run 则无法判定。"""
    run = next((item for item in block.para.runs if is_cjk_run(item)), None)
    if run is None:
        return None
    return (run.ea, run.size)


def run_font(run: Run) -> tuple[str | None, float | None]:
    """run 的（西文字体, 字号）；用于「Times New Roman，小四」这类合并的字体规则。"""
    return (run.west, run.size)


def para_first_line(block: Block) -> float | None:
    return block.para.first_line_chars


def empty_run_after(blocks: Sequence[Block], block: Block) -> int:
    """`block` 之后**紧接着**的空段落个数。

    分节符段落（承载 `w:sectPr` 的空段）是**结构标记**，不是空行——遇到它就停，
    否则「标题后正好 1 个空行」会被文末分节符误算成 2 个。
    """
    index = next(i for i, item in enumerate(blocks) if item is block)
    count = 0
    for item in blocks[index + 1 :]:
        if item.para.section_break or item.role is not Role.EMPTY:
            break
        count += 1
    return count


def blanks_after(sel: BlockSel) -> Callable[[Sequence[Block]], tuple[tuple[Block, int], ...]]:
    """（对象, 其后空段落数）对；`prop` 用 `count` 取数。"""

    def pick(blocks: Sequence[Block]) -> tuple[tuple[Block, int], ...]:
        return tuple((block, empty_run_after(blocks, block)) for block in sel(blocks))

    return pick


def last_of(sel: BlockSel) -> BlockSel:
    """选定段落中的**最后一段**（「正文最后一段之后」这类规则用）。"""

    def pick(blocks: Sequence[Block]) -> tuple[Block, ...]:
        found = sel(blocks)
        return (found[-1],) if found else ()

    return pick


def count(pair: tuple[Block, int]) -> int:
    return pair[1]


def found(sel: BlockSel) -> Callable[[Sequence[Block]], tuple[tuple[Block, ...], ...]]:
    """存在性规则用：**始终产出一个对象**（找到的是哪些段落），缺失时为空元组。"""

    def pick(blocks: Sequence[Block]) -> tuple[tuple[Block, ...], ...]:
        return (sel(blocks),)

    return pick


def present(blocks: tuple[Block, ...]) -> bool:
    return bool(blocks)


# ── 文本形状 / 编号后空格 ───────────────────────────────────────


def shape_verdict(pattern: re.Pattern[str]) -> Callable[[Block], str]:
    """整段可见文本必须匹配 `pattern`（`fullmatch`）；用于编号形态与空格的文本规则。"""

    def verdict(block: Block) -> str:
        return "合规" if pattern.fullmatch(block.para.text) else "编号或空格不符"

    return verdict


def gap_after(text: str, pattern: re.Pattern[str]) -> int | None:
    """编号之后、标题首字符之前的**半角空格数**；编号后没有标题则无法判定。"""
    match = pattern.match(text)
    if match is None:
        return None
    rest = text[match.end() :]
    tail = rest.lstrip(" ")
    if not tail:
        return None
    return len(rest) - len(tail)


def gap_of(pattern: re.Pattern[str]) -> Callable[[Block], int | None]:
    def gap(block: Block) -> int | None:
        return gap_after(block.para.text, pattern)

    return gap


# ── 块级相邻（题注位置等）───────────────────────────────────────


def index_of(blocks: Sequence[Block], block: Block) -> int:
    return next(i for i, item in enumerate(blocks) if item is block)


def neighbour_flag(sel: BlockSel, *, before: bool, pred: Callable[[Block], bool]) -> _PairSel:
    """（对象, 相邻块是否满足 `pred`）对；`before=True` 看前一个块，否则看后一个。"""

    def pick(blocks: Sequence[Block]) -> tuple[tuple[Block, bool], ...]:
        out: list[tuple[Block, bool]] = []
        for block in sel(blocks):
            index = index_of(blocks, block) + (-1 if before else 1)
            neighbour = blocks[index] if 0 <= index < len(blocks) else None
            out.append((block, neighbour is not None and pred(neighbour)))
        return tuple(out)

    return pick


def flag(pair: tuple[Block, bool]) -> bool:
    return pair[1]


# ── 整篇索引（跨作用域规则共用）────────────────────────────────


def context_index(ctx: CheckContext) -> DocumentIndex:
    """从只读上下文收集整篇索引。

    索引层的入口按"段落 + 块"暴露（规则手里没有 `Document`）；只喂**正文故事区**段落，
    与 `build_index(doc, ...)` 口径一致（文本框段落不在索引范围内）。
    """
    main = tuple(para for para in ctx.paragraphs if para.story is Story.MAIN)
    return index_from(main, ctx)
