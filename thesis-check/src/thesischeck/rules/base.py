"""L4 规则原语：规则是**数据**，判定是**三态**。

一条属性类规则的全部内容就是一行数据：

    Rule(id="ABS-C-02", of=abstract_c_title_cjk_runs, prop=attrgetter("ea"),
         expect="黑体", src="规范原文：中文摘要标题三号黑体")

设计要点：

- **属性提取器是函数**（`operator.attrgetter` 或具名函数），不是字符串 + `getattr`；
  对象类型由 `Rule[Obj, Val]` 泛型锁住。
- **容差是配置**：`Tolerances` 的数值不在规则里出现，`APPROX` 只引用一个容差键，
  引擎把配置传进来（需求 `NFR-5.5` / §3.3）。
- **取不到值是 `None`**，含义是"无法判定"，**不是**通过。
- 比较器只要 5 个：等值 / 近似 / 正则 / 集合包含 / 计数范围。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..errors import RuleError
from ..semantics.blocks import CheckContext


class Verdict(StrEnum):
    """结果三态；`PASS` 不进报告。"""

    PASS = "pass"
    FAIL = "fail"
    UNDETERMINED = "undetermined"


class Comparison(StrEnum):
    EQ = "eq"
    APPROX = "approx"
    PATTERN = "pattern"
    IN_SET = "in_set"
    COUNT_RANGE = "count_range"


class ToleranceKey(StrEnum):
    """容差键：规则只写键，数值由引擎从 `Tolerances` 取。"""

    PAPER_PT = "paper_pt"
    MARGIN_PT = "margin_pt"
    SIZE_PT = "size_pt"
    LINE = "line"
    INDENT_CHARS = "indent_chars"


@dataclass(frozen=True, slots=True)
class Tolerances:
    """§3.3 的默认容差（样张校准前的建议值）；测试可整体覆写。"""

    paper_pt: float = 2.83  # 1 mm
    margin_pt: float = 1.42  # 0.5 mm
    size_pt: float = 0.5
    line: float = 0.05
    indent_chars: float = 0.05


DEFAULT_TOLERANCES = Tolerances()

_TOLERANCE_VALUE: dict[ToleranceKey, Callable[[Tolerances], float]] = {
    ToleranceKey.PAPER_PT: lambda t: t.paper_pt,
    ToleranceKey.MARGIN_PT: lambda t: t.margin_pt,
    ToleranceKey.SIZE_PT: lambda t: t.size_pt,
    ToleranceKey.LINE: lambda t: t.line,
    ToleranceKey.INDENT_CHARS: lambda t: t.indent_chars,
}


@dataclass(frozen=True, slots=True)
class Rule[Obj, Val]:
    """一条规则的数据。`of` 选对象，`prop` 取属性，`expect` 是期望值。"""

    id: str
    of: Callable[[CheckContext], tuple[Obj, ...]]
    prop: Callable[[Obj], Val | None]
    expect: Val
    src: str
    cmp: Comparison = Comparison.EQ
    tol: ToleranceKey | None = None


@dataclass(frozen=True, slots=True)
class Issue:
    """一条问题。`error` 非空表示该规则**未执行**（需求 §11 第 2 条），不是通过。"""

    rule: str
    verdict: Verdict
    where: object | None = None
    got: object | None = None
    expect: object | None = None
    src: str = ""
    error: RuleError | None = None


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"近似比较需要数值，实际是 {type(value).__name__}")
    return float(value)


def _as_range(value: object) -> tuple[int, int]:
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and all(isinstance(bound, int) and not isinstance(bound, bool) for bound in value)
    ):
        low, high = value
        return int(low), int(high)
    raise TypeError(f"计数范围比较需要 (下界, 上界)，实际是 {value!r}")


def matches(rule: Rule[Any, Any], got: Any, tolerances: Tolerances) -> bool:
    """按 `rule.cmp` 判定 `got` 是否符合 `rule.expect`；类型不对就抛错，由引擎记 `RuleError`。"""
    if rule.cmp is Comparison.EQ:
        return bool(got == rule.expect)
    if rule.cmp is Comparison.APPROX:
        if rule.tol is None:
            raise ValueError(f"{rule.id}: APPROX 比较必须指定容差键")
        tolerance = _TOLERANCE_VALUE[rule.tol](tolerances)
        # 纸张尺寸是二维的：允许对同长的数值序列逐分量比较（GLB-15）
        if isinstance(got, (tuple, list)) and isinstance(rule.expect, (tuple, list)):
            if len(got) != len(rule.expect):
                return False
            return all(
                abs(_as_float(a) - _as_float(b)) <= tolerance for a, b in zip(got, rule.expect, strict=True)
            )
        return abs(_as_float(got) - _as_float(rule.expect)) <= tolerance
    if rule.cmp is Comparison.PATTERN:
        if not isinstance(rule.expect, re.Pattern):
            raise TypeError(f"{rule.id}: PATTERN 比较的期望值必须是正则")
        return isinstance(got, str) and rule.expect.fullmatch(got) is not None
    if rule.cmp is Comparison.IN_SET:
        if not isinstance(rule.expect, Collection):
            raise TypeError(f"{rule.id}: IN_SET 比较的期望值必须是集合")
        return got in rule.expect
    low, high = _as_range(rule.expect)
    return low <= len(tuple(iter(got))) <= high
