"""L4 规则引擎：跑注册表，产出 `list[Issue]`。

三条纪律：

- 取不到属性值（`None`）-> `UNDETERMINED`，**不是通过**。
- 单条规则抛异常 -> 记 `RuleError`、该规则标为"未执行"（以 `UNDETERMINED` 承载），
  **不中断整篇**，其余规则照跑（需求 §11 第 2 条）。
- 引擎本身不做判定逻辑；判定全部在 `base.matches` 与规则数据里。

引擎就这么长，不做成框架。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..errors import RuleError
from ..semantics.blocks import CheckContext
from .base import DEFAULT_TOLERANCES, Issue, Rule, Tolerances, Verdict, matches


def run_rules(
    context: CheckContext,
    registry: Sequence[Rule[Any, Any]],
    *,
    tolerances: Tolerances = DEFAULT_TOLERANCES,
) -> list[Issue]:
    """跑完注册表，按注册顺序返回全部问题（`PASS` 不出现）。"""
    issues: list[Issue] = []
    for rule in registry:
        try:
            for obj in rule.of(context):
                got = rule.prop(obj)
                if got is None:
                    issues.append(Issue(rule.id, Verdict.UNDETERMINED, obj, expect=rule.expect, src=rule.src))
                elif not matches(rule, got, tolerances):
                    issues.append(Issue(rule.id, Verdict.FAIL, obj, got, rule.expect, rule.src))
        except Exception as exc:
            issues.append(Issue(rule.id, Verdict.UNDETERMINED, error=RuleError(rule.id, str(exc))))
    return issues
