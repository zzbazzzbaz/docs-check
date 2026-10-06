"""端到端：`pipeline.review` 串起 parse → semantics → index → rules → report。

底稿必须零问题；偏差变体必须出现对应条目，且带定位 / 实际值 / 期望值 / 规则文案。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.fixtures.base import BASE
from tests.fixtures.synth import ea
from thesischeck import cli
from thesischeck.parse.document import parse_document
from thesischeck.parse.package import PART_COMMENTS, Package
from thesischeck.pipeline import review


def _run(tmp_path: Path, data: bytes) -> tuple[Path, dict[str, Any]]:
    docx = tmp_path / "case.docx"
    docx.write_bytes(data)
    result = review(docx, tmp_path / "out")
    payload = json.loads(result.issues_json.read_text(encoding="utf-8"))
    return result.issues_json, payload


def test_review_writes_products_for_compliant_base(tmp_path: Path) -> None:
    issues_json, payload = _run(tmp_path, BASE)
    assert issues_json.is_file()
    assert set(payload) == {"summary", "rules", "problems"}
    assert payload["summary"]["fail"] == 0
    assert payload["summary"]["undetermined"] == 0
    assert payload["problems"] == []
    assert payload["rules"] == {}


def test_review_reports_deviation_with_values_and_basis(tmp_path: Path) -> None:
    _, payload = _run(tmp_path, ea("中文摘要标题", "仿宋").apply(BASE))
    hits = [entry for entry in payload["problems"] if entry["rule"] == "ABS-C-02"]
    assert hits, "中文摘要标题字体偏差没有被报出"
    entry = hits[0]
    assert entry["severity"] == "fail"
    assert entry["got"] == "仿宋"
    assert entry["expect"] == "黑体"
    assert entry["where"]["module"] == "中文摘要"
    assert payload["rules"]["ABS-C-02"]["text"], "规则文案应随 rules 表给出"


def test_cli_runs_review_and_writes_products(tmp_path: Path) -> None:
    docx = tmp_path / "case.docx"
    docx.write_bytes(BASE)
    outdir = tmp_path / "cli-out"
    assert cli.main([str(docx), "-o", str(outdir)]) == 0
    assert (outdir / "issues.json").is_file()
    assert (outdir / "case.marked.docx").is_file()


def test_review_writes_marked_document_with_comments(tmp_path: Path) -> None:
    """第二件产物：标注版 docx（批注回写），且不破坏正文。"""
    docx = tmp_path / "case.docx"
    docx.write_bytes(ea("中文摘要标题", "仿宋").apply(BASE))
    result = review(docx, tmp_path / "out")

    assert result.marked_docx.name == "case.marked.docx"
    with Package.open(result.marked_docx) as pkg:
        document = parse_document(pkg)
        comments = pkg.read(PART_COMMENTS)
    assert comments is not None
    assert b"ABS-C-02" in comments
    assert any(para.text.startswith("摘") for para in document.paragraphs)
