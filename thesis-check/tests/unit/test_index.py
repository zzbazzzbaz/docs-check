"""L3 索引层：跨作用域事实的收集与不变量自检。

两条纪律用测试钉死：

- **宽松收集**：章候选不要求大纲级别（`第3章` / 无级别的 `第X章` 都要收进来），
  否则"级别写错 → 索引为空 → 连续性规则静默通过"就成了恒真式。
- **取不到就显式无法判定**：定位不到正文区时 `citations is None`，不是空集合。

不变量既在底稿上全过，也被证明"报得出来"（人为破坏索引后能报出对应违规）。
真实语料沿用与解析层相同的定位：`THESIS_CORPUS_DIR` 或 `test2/corpus`，都没有则跳过。
"""

from __future__ import annotations

import io
import os
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from tests.fixtures.base import BASE
from tests.fixtures.synth import insert_line_after, rename_style

from thesischeck.index import (
    MODULE_ORDER,
    ModuleSpan,
    Severity,
    build_index,
    check_index,
    detected_modules,
    module_spans,
)
from thesischeck.parse import package as pkg
from thesischeck.parse.document import parse_document
from thesischeck.parse.model import Document
from thesischeck.semantics.blocks import Block, tag_blocks

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

STYLES = f"""<?xml version="1.0"?>
<w:styles xmlns:w="{W}">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="正文"/></w:style>
  <w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/></w:style>
</w:styles>"""


def para(text: str = "", *, style: str | None = None) -> str:
    prefix = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    run = f"<w:r><w:t>{text}</w:t></w:r>" if text else ""
    return f"<w:p>{prefix}{run}</w:p>"


def superscript(text: str) -> str:
    return f'<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:t>{text}</w:t></w:r>'


def _parse(path: Path) -> tuple[Document, tuple[Block, ...]]:
    with pkg.Package.open(path) as opened:
        document = parse_document(opened)
    return document, tag_blocks(document)


def _load(tmp_path: Path, body: str) -> tuple[Document, tuple[Block, ...]]:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(pkg.PART_CONTENT_TYPES, b'<?xml version="1.0"?><Types/>')
        zf.writestr(pkg.PART_DOCUMENT, document_xml.encode())
        zf.writestr(pkg.PART_STYLES, STYLES.encode())
    path = tmp_path / "d.docx"
    path.write_bytes(archive.getvalue())
    return _parse(path)


def _from_bytes(tmp_path: Path, data: bytes) -> tuple[Document, tuple[Block, ...]]:
    path = tmp_path / "case.docx"
    path.write_bytes(data)
    return _parse(path)


# ── 底稿：每个字段都有对象，不变量全过 ──────────────────────────


def test_base_document_index_collects_every_field(tmp_path: Path) -> None:
    document, blocks = _from_bytes(tmp_path, BASE)
    index = build_index(document, blocks)

    assert [span.name for span in index.modules] == list(MODULE_ORDER)
    assert all(span.title_found for span in index.modules)
    assert [chapter.no for chapter in index.chapters] == [1, 2, 3, 4, 5]
    assert all(chapter.is_heading1 for chapter in index.chapters)
    assert [ref.no for ref in index.floats.figures] == ["1-1"]
    assert [ref.no for ref in index.floats.tables] == ["1-1"]
    assert [ref.no for ref in index.floats.formulas] == ["1-1"]
    assert index.floats.formula_objects == 1
    assert index.citations is not None
    assert {citation.no for citation in index.citations} == {1, 2}
    assert [citation.order for citation in index.citations] == [1, 2]
    assert [entry.level for entry in index.toc_entries] == [1, 2, 3, 1, 1, 1]
    assert check_index(document, index) == ()


# ── 宽松收集 ────────────────────────────────────────────────────


def test_chapters_are_collected_without_outline_or_style(tmp_path: Path) -> None:
    body = (
        para("本科生毕业设计（论文）")
        + para("摘    要")
        + para("中文摘要正文。")
        + para("第一章 引言")
        + para("第一章是引言，本段没有任何大纲级别。")
        + para("第3章 系统设计")
        + para("参考文献")
        + para("[1] 作者. 题名[M].")
    )
    document, blocks = _load(tmp_path, body)
    index = build_index(document, blocks)

    assert [chapter.no for chapter in index.chapters] == [1, 1, 3]
    assert [chapter.is_heading1 for chapter in index.chapters] == [False, False, False]
    assert check_index(document, index) == ()


def test_module_spans_recognise_arabic_chapters(tmp_path: Path) -> None:
    body = para("封面行") + para("摘    要") + para("第一章 引言") + para("第2章 系统")
    _document, blocks = _load(tmp_path, body)
    spans = module_spans(blocks)

    assert [span.name for span in spans] == ["封面", "中文摘要", "正文"]
    # 封面关键文本缺失：区间仍保留（覆盖全篇），但不算"识别到"
    assert detected_modules(spans) == ("中文摘要", "正文")


# ── 无法判定 ────────────────────────────────────────────────────


def test_citations_are_undetermined_without_a_body_scope(tmp_path: Path) -> None:
    body = para("本科生毕业设计（论文）") + para("摘    要") + para("中文摘要正文。")
    document, blocks = _load(tmp_path, body)
    index = build_index(document, blocks)

    assert index.citations is None
    violations = check_index(document, index)
    assert [violation.check for violation in violations] == ["引用唯一且顺序一致"]
    assert violations[0].severity is Severity.WARN


def test_citation_numbers_follow_first_appearance(tmp_path: Path) -> None:
    body = (
        para("本科生毕业设计（论文）")
        + para("摘    要")
        + para("中文摘要正文。")
        + para("第一章 引言")
        + f"<w:p>{superscript('[3]')}</w:p>"
        + f"<w:p>{superscript('[1,2]')}</w:p>"
    )
    document, blocks = _load(tmp_path, body)
    index = build_index(document, blocks)

    assert index.citations is not None
    assert [(citation.no, citation.order) for citation in index.citations] == [(3, 1), (1, 2), (2, 3)]
    assert check_index(document, index) == ()


# ── 不变量：报得出来 ────────────────────────────────────────────


def test_module_range_invariant_detects_a_gap(tmp_path: Path) -> None:
    document, blocks = _from_bytes(tmp_path, BASE)
    index = build_index(document, blocks)
    broken = replace(index, modules=index.modules[:-1])

    checks = {violation.check for violation in check_index(document, broken)}
    assert "模块区间连续" in checks


def test_module_boundary_invariant_detects_a_mismatch(tmp_path: Path) -> None:
    document, blocks = _from_bytes(tmp_path, BASE)
    index = build_index(document, blocks)
    mislabelled = ModuleSpan(name="中文摘要", start=0, end=index.modules[0].end, title_found=True)
    broken = replace(index, modules=(mislabelled, *index.modules[1:]))

    checks = {violation.check for violation in check_index(document, broken)}
    assert "模块边界文本对得上" in checks


def test_duplicate_figure_numbers_are_a_warning(tmp_path: Path) -> None:
    data = insert_line_after("正文段落", "图1-1 重复的图题").apply(BASE)
    document, blocks = _from_bytes(tmp_path, data)
    index = build_index(document, blocks)
    violations = check_index(document, index)

    assert any(
        violation.check == "图/表编号重复" and violation.severity is Severity.WARN for violation in violations
    )
    assert all(violation.severity is Severity.WARN for violation in violations)


def test_toc_level_outside_one_to_three_is_reported(tmp_path: Path) -> None:
    data = rename_style("toc 3", "toc 4").apply(BASE)
    document, blocks = _from_bytes(tmp_path, data)
    index = build_index(document, blocks)

    assert 4 in [entry.level for entry in index.toc_entries]
    assert any(
        violation.check == "目录条目层级合法" and violation.severity is Severity.FAIL
        for violation in check_index(document, index)
    )


# ── 真实语料：40 篇的不变量与统计 ───────────────────────────────


def _corpus_docs() -> list[Path]:
    env = os.environ.get("THESIS_CORPUS_DIR")
    if env and Path(env).is_dir():
        return sorted(Path(env).glob("*.docx"))
    repo = Path(__file__).resolve().parents[2]
    fallback = repo.parent / "test2" / "corpus"
    return sorted(fallback.glob("*.docx")) if fallback.is_dir() else []


@pytest.mark.real_corpus
@pytest.mark.slow
@pytest.mark.skipif(not _corpus_docs(), reason="需要真实语料（THESIS_CORPUS_DIR 或 test2/corpus）")
def test_real_corpus_index_invariants() -> None:
    docs = _corpus_docs()
    warnings = 0
    print(f"\nreal corpus index: {len(docs)} docs")
    print(f"  {'document':<34}{'mod':>4}{'ch':>4}{'fig':>5}{'tab':>5}{'formula':>8}{'cite':>6}{'toc':>5}")
    for docx in docs:
        with pkg.Package.open(docx) as opened:
            document = parse_document(opened)
        blocks = tag_blocks(document)
        index = build_index(document, blocks)
        violations = check_index(document, index)
        fails = [violation for violation in violations if violation.severity is Severity.FAIL]
        warns = [violation for violation in violations if violation.severity is Severity.WARN]
        warnings += len(warns)
        assert not fails, f"{docx.name}: {[(v.check, v.detail) for v in fails]}"
        citations = "?" if index.citations is None else str(len(index.citations))
        print(
            f"  {docx.stem[:32]:<34}{len(index.modules):>4}{len(index.chapters):>4}"
            f"{len(index.floats.figures):>5}{len(index.floats.tables):>5}"
            f"{len(index.floats.formulas):>8}{citations:>6}{len(index.toc_entries):>5}"
        )
    print(f"  全部通过（提示 {warnings} 条）")
