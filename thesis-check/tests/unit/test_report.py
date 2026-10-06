"""报告层：`issues.json`（`summary` / `rules` / `problems`）规范化、三态分区、定位、规则表去重。

报告只呈现不判定，所以这里既锁"输出稳定可快照"，也锁"没通过的不许混进通过"。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.base import BASE
from tests.fixtures.synth import ea, line_exact

from thesischeck.index import build_index
from thesischeck.parse.document import parse_document
from thesischeck.parse.package import Package
from thesischeck.report import RULESET_VERSION, Entry, Report, build_report
from thesischeck.report import issues as report_issues
from thesischeck.rules import REGISTRY, Rule, run_rules
from thesischeck.semantics.blocks import Block, CheckContext, Role, tag_context


def _report_for(data: bytes, registry: Sequence[Rule[Any, Any]] = REGISTRY) -> Report:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "case.docx"
        path.write_bytes(data)
        with Package.open(path) as pkg:
            document = parse_document(pkg)
            context = tag_context(document)
            issues = run_rules(context, registry)
            index = build_index(document, context)
            return build_report(context, index, issues, ruleset_version="test")


def _dump(report: Report) -> str:
    return json.dumps(report.to_json(), ensure_ascii=False, indent=2)


def _of(report: Report, severity: str) -> list[Entry]:
    return [entry for entry in report.problems if entry.severity == severity]


# ── 快照稳定 ────────────────────────────────────────────────────


def test_json_is_identical_for_the_same_input() -> None:
    deviation = ea("中文摘要标题", "仿宋").apply(BASE)
    assert _dump(_report_for(BASE)) == _dump(_report_for(BASE))
    assert _dump(_report_for(deviation)) == _dump(_report_for(deviation))


def test_base_document_reports_nothing() -> None:
    report = _report_for(BASE)
    assert report.problems == ()
    payload = report.to_json()
    assert payload["summary"] == {
        "ruleset_version": "test",
        "fail": 0,
        "undetermined": 0,
        "not_run": 0,
        "unrecognised": 0,
        "by_scope": {},
    }
    assert payload["rules"] == {}
    assert payload["problems"] == []


def test_json_has_no_timestamp_or_absolute_path() -> None:
    payload = _dump(_report_for(BASE))
    for leak in ("/Users", "/Volumes", "20" + "26-", "timestamp", "elapsed", "duration"):
        assert leak not in payload


def test_problem_shape_is_locked() -> None:
    """`problems` 每条只带 定位 + 实际值 / 期望值 + 状态，不再重复规则文案。"""
    report = _report_for(ea("正文段落", "仿宋").apply(BASE))
    entry = next(entry for entry in report.problems if entry.rule == "TXT-25")
    payload = entry.to_dict()
    assert set(payload) == {"rule", "severity", "where", "got", "expect", "error"}
    assert set(payload["where"]) == {"block_id", "module", "chapter", "section", "ordinal", "excerpt"}


# ── 三态分区：后两类与未识别都不许当通过 ────────────────────────


def test_undetermined_stays_out_of_fail() -> None:
    rule: Rule[Any, Any] = Rule(
        id="TST-U1",
        of=lambda ctx: (ctx[0],),
        prop=lambda block: None,
        expect="应有值",
        src="测试：取不到值",
    )
    report = _report_for(BASE, registry=(rule,))
    assert [entry.rule for entry in _of(report, "undetermined")] == ["TST-U1"]
    assert _of(report, "fail") == []
    assert _of(report, "undetermined")[0].got == "无法确定"


def test_unrecognised_structure_is_its_own_section() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "case.docx"
        path.write_bytes(BASE)
        with Package.open(path) as pkg:
            document = parse_document(pkg)
            context = tag_context(document)
        blocks = tuple(context)
        modified = (Block(blocks[0].para, blocks[0].scope, Role.UNKNOWN), *blocks[1:])
        broken = CheckContext(
            modified,
            sections=context.sections,
            paragraphs=context.paragraphs,
            tables=context.tables,
            has_numbering_part=context.has_numbering_part,
        )
        report = build_report(
            broken,
            build_index(document, modified),
            [],
            ruleset_version="test",
        )
    assert len(report.problems) == 1
    assert report.problems[0].severity == "unrecognised"
    assert report.problems[0].rule is None
    assert _of(report, "fail") == []


# ── 定位 ────────────────────────────────────────────────────────


def test_location_carries_scope_chapter_section_and_excerpt() -> None:
    report = _report_for(ea("正文段落", "仿宋").apply(BASE))
    hits = [entry for entry in report.problems if entry.rule == "TXT-25"]
    assert hits, "正文中文字体偏差没有被报出"
    location = hits[0].location
    assert location.module == "正文"
    assert location.chapter == "第一章  绪论"
    assert location.section == "1.1.1 现状分析"
    assert location.ordinal == 3
    assert location.excerpt == "这是第1章的正文段落，用于承载正文属性的判定对象。"
    assert location.block_id is not None


# ── 规则表：静态文案只写一次 ────────────────────────────────────


def test_rules_table_lists_each_rule_once() -> None:
    report = _report_for(ea("正文段落", "仿宋").apply(BASE))
    rules = report.to_json()["rules"]
    referenced = {entry.rule for entry in report.problems if entry.rule is not None}
    assert set(rules) == referenced
    assert rules["TXT-25"]["text"], "规则文案不应为空"


# ── 已知待办：行距哨兵 ──────────────────────────────────────────


def test_fixed_line_spacing_is_rendered_in_words() -> None:
    report = _report_for(line_exact("中文摘要正文", 20.0).apply(BASE))
    entries = [entry for entry in report.problems if entry.rule == "ABS-C-09"]
    assert entries
    assert all(entry.got == "固定行距 20pt" for entry in entries)
    assert "NaN" not in _dump(report)


def test_a_rule_that_raises_is_not_run_and_others_continue() -> None:
    """需求 §11 第 2 条 / `NFR-3.3`：单条规则抛异常只记"未执行"，其余规则照跑。"""

    def boom(ctx: CheckContext) -> tuple[Block, ...]:
        raise RuntimeError("boom")

    bad: Rule[Any, Any] = Rule(id="TST-E1", of=boom, prop=lambda block: None, expect="黑体", src="测试")
    good: Rule[Any, Any] = Rule(
        id="TST-U2", of=lambda ctx: (ctx[0],), prop=lambda block: None, expect="有值", src="测试"
    )
    report = _report_for(BASE, registry=(bad, good))
    not_run = _of(report, "not_run")
    assert [entry.rule for entry in not_run] == ["TST-E1"]
    assert not_run[0].error == "boom"
    assert [entry.rule for entry in _of(report, "undetermined")] == ["TST-U2"]
    assert _of(report, "fail") == []


# ── 规则集版本（NFR-6）──────────────────────────────────────────


def test_ruleset_version_prefers_git_describe(monkeypatch: pytest.MonkeyPatch) -> None:
    """有 git 描述时用它，且结果缓存——一次进程只起一次 git。"""
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> Any:
        calls.append(cmd)
        return type("Result", (), {"stdout": "v1.2.3-4-gabc-dirty\n"})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    report_issues.ruleset_version.cache_clear()
    try:
        assert report_issues.ruleset_version() == "v1.2.3-4-gabc-dirty"
        assert report_issues.ruleset_version() == "v1.2.3-4-gabc-dirty"
    finally:
        report_issues.ruleset_version.cache_clear()
    assert len(calls) == 1


def test_ruleset_version_falls_back_without_git(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: object, **__: object) -> Any:
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", boom)
    report_issues.ruleset_version.cache_clear()
    try:
        assert report_issues.ruleset_version() == RULESET_VERSION
    finally:
        report_issues.ruleset_version.cache_clear()
