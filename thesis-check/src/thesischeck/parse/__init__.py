"""L1 解析：**唯一碰 OOXML 的地方**。只产事实，不做判定。

职责：
- 包层：zip / rels / 部件 / 命名空间（含不可信输入的防护）
- 文档模型：块序列 · 段落 · run · 表格 · 文本框 · 分节 · 域 · 对象
- 有效格式：run → 字符样式 → 段落样式链 → 默认样式 → docDefaults → 主题字体

**禁止**：出现任何判定逻辑（形如 `if 字体 != "宋体"`）。
取不到值一律给 `None`——`None` 是"无法判定"，不是"不符合"。

本包是 L1 对外的**唯一门面**：别的层只准 `from thesischeck.parse import X`，
不许 import 其中的子模块（`.importlinter` 有契约强制）。这里只导出别的层实际要用的符号，
是**有意挑选的契约**而非子模块镜像——新增跨层符号时在这里补一行。
"""

from __future__ import annotations

from . import compat
from .document import para_text, parse_document, resolver_for
from .effective import DIRECT, Resolver, run_source
from .model import (
    Cell,
    Document,
    HeaderFooter,
    LineRule,
    Para,
    Run,
    Section,
    Story,
    Table,
)
from .package import (
    PART_COMMENTS,
    PART_CONTENT_TYPES,
    PART_DOCUMENT,
    Package,
    rels_part_name,
)

__all__ = [
    "DIRECT",
    "PART_COMMENTS",
    "PART_CONTENT_TYPES",
    "PART_DOCUMENT",
    "Cell",
    "Document",
    "HeaderFooter",
    "LineRule",
    "Package",
    "Para",
    "Resolver",
    "Run",
    "Section",
    "Story",
    "Table",
    "compat",
    "para_text",
    "parse_document",
    "rels_part_name",
    "resolver_for",
    "run_source",
]
