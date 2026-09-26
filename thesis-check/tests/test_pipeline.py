"""端到端：`pipeline.review` 串起 parse → semantics → index → rules → report。

底稿必须零问题；偏差变体必须出现对应条目，且带期望值 / 实际值 / 依据。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.fixtures.base import BASE
from tests.fixtures.synth import ea
from thesischeck import cli
from thesischeck.pipeline import review


def _run(tmp_path: Path, data: bytes) -> tuple[Path, Path, dict[str, Any]]:
    docx = tmp_path / "case.docx"
    docx.write_bytes(data)
    result = review(docx, tmp_path / "out")
    payload = json.loads(result.issues_json.read_text(encoding="utf-8"))
    return result.issues_json, result.report_html, payload


def test_review_writes_both_products_for_compliant_base(tmp_path: Path) -> None:
    issues_json, report_html, payload = _run(tmp_path, BASE)
    assert issues_json.is_file()
    assert report_html.is_file()
    assert payload["summary"] == {
        "fail": 0,
        "undetermined": 0,
        "not_run": 0,
        "unrecognised": 0,
        "by_scope": {},
        "auto_numbering_paragraphs": 0,
    }
    assert payload["uncovered"]


def test_review_reports_deviation_with_values_and_basis(tmp_path: Path) -> None:
    _, _, payload = _run(tmp_path, ea("中文摘要标题", "仿宋").apply(BASE))
    hits = [entry for entry in payload["fail"] if entry["rule"] == "ABS-C-02"]
    assert hits, "中文摘要标题字体偏差没有被报出"
    entry = hits[0]
    assert entry["got"] == "仿宋"
    assert entry["expect"] == "黑体"
    assert entry["basis"]
    assert entry["location"]["module"] == "中文摘要"
    assert entry["provenance"] == "在 run 上直接设置"


def test_cli_runs_review_and_writes_products(tmp_path: Path) -> None:
    docx = tmp_path / "case.docx"
    docx.write_bytes(BASE)
    outdir = tmp_path / "cli-out"
    assert cli.main([str(docx), "-o", str(outdir)]) == 0
    assert (outdir / "issues.json").is_file()
    assert (outdir / "report.html").is_file()
