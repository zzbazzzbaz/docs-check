"""规则号双向一致性（需求 `NFR-4.2`）。

`docs/规则/*.md` 的「规则一览」表是规则号的**权威来源**；代码里的规则号必须与它
**双向相等**（多了少了都失败）。本测试解析表格抽出文档侧集合，与 `REGISTRY` 比对。

Phase 7 只注册了一条示范规则，所以：

- **正向**（代码有、文档无 / 代码实现了"本期不做"）**始终是硬断言**；
- **反向**（文档有、代码无）在批 1/2 填完前 `pytest.skip`，只报差集。
  Phase 8 填完后把 `ALL_IN_SCOPE_RULES_REGISTERED` 改为 `True`，它立即变成硬断言。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from thesischeck.rules import REGISTRY

# Phase 8 把 197 条批 1 + 7 条批 2 填完后改成 True
ALL_IN_SCOPE_RULES_REGISTERED = False

# A.1：本期不做（5 条著录格式 + 1 条渲染通道），文档里有、代码里不应有
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
    assert len(ids) == 210, f"规则文档应定义 210 条，实际 {len(ids)} 条"
    assert ids & EXCLUDED == EXCLUDED


def test_registered_rules_are_documented_and_in_scope() -> None:
    registered = registered_ids()
    assert registered - documented_ids() == set(), f"代码有、文档无：{sorted(registered - documented_ids())}"
    assert registered & EXCLUDED == set(), f"代码实现了本期不做的规则：{sorted(registered & EXCLUDED)}"


def test_every_in_scope_rule_is_registered() -> None:
    missing = (documented_ids() - EXCLUDED) - registered_ids()
    if not ALL_IN_SCOPE_RULES_REGISTERED:
        pytest.skip(f"Phase 8 尚未填写批 1/2：缺 {len(missing)} 条，已注册 {len(registered_ids())} 条")
    assert missing == set(), f"文档有、代码无：{sorted(missing)}"
