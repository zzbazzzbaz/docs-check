"""域采集：真实域的代码、跨度、嵌套，以及填进 `Para.field_codes` 的起始域代码。

口径对 `test2/docxfmt/own.py` 的 `OwnDoc.fields`（40 篇语料逐段 100%）；
样张在内存里拼最小 docx，不读语料。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from lxml import etree

from thesischeck.parse import package as pkgmod
from thesischeck.parse.document import iter_paragraphs, parse_document
from thesischeck.parse.fields import parse_fields
from thesischeck.parse.model import Document

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
V = "urn:schemas-microsoft-com:vml"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

MIN_TYPES = b'<?xml version="1.0"?><Types/>'


def paragraphs(body: str) -> list[etree._Element]:
    root = etree.fromstring(f'<w:body xmlns:w="{W}" xmlns:mc="{MC}" xmlns:v="{V}">{body}</w:body>'.encode())
    return [el for el, _, _ in iter_paragraphs(root)]


def load(tmp_path: Path, body: str) -> Document:
    document = (
        f'<?xml version="1.0"?><w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>'
    )
    path = tmp_path / "f.docx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(pkgmod.PART_CONTENT_TYPES, MIN_TYPES)
        archive.writestr(pkgmod.PART_DOCUMENT, document.encode())
    path.write_bytes(buf.getvalue())
    with pkgmod.Package.open(path) as opened:
        return parse_document(opened)


# ── 代码与跨度 ──────────────────────────────────────────────────


def test_char_field_records_code_and_span() -> None:
    body = (
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> PAGE \\* MERGEFORMAT </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>1</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    )
    (field,) = parse_fields(paragraphs(body))
    assert (field.code, field.start, field.end, field.end_content) == ("PAGE", 0, 0, 0)


def test_simple_field_is_a_single_paragraph() -> None:
    body = '<w:p><w:r><w:fldSimple w:instr=" PAGE "><w:t>1</w:t></w:fldSimple></w:r></w:p>'
    (field,) = parse_fields(paragraphs(body))
    assert (field.code, field.start, field.end, field.end_content) == ("PAGE", 0, 0, 0)


def test_toc_span_uses_the_last_paragraph_with_content() -> None:
    """TOC 的结束标记落在只有标记的空段上，内容其实结束在上一段。"""
    body = (
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText> TOC \\o "1-3" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>目录</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>第一章 引言\t1</w:t></w:r></w:p>"
        '<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    )
    fields = parse_fields(paragraphs(body))
    assert [(f.code, f.start, f.end, f.end_content) for f in fields] == [("TOC", 0, 2, 1)]


def test_nested_fields_are_all_collected() -> None:
    body = (
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> TOC </w:instrText></w:r><w:r><w:t>目录</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>一</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> PAGEREF _Toc1 \\h </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        '<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    )
    codes = {f.code: (f.start, f.end, f.end_content) for f in parse_fields(paragraphs(body))}
    assert codes == {"TOC": (0, 2, 1), "PAGEREF": (1, 1, 1)}


def test_textbox_and_fallback_fields_are_skipped() -> None:
    body = (
        "<w:p><w:r><w:pict><v:shape><v:textbox><w:txbxContent>"
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText>PAGE</w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        "</w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>"
        '<w:p><w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing/></mc:Choice>'
        "<mc:Fallback><w:fldChar/></mc:Fallback></mc:AlternateContent></w:r></w:p>"
    )
    assert parse_fields(paragraphs(body)) == ()


# ── 填进 Para 的起始域代码 ──────────────────────────────────────


def test_starting_codes_are_filled_into_the_paragraph(tmp_path: Path) -> None:
    body = (
        "<w:p><w:r><w:t>X</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> PAGE </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    )
    document = load(tmp_path, body)
    record = document.paragraphs[0]
    assert record.text == "X"  # 域代码不是可见文本
    assert record.field_codes == ("PAGE",)
    assert [(f.code, f.start, f.end_content) for f in document.fields] == [("PAGE", 0, 0)]


def test_only_the_beginning_paragraph_carries_the_code(tmp_path: Path) -> None:
    body = (
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText>TOC</w:instrText></w:r></w:p>"
        "<w:p><w:r><w:t>条目</w:t></w:r></w:p>"
        '<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    )
    document = load(tmp_path, body)
    assert [p.field_codes for p in document.paragraphs] == [("TOC",), (), ()]
