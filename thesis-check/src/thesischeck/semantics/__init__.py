"""L2 语义定位：作用域分区 · 块角色 · 具名选择器 · 共享匹配器。

职责：
- 把文档流切成 8 个作用域（封面 / 中英文摘要 / 目录 / 正文 / 参考文献 / 致谢 / 附录）
- **全量**判定块角色；认不出的记为 `UNKNOWN`，进报告「未识别结构」，**不是通过**
- 提供具名选择器：**对象识别的唯一出处**（口径"只判中文字符""只判字母数字"
  "按字符定位到 run"都落在这里，只实现一次）
- 共享匹配器：保证互斥的两条规则用同一个判据（如 `REF-10` 与 `REF-21`）

**禁止**：取属性值、判对错。识别器是超集，收缩交给规则层。

本包是 L2 对外的**唯一门面**：别的层只准 `from thesischeck.semantics import X`。
`Role` / `Scope` 的唯一定义处是 `.roles` / `.scope`；`select` 是选择器工具箱，
按命名空间整体放行（`from thesischeck.semantics import select`）。
"""

from __future__ import annotations

from . import select
from .blocks import Block, CheckContext, tag_context
from .matchers import (
    chapter_no,
    citation_numbers,
    figure_no,
    formula_no,
    has_ascii_alnum,
    has_cjk,
    is_appendix_title,
    is_chapter,
    is_citation,
    is_toc_entry_style,
    key_text,
    looks_like_number,
    table_no,
    toc_style_level,
)
from .roles import Role, heading_level
from .scope import Scope

__all__ = [
    "Block",
    "CheckContext",
    "Role",
    "Scope",
    "chapter_no",
    "citation_numbers",
    "figure_no",
    "formula_no",
    "has_ascii_alnum",
    "has_cjk",
    "heading_level",
    "is_appendix_title",
    "is_chapter",
    "is_citation",
    "is_toc_entry_style",
    "key_text",
    "looks_like_number",
    "select",
    "table_no",
    "tag_context",
    "toc_style_level",
]
