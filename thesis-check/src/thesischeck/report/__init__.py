"""L5 呈现：`issues.json` · `report.html` · 批注回写。

约定：
- **不重新判定、不修改结论**
- 报告严格分区：不通过 / 无法判定 / 未识别结构；后两类**不许当通过**
- 报告要带「本轮未覆盖项」声明
- 批注回写**只插标记，不改正文**（需求 `FR-11.4.1`）：标注版与原文档正文必须逐字一致
- 定位分两层：机器层（块号 + run 序号 + XML 元素引用）与人类层（作用域 › 章/节 + 文字摘要 + 字符片段）

本包是 L5 对外的**唯一门面**：别的层只准 `from thesischeck.report import X`。
"""

from __future__ import annotations

from .annotate import Plan, PlannedComment, annotate, plan_comments, write_marked
from .issues import (
    BENIGN_ELEMENTS,
    RULESET_VERSION,
    SCHEMA_VERSION,
    UNCOVERED,
    Downgrade,
    Entry,
    Location,
    Report,
    build_report,
    ruleset_version,
)

__all__ = [
    "BENIGN_ELEMENTS",
    "RULESET_VERSION",
    "SCHEMA_VERSION",
    "UNCOVERED",
    "Downgrade",
    "Entry",
    "Location",
    "Plan",
    "PlannedComment",
    "Report",
    "annotate",
    "build_report",
    "plan_comments",
    "ruleset_version",
    "write_marked",
]
