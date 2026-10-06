"""L5 呈现：`issues.json` · 批注回写。

约定：
- **不重新判定、不修改结论**
- 问题严格分区：不通过 / 无法判定 / 该规则未执行 / 未识别结构；后三类**不许当通过**
- 批注回写**只插标记，不改正文**（需求 `FR-11.4.1`）：标注版与原文档正文必须逐字一致
- 定位分两层：机器层（段号）与人类层（作用域 › 章/节 + 文字摘要）

本包是 L5 对外的**唯一门面**：别的层只准 `from thesischeck.report import X`。
"""

from __future__ import annotations

from .annotate import Plan, PlannedComment, annotate, plan_comments, write_marked
from .issues import (
    RULESET_VERSION,
    Entry,
    Location,
    Report,
    build_report,
    ruleset_version,
)

__all__ = [
    "RULESET_VERSION",
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
