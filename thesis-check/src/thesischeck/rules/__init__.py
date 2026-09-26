"""L4 规则：数据驱动判定 → 问题清单。

一条属性类规则的全部内容：

    Rule(id="TXT-25", of=BODY_PARA, prop=EA, expect="宋体", src="规范原文：小四号宋体")

**禁止**：
- `import lxml`、读 XML（`.importlinter` 里有契约检查）
- 硬编码段号 / 样本文件名 / 按文件名分支

结果三态：`FAIL` / `UNDETERMINED`（`PASS` 不进报告）。
有自动编号的段落要让开下游编号类规则——用选择器过滤实现，不做"抑制机制"。
"""

from __future__ import annotations

from typing import Any

from .abstract_c import REGISTRY as _ABSTRACT_C
from .abstract_e import REGISTRY as _ABSTRACT_E
from .acknowledgements import REGISTRY as _ACK
from .appendix import REGISTRY as _APPENDIX
from .base import (
    AttrGetter,
    Comparison,
    Issue,
    Rule,
    ToleranceKey,
    Tolerances,
    Verdict,
    attrgetter,
    matches,
    trace_prop,
)
from .cover import REGISTRY as _COVER
from .document_wide import REGISTRY as _GLOBAL
from .engine import run_rules
from .references import REGISTRY as _REFERENCES
from .text import REGISTRY as _TEXT
from .toc import REGISTRY as _TOC

REGISTRY: tuple[Rule[Any, Any], ...] = (
    *_COVER,
    *_ABSTRACT_C,
    *_ABSTRACT_E,
    *_TOC,
    *_TEXT,
    *_REFERENCES,
    *_ACK,
    *_APPENDIX,
    *_GLOBAL,
)

__all__ = [
    "REGISTRY",
    "AttrGetter",
    "Comparison",
    "Issue",
    "Rule",
    "ToleranceKey",
    "Tolerances",
    "Verdict",
    "attrgetter",
    "matches",
    "run_rules",
    "trace_prop",
]
