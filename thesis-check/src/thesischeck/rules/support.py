"""规则层共用小工具：run 选择、冒号切分、空段计数与关键词内容判定。

只组合 `semantics` 的选择器与匹配器，**不新增对象判据**（`NFR-4.3`）。作用域规则
（封面 / 摘要）都从这里取对象定位与文本切分；判定值本身仍是各规则里的数据。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..parse.model import Para, Run
from ..semantics.blocks import Block, Role
from ..semantics.matchers import has_ascii_alnum, has_cjk

BlockSel = Callable[[Sequence[Block]], tuple[Block, ...]]
RunSel = Callable[[Sequence[Block]], tuple[Run, ...]]
TextSel = Callable[[Sequence[Block]], tuple[str, ...]]
_RunPred = Callable[[Run], bool]

_COLONS = "：:"
_OTHER_SEPARATORS = ",;，、"
_PUNCT = frozenset("。；，、,;.：:！？!?…．")


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
    return block.para.text


def prefix_text(block: Block) -> str:
    return split_text(block.para.text)[0]


def para_align(block: Block) -> str | None:
    return block.para.align


def para_line(block: Block) -> float | None:
    return block.para.line_multiple


def para_first_line(block: Block) -> float | None:
    return block.para.first_line_chars


def empty_run_after(blocks: Sequence[Block], block: Block) -> int:
    """`block` 之后**紧接着**的空段落个数。"""
    index = next(i for i, item in enumerate(blocks) if item is block)
    count = 0
    for item in blocks[index + 1 :]:
        if item.role is not Role.EMPTY:
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
