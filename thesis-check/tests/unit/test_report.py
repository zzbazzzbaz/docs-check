"""报告层：`issues.json` 规范化、三态分区、定位、按需回溯。

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
from tests.fixtures.synth import auto_numbering, ea, line_exact

from thesischeck.index import build_index
from thesischeck.parse.document import parse_document, resolver_for
from thesischeck.parse.package import Package
from thesischeck.report import RULESET_VERSION, Report, build_report
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
            resolver = resolver_for(pkg)
            issues = run_rules(context, registry)
            index = build_index(document, context)
            return build_report(
                context,
                index,
                issues,
                parser_version="test",
                ruleset_version="test",
                resolver=resolver,
            )


def _dump(report: Report) -> str:
    return json.dumps(report.to_json(), ensure_ascii=False, indent=2)


# ── 快照稳定 ────────────────────────────────────────────────────


def test_json_is_identical_for_the_same_input() -> None:
    deviation = ea("中文摘要标题", "仿宋").apply(BASE)
    assert _dump(_report_for(BASE)) == _dump(_report_for(BASE))
    assert _dump(_report_for(deviation)) == _dump(_report_for(deviation))


def test_base_document_reports_nothing() -> None:
    report = _report_for(BASE)
    assert report.problem_count() == 0
    payload = report.to_json()
    assert payload["summary"] == {
        "fail": 0,
        "undetermined": 0,
        "not_run": 0,
        "unrecognised": 0,
        "by_scope": {},
        "auto_numbering_paragraphs": 0,
    }


def test_json_has_no_timestamp_or_absolute_path() -> None:
    payload = _dump(_report_for(BASE))
    for leak in ("/Users", "/Volumes", "20" + "26-", "timestamp", "elapsed", "duration"):
        assert leak not in payload


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
    assert [entry.rule for entry in report.undetermined] == ["TST-U1"]
    assert report.fail == ()
    assert report.undetermined[0].got == "无法确定"
    assert [entry["rule"] for entry in report.to_json()["fail"]] == []


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
            parser_version="test",
            ruleset_version="test",
        )
    assert report.problem_count() == 1
    assert len(report.unrecognised) == 1
    assert report.fail == ()
    assert report.undetermined == ()
    assert report.unrecognised[0].rule is None
    assert report.to_json()["fail"] == []


# ── 定位 ────────────────────────────────────────────────────────


def test_location_carries_scope_chapter_excerpt_and_run_span() -> None:
    report = _report_for(ea("正文段落", "仿宋").apply(BASE))
    hits = [entry for entry in report.fail if entry.rule == "TXT-25"]
    assert hits, "正文中文字体偏差没有被报出"
    entry = hits[0]
    assert entry.location.module == "正文"
    assert entry.location.chapter == "第一章  绪论"
    assert entry.location.section == "1.1.1 现状分析"
    assert entry.location.ordinal == 3
    assert entry.location.excerpt == "这是第1章的正文段落，用于承载正文属性的判定对象。"
    assert entry.location.span == entry.location.excerpt
    assert entry.location.block_id is not None
    assert entry.location.run_index == 0
    assert entry.location.element and entry.location.element.startswith("document/body")
    assert "第一章  绪论" in entry.location.text()


# ── 按需回溯 ────────────────────────────────────────────────────


def test_failure_records_provenance_from_the_run() -> None:
    report = _report_for(ea("中文摘要标题", "仿宋").apply(BASE))
    entry = next(entry for entry in report.fail if entry.rule == "ABS-C-02")
    assert entry.source == "在 run 上直接设置"


def test_html_is_student_facing_and_searchable() -> None:
    page = _report_for(ea("正文段落", "仿宋").apply(BASE)).to_html()
    assert "【TXT-25】" in page
    assert "第一章  绪论" in page
    assert "怎么找" in page
    assert "中文字体" in page
    for xml_term in ("eastAsia", "w:sz", "w:rPr", "pPr"):
        assert xml_term not in page


# ── 已知待办：行距哨兵与 GLB-28 汇总计数 ────────────────────────


def test_fixed_line_spacing_is_rendered_in_words() -> None:
    report = _report_for(line_exact("中文摘要正文", 20.0).apply(BASE))
    entries = [entry for entry in report.fail if entry.rule == "ABS-C-09"]
    assert entries
    assert all(entry.got == "固定行距 20pt" for entry in entries)
    assert "NaN" not in _dump(report)


def test_auto_numbering_is_counted_at_the_end() -> None:
    report = _report_for(auto_numbering("正文段落").apply(BASE))
    assert report.auto_numbering >= 1
    assert report.to_json()["summary"]["auto_numbering_paragraphs"] == report.auto_numbering
    assert f"共 {report.auto_numbering} 段使用了自动编号" in report.to_html()


def test_a_rule_that_raises_is_not_run_and_others_continue() -> None:
    """需求 §11 第 2 条 / `NFR-3.3`：单条规则抛异常只记"未执行"，其余规则照跑。"""

    def boom(ctx: CheckContext) -> tuple[Block, ...]:
        raise RuntimeError("boom")

    bad: Rule[Any, Any] = Rule(id="TST-E1", of=boom, prop=lambda block: None, expect="黑体", src="测试")
    good: Rule[Any, Any] = Rule(
        id="TST-U2", of=lambda ctx: (ctx[0],), prop=lambda block: None, expect="有值", src="测试"
    )
    report = _report_for(BASE, registry=(bad, good))
    assert [entry.rule for entry in report.not_run] == ["TST-E1"]
    assert report.not_run[0].error == "boom"
    assert [entry.rule for entry in report.undetermined] == ["TST-U2"]
    assert report.fail == ()


# ── 未覆盖项声明 ────────────────────────────────────────────────


def test_uncovered_items_are_declared() -> None:
    report = _report_for(BASE)
    assert len(report.uncovered) == 4
    page = report.to_html()
    for item in report.uncovered:
        assert item in page
    assert "目录页码" in page
    assert "续表" in page


# ── 解析器未认识元素（FR-10.4）──────────────────────────────────


def test_unknown_elements_are_counted_and_split_benign() -> None:
    report = Report(
        parser_version="test",
        ruleset_version="test",
        fail=(),
        undetermined=(),
        not_run=(),
        unrecognised=(),
        uncovered=(),
        auto_numbering=0,
        unknown_elements=("bookmarkStart", "customXml", "gridCol"),
    )
    assert report.unknown_benign() == ("bookmarkStart",)
    assert report.unknown_notable() == ("customXml", "gridCol")
    assert report.to_json()["unknown_elements"] == {"total": 3, "benign": 1, "notable": 2}
    assert "2 种值得关注" in report.to_html()


# ── 规则集版本（NFR-6）──────────────────────────────────────────


def test_ruleset_version_prefers_git_describe(monkeypatch: pytest.MonkeyPatch) -> None:
    """有 git 描述时用它，且结果缓存——一次进程只起一次 git（web 线程池不重复起进程）。"""
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
