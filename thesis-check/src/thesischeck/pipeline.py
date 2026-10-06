"""编排：把各层串起来（parse → semantics → index → rules → report）。

放在最上层是有意的：`cli` 只调这里，不自己拼流程。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .index import build_index
from .parse import Package, parse_document
from .report import Report, build_report, plan_comments, ruleset_version, write_marked
from .rules import REGISTRY, run_rules
from .semantics import tag_context


@dataclass(frozen=True, slots=True)
class ReviewResult:
    """一次审核的产物路径与报告对象。"""

    issues_json: Path
    marked_docx: Path
    report: Report


def review(docx: Path, outdir: Path) -> ReviewResult:
    """审核一篇文档，产出 `issues.json` 与标注版 docx（原文件一律不改动）。"""
    outdir.mkdir(parents=True, exist_ok=True)
    with Package.open(docx) as pkg:
        document = parse_document(pkg)
        context = tag_context(document)
        issues = run_rules(context, REGISTRY)
        index = build_index(document, context)
        plan = plan_comments(document, issues)
        report = build_report(context, index, issues, ruleset_version=ruleset_version())
        marked = write_marked(pkg, document, plan)

    issues_json = outdir / "issues.json"
    marked_docx = outdir / f"{docx.stem}.marked.docx"
    issues_json.write_text(
        json.dumps(report.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    marked_docx.write_bytes(marked)
    return ReviewResult(issues_json=issues_json, marked_docx=marked_docx, report=report)
