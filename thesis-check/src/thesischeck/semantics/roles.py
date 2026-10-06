"""块角色的**全量**判定。

角色是全函数：每个段落都必须拿到一个角色；认不出的记 `Role.UNKNOWN`，进报告
「未识别结构」，**不是通过**（需求 `FR-4.3`）。粗粒度即可——「题目标签」「附录子标题」
这类更细的对象交给 `select` + `matchers` 组合，不塞进枚举。

**标题层级只用大纲级别 / 样式名判**（`FR-4.5`），不许用字号或加粗猜。`outline` 是
`w:outlineLvl` 的 0 起值，`9` 表示"正文级"，不算标题。
"""

from __future__ import annotations

from enum import StrEnum

from ..parse import Para
from .matchers import (
    heading_style_level,
    is_continued_table_caption,
    is_figure_caption,
    is_keyword_line,
    is_table_caption,
    is_toc_entry_style,
    key_text,
)
from .scope import Scope


class Role(StrEnum):
    TITLE = "title"  # 模块标题（摘要 / ABSTRACT / 目录 / 参考文献 / 致谢 / 附录）
    H1 = "h1"
    H2 = "h2"
    H3 = "h3"
    H4 = "h4-"  # 三级以下
    BODY = "body"
    CAPTION_FIG = "fig"
    CAPTION_TAB = "tab"
    FORMULA = "formula"
    REF_ITEM = "ref"
    KEYWORDS = "keywords"
    EMPTY = "empty"
    UNKNOWN = "unknown"


# 模块标题的关键文本，与 `scope` 的边界判据一致
_TITLES: dict[Scope, str] = {
    Scope.ABS_C: "摘要",
    Scope.ABS_E: "ABSTRACT",
    Scope.TOC: "目录",
    Scope.REFS: "参考文献",
    Scope.ACK: "致谢",
    Scope.APPENDIX: "附录",
}

_HEADING_ROLE: dict[int, Role] = {1: Role.H1, 2: Role.H2, 3: Role.H3, 4: Role.H4}

_OUTLINE_BODY = 9  # w:outlineLvl=9 表示正文级，不是标题


def is_module_title(para: Para, scope: Scope) -> bool:
    want = _TITLES.get(scope)
    if want is None:
        return False
    return key_text(para.text).upper() == want.upper()


def heading_level(para: Para) -> int | None:
    """标题层级（1 起）：优先大纲级别，其次 `heading N` 样式名；都没有则 `None`。"""
    if para.outline is not None and 0 <= para.outline < _OUTLINE_BODY:
        return int(para.outline) + 1
    return heading_style_level(para.style)


def assign_role(para: Para, scope: Scope) -> Role:
    if para.is_empty:
        return Role.EMPTY
    if is_module_title(para, scope):
        return Role.TITLE
    if is_toc_entry_style(para.style):
        # 目录条目不是标题层级，由 `select.toc_entries` 按样式取；这里给正文角色
        return Role.BODY
    level = heading_level(para)
    if level is not None:
        return _HEADING_ROLE[min(level, 4)]
    key = key_text(para.text)
    if is_figure_caption(key):
        return Role.CAPTION_FIG
    if is_table_caption(key) or is_continued_table_caption(key):
        return Role.CAPTION_TAB
    if para.objects.ole or para.objects.omath:
        return Role.FORMULA
    if scope is Scope.ABS_C and is_keyword_line(key, english=False):
        return Role.KEYWORDS
    if scope is Scope.ABS_E and is_keyword_line(key, english=True):
        return Role.KEYWORDS
    if scope is Scope.REFS:
        # 「条目 = 区内的**非空段落**」：只有图片 / 浮动的段落没有文字，不算条目，
        # 否则会被 REF-12 / REF-13 / REF-21 当空条目误报。
        return Role.REF_ITEM if key_text(para.text) else Role.EMPTY
    if scope is Scope.TOC:
        # 目录区里既不是标题、又不是 `toc N` 条目的非空段落：认不出
        return Role.UNKNOWN
    return Role.BODY
