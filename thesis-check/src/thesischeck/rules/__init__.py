"""L4 规则：数据驱动判定 → 问题清单。

一条属性类规则的全部内容：

    Rule(id="TXT-25", of=BODY_PARA, prop=EA, expect="宋体", src="规范原文：小四号宋体")

**禁止**：
- `import lxml`、读 XML（`.importlinter` 里有契约检查）
- 硬编码段号 / 样本文件名 / 按文件名分支

结果三态：`FAIL` / `UNDETERMINED`（`PASS` 不进报告）。
有自动编号的段落要让开下游编号类规则——用选择器过滤实现，不做"抑制机制"。
"""

from .base import Comparison, Issue, Rule, ToleranceKey, Tolerances, Verdict, matches
from .batch1 import REGISTRY
from .engine import run_rules

__all__ = [
    "REGISTRY",
    "Comparison",
    "Issue",
    "Rule",
    "ToleranceKey",
    "Tolerances",
    "Verdict",
    "matches",
    "run_rules",
]
