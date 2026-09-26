"""L3 整篇索引：`modules` / `chapters` / `floats` / `citations` / `toc_entries`。

纪律（规则文档 `9-整体`「跨作用域规则」）：

- **只收集事实，不做判定**
- **宽松收集，规则负责收缩**——否则"编号写错 → 索引为空 → 连续性规则反而不报"就成了恒真式
- **取不到就显式「无法判定」**，不静默通过

索引自身有 `checks.check_index` 不变量自检（块覆盖完整、区间连续不重叠、边界文本对得上…）。
"""

from __future__ import annotations

from .checks import IndexViolation, Severity, check_index
from .document_index import (
    MODULE_ORDER,
    Chapter,
    Citation,
    DocumentIndex,
    FloatRef,
    Floats,
    ModuleSpan,
    TocEntry,
    build_index,
    detected_modules,
    matches_module,
    module_spans,
)

__all__ = [
    "MODULE_ORDER",
    "Chapter",
    "Citation",
    "DocumentIndex",
    "FloatRef",
    "Floats",
    "IndexViolation",
    "ModuleSpan",
    "Severity",
    "TocEntry",
    "build_index",
    "check_index",
    "detected_modules",
    "matches_module",
    "module_spans",
]
