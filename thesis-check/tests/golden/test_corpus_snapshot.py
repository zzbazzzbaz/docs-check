"""Phase 14 回归快照：40 篇真实语料的全流程问题数（按规则聚合）。

`corpus_snapshot.json` 是**语料金标准**（需求 `NFR-5.2` / 技术设计 §9.4）：改动解析或规则后，
这份 diff **必须人工过一遍**才算回归保护。快照只存计数与语料摘要，**不含任何正文文本、
文件名、绝对路径或时间戳**；按规则号排序落盘，diff 才干净。

两类断言：

- 同一次语料跑两次，结果必须**逐字节一致**（`NFR-6.1` 可复现）；
- 结果必须与提交在仓库里的快照**完全一致**（防"改一处坏一处"）。

语料在仓库外（`../test2/corpus`），不在本地时整组跳过（`real_corpus` + `slow`）。
重建快照：`uv run python tests/golden/test_corpus_snapshot.py --write`。
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from thesischeck import __version__
from thesischeck.index import build_index
from thesischeck.parse.document import parse_document
from thesischeck.parse.package import Package
from thesischeck.report import RULESET_VERSION, build_report
from thesischeck.rules import REGISTRY, run_rules
from thesischeck.semantics.blocks import tag_context

_REPO = Path(__file__).resolve().parents[2]
CORPUS = _REPO.parent / "test2" / "corpus"
SNAPSHOT = Path(__file__).with_name("corpus_snapshot.json")
SCHEMA = 1


def _docs() -> list[Path]:
    return sorted(CORPUS.glob("*.docx")) if CORPUS.is_dir() else []


def _run_one(path: Path) -> dict[str, Any]:
    """一篇的全流程计数：解析 -> 规则 -> 索引 -> 报告。只取计数，不取文本。"""
    with Package.open(path) as pkg:
        document = parse_document(pkg)
        context = tag_context(document)
        issues = run_rules(context, REGISTRY)
        index = build_index(document, context)
        report = build_report(context, index, issues, ruleset_version=RULESET_VERSION)
    by_rule: dict[str, dict[str, int]] = {}
    for issue in issues:
        bucket = by_rule.setdefault(issue.rule, {"fail": 0, "undetermined": 0, "not_run": 0})
        if issue.error is not None:
            bucket["not_run"] += 1
        else:
            bucket["fail" if issue.verdict.value == "fail" else "undetermined"] += 1
    return {**report.counts(), "by_rule": by_rule}


def build_snapshot() -> dict[str, Any]:
    """把整份语料聚合成一份可 diff 的快照。"""
    documents: list[dict[str, Any]] = []
    by_rule: dict[str, dict[str, int]] = {}
    totals: Counter[str] = Counter()
    for index, path in enumerate(_docs(), 1):
        result = _run_one(path)
        for key in ("fail", "undetermined", "not_run", "unrecognised"):
            totals[key] += result[key]
        for rule, counts in result["by_rule"].items():
            bucket = by_rule.setdefault(rule, {"fail": 0, "undetermined": 0, "not_run": 0})
            bucket["fail"] += counts["fail"]
            bucket["undetermined"] += counts["undetermined"]
            bucket["not_run"] += counts["not_run"]
        documents.append(
            {
                "index": index,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                "fail": result["fail"],
                "undetermined": result["undetermined"],
                "not_run": result["not_run"],
                "unrecognised": result["unrecognised"],
            }
        )
    totals["problems"] = totals["fail"] + totals["undetermined"] + totals["not_run"] + totals["unrecognised"]
    return {
        "schema": SCHEMA,
        "parser_version": __version__,
        "ruleset_version": RULESET_VERSION,
        "documents": len(documents),
        "totals": dict(totals),
        "by_rule": {rule: by_rule[rule] for rule in sorted(by_rule)},
        "per_document": documents,
    }


def _dump(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _available() -> bool:
    return bool(_docs())


@pytest.mark.skipif(not _available(), reason="需要 test2/corpus")
def test_corpus_snapshot_matches_committed() -> None:
    """实跑结果必须与仓库里的快照完全一致；不一致就是回归，必须人工过一遍。"""
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = build_snapshot()
    if actual == expected:
        return

    lines = ["语料快照与提交的快照不一致："]
    for key in ("documents", "totals", "parser_version", "ruleset_version", "schema"):
        if actual.get(key) != expected.get(key):
            lines.append(f"  {key}: {expected.get(key)!r} -> {actual.get(key)!r}")
    exp_rule, act_rule = expected.get("by_rule", {}), actual.get("by_rule", {})
    for rule in sorted(set(exp_rule) | set(act_rule)):
        if exp_rule.get(rule) != act_rule.get(rule):
            lines.append(f"  {rule}: {exp_rule.get(rule)} -> {act_rule.get(rule)}")
    for exp_doc, act_doc in zip(expected.get("per_document", []), actual["per_document"], strict=False):
        if exp_doc != act_doc:
            lines.append(f"  第 {act_doc['index']} 篇: {exp_doc} -> {act_doc}")
    pytest.fail("\n".join(lines[:60]))


@pytest.mark.skipif(not _available(), reason="需要 test2/corpus")
def test_corpus_run_is_reproducible() -> None:
    """同一输入跑两次，结论必须逐字节一致（`NFR-6.1`）。"""
    first = _dump(build_snapshot())
    second = _dump(build_snapshot())
    assert first == second, "同一语料两次运行结果不同，可复现性被破坏"


def _write() -> None:
    SNAPSHOT.write_text(_dump(build_snapshot()), encoding="utf-8")
    print(f"已写入 {SNAPSHOT}")


if __name__ == "__main__":
    if "--write" in sys.argv:
        _write()
    else:
        raise SystemExit("用法：uv run python tests/golden/test_corpus_snapshot.py --write")
