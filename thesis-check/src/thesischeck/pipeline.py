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
    """一次审核的落盘产物路径与报告对象。"""

    issues_json: Path
    marked_docx: Path
    report: Report


@dataclass(frozen=True, slots=True)
class ReviewPayload:
    """一次审核的内存产物：报告 + 标注版 docx 字节（Web 上传直接消费，不落盘）。"""

    report: Report
    marked_docx: bytes


def _review(pkg: Package) -> ReviewPayload:
    """已打开的包 → 报告 + 标注版字节；落盘与否由调用方决定。"""
    document = parse_document(pkg)
    context = tag_context(document)
    issues = run_rules(context, REGISTRY)
    index = build_index(document, context)
    plan = plan_comments(document, issues)
    report = build_report(context, index, issues, ruleset_version=ruleset_version())
    marked = write_marked(pkg, document, plan)
    return ReviewPayload(report=report, marked_docx=marked)


def review_bytes(data: bytes) -> ReviewPayload:
    """审核内存中的 .docx 字节（Web 上传场景），产物全部在内存。"""
    with Package.open_bytes(data) as pkg:
        return _review(pkg)


def review(docx: Path, outdir: Path) -> ReviewResult:
    """审核一篇文档，产出 `issues.json` 与标注版 docx（原文件一律不改动）。"""
    outdir.mkdir(parents=True, exist_ok=True)
    with Package.open(docx) as pkg:
        payload = _review(pkg)

    issues_json = outdir / "issues.json"
    marked_docx = outdir / f"{docx.stem}.marked.docx"
    issues_json.write_text(
        json.dumps(payload.report.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    marked_docx.write_bytes(payload.marked_docx)
    return ReviewResult(issues_json=issues_json, marked_docx=marked_docx, report=payload.report)
