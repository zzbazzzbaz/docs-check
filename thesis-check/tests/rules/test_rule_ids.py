"""规则号双向一致性（需求 `NFR-4.2`）。

`docs/规则/*.md` 的「规则一览」表是规则号的**权威来源**；代码里的规则号必须与它
**双向相等**（多了少了都失败）。本测试解析表格抽出文档侧集合，与 `REGISTRY` 比对。

一处例外，显式登记而不是静默跳过：`EXCLUDED` 是本期**不做**的 6 条（1 条渲染通道 +
5 条著录格式骨架）。批 2 的 7 条已在第 10 阶段注册，不再排除。

`ALL_IN_SCOPE_RULES_REGISTERED = True`（第 8 阶段收尾）后，反向断言是**硬断言**：
`文档 − EXCLUDED == 代码注册`，差集必须为空。
"""

from __future__ import annotations

import re
from pathlib import Path

from thesischeck.rules import REGISTRY

ALL_IN_SCOPE_RULES_REGISTERED = True

# 本期不做（1 条渲染通道 + 5 条著录格式骨架），文档里有、代码里不应有
EXCLUDED = frozenset({"TXT-50", "REF-16", "REF-17", "REF-18", "REF-19", "REF-20"})

_DOCS = Path(__file__).resolve().parents[3] / "docs" / "规则"
_ID = re.compile(r"^\|\s*((?:ABS-C|ABS-E|COV|TOC|TXT|REF|ACK|APP|GLB)-\d{2})\s*\|", re.MULTILINE)


def documented_ids() -> set[str]:
    found: set[str] = set()
    for path in sorted(_DOCS.glob("*.md")):
        found.update(_ID.findall(path.read_text(encoding="utf-8")))
    return found


def registered_ids() -> set[str]:
    return {rule.id for rule in REGISTRY}


def test_documents_define_the_expected_rule_set() -> None:
    ids = documented_ids()
    assert len(ids) == 213, f"规则文档应定义 213 条，实际 {len(ids)} 条"
    assert ids & EXCLUDED == EXCLUDED


def test_registered_rules_are_documented_and_in_scope() -> None:
    registered = registered_ids()
    assert registered - documented_ids() == set(), f"代码有、文档无：{sorted(registered - documented_ids())}"
    assert registered & EXCLUDED == set(), f"代码实现了本期不做的规则：{sorted(registered & EXCLUDED)}"


def test_every_in_scope_rule_is_registered() -> None:
    assert ALL_IN_SCOPE_RULES_REGISTERED, "第 8 阶段收尾必须把双向断言翻成硬断言"
    missing = (documented_ids() - EXCLUDED) - registered_ids()
    assert missing == set(), f"文档有、代码无：{sorted(missing)}"
