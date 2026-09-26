"""规则编号 → 规则内容数组：批注与报告取"这条规则要求什么"的单一事实来源。

`rules.catalog.RULE_TEXTS` 必须与 `REGISTRY` 一一对应：不重、不漏、内容一致。
"""

from __future__ import annotations

from thesischeck.rules import REGISTRY
from thesischeck.rules.catalog import RULE_TEXTS, content, text


def test_catalog_covers_every_rule_exactly_once() -> None:
    ids = [rule_id for rule_id, _ in RULE_TEXTS]
    assert len(ids) == len(set(ids))
    assert set(ids) == {rule.id for rule in REGISTRY}


def test_catalog_content_matches_the_registry() -> None:
    for rule in REGISTRY:
        assert text(rule.id) == rule.src


def test_content_strips_the_source_prefix() -> None:
    assert content("ABS-C-01") == "摘要标题「摘    要」，中间 4 个半角空格"
    assert content("ABS-C-05") == "中文摘要标题后 1 个空段落"
    assert content("COV-11") == "信息行三号（16pt）"


def test_content_is_never_empty_for_a_registered_rule() -> None:
    assert all(content(rule.id).strip() for rule in REGISTRY)


def test_unknown_rule_degrades_to_empty() -> None:
    assert content("TST-UNKNOWN") == ""
