"""编排：把各层串起来（parse → semantics → index → rules → report）。

放在最上层是有意的：`cli` 与 `web` 都只调这里，不各自拼流程，
这样两条入口的结论一定一致。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .index import build_index
from .parse.document import parse_document, resolver_for
from .parse.package import Package
from .report import Report, build_report, ruleset_version
from .report.annotate import plan_comments, write_marked
from .rules import REGISTRY, run_rules
from .semantics.blocks import tag_context


@dataclass(frozen=True, slots=True)
class ReviewResult:
    """一次审核的产物路径与报告对象。"""

    issues_json: Path
    report_html: Path
    marked_docx: Path
    report: Report


def review(docx: Path, outdir: Path) -> ReviewResult:
    """审核一篇文档，产出 `issues.json`、`report.html` 与标注版 docx（原文件一律不改动）。"""
    outdir.mkdir(parents=True, exist_ok=True)
    with Package.open(docx) as pkg:
        document = parse_document(pkg)
        resolver = resolver_for(pkg)
        context = tag_context(document)
        issues = run_rules(context, REGISTRY)
        index = build_index(document, context)
        plan = plan_comments(document, issues)
        report = build_report(
            context,
            index,
            issues,
            parser_version=__version__,
            ruleset_version=ruleset_version(),
            resolver=resolver,
            annotation=plan.downgrades,
            unknown_elements=document.unknown_elements,
        )
        marked = write_marked(pkg, document, plan)

    issues_json = outdir / "issues.json"
    report_html = outdir / "report.html"
    marked_docx = outdir / f"{docx.stem}.marked.docx"
    issues_json.write_text(
        json.dumps(report.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_html.write_text(report.to_html(), encoding="utf-8")
    marked_docx.write_bytes(marked)
    return ReviewResult(
        issues_json=issues_json, report_html=report_html, marked_docx=marked_docx, report=report
    )
