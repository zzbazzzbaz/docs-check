"""分节、页眉页脚继承、页面设置、分页标记。

口径对 `test2/docxfmt/own_pages.py`（40 篇语料逐字段 100%）；样张在内存里拼最小 docx。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from thesischeck.parse import package as pkgmod
from thesischeck.parse.document import parse_document
from thesischeck.parse.model import Document

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

MIN_TYPES = b'<?xml version="1.0"?><Types/>'
HEADER_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
FOOTER_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"


def rels(*items: tuple[str, str, str]) -> str:
    rows = "".join(f'<Relationship Id="{i}" Type="{t}" Target="{target}"/>' for i, t, target in items)
    return f'<?xml version="1.0"?><Relationships xmlns="{REL_NS}">{rows}</Relationships>'


def load(tmp_path: Path, body: str, extra: dict[str, str] | None = None) -> Document:
    document = (
        f'<?xml version="1.0"?><w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>'
    )
    parts = {pkgmod.PART_DOCUMENT: document}
    parts.update(extra or {})
    path = tmp_path / "s.docx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(pkgmod.PART_CONTENT_TYPES, MIN_TYPES)
        for name, content in parts.items():
            archive.writestr(name, content)
    path.write_bytes(buf.getvalue())
    with pkgmod.Package.open(path) as opened:
        return parse_document(opened)


def header_part(text: str) -> str:
    return f'<?xml version="1.0"?><w:hdr xmlns:w="{W}"><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:hdr>'


# ── 分节与继承 ──────────────────────────────────────────────────


def test_section_without_reference_inherits_previous(tmp_path: Path) -> None:
    body = (
        '<w:p><w:pPr><w:sectPr><w:headerReference w:type="default" r:id="rId1"/>'
        '<w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:pPr><w:r><w:t>A</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>B</w:t></w:r></w:p>"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
    )
    document = load(
        tmp_path,
        body,
        {
            "word/_rels/document.xml.rels": rels(("rId1", HEADER_TYPE, "header1.xml")),
            "word/header1.xml": header_part("山东石油化工学院本科毕业设计（论文）"),
        },
    )
    assert len(document.sections) == 2
    first, second = document.sections
    assert first.index == 1 and second.index == 2
    assert len(first.headers) == 3  # default / first / even
    assert first.headers[0].owned is True
    assert first.headers[0].part == "word/header1.xml"
    assert first.headers[0].text == "山东石油化工学院本科毕业设计（论文）"
    assert second.headers[0].owned is False  # 继承
    assert second.headers[0].part == "word/header1.xml"
    assert second.headers[0].text == "山东石油化工学院本科毕业设计（论文）"
    assert second.footers[0].part is None
    assert [p.section for p in document.paragraphs] == [1, 2]


def test_page_setup_and_page_number_format(tmp_path: Path) -> None:
    body = (
        "<w:p><w:r><w:t>A</w:t></w:r></w:p>"
        '<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/>'
        '<w:pgMar w:top="1474" w:bottom="1474" w:left="1474" w:right="1474"'
        ' w:header="851" w:footer="992"/>'
        '<w:pgNumType w:fmt="upperRoman"/><w:titlePg/></w:sectPr>'
    )
    section = load(tmp_path, body).sections[0]
    assert (section.width_pt, section.height_pt, section.orientation) == (841.9, 595.3, "landscape")
    assert (section.top_pt, section.bottom_pt, section.left_pt, section.right_pt) == (
        73.7,
        73.7,
        73.7,
        73.7,
    )
    assert (section.header_pt, section.footer_pt) == (42.55, 49.6)
    assert section.page_number_format == "upperRoman"
    assert section.different_first_page is True
    assert section.type == "nextPage"


def test_even_and_odd_pages_come_from_settings(tmp_path: Path) -> None:
    body = "<w:p><w:r><w:t>A</w:t></w:r></w:p><w:sectPr/>"
    settings = f'<?xml version="1.0"?><w:settings xmlns:w="{W}"><w:evenAndOddHeaders/></w:settings>'
    assert load(tmp_path, body).sections[0].odd_and_even_pages is False
    assert load(tmp_path, body, {pkgmod.PART_SETTINGS: settings}).sections[0].odd_and_even_pages is True


def test_multiple_sections_and_own_references(tmp_path: Path) -> None:
    """第二节自己写页脚引用，就不再继承第一节的页脚；页眉仍继承。"""
    body = (
        '<w:p><w:pPr><w:sectPr><w:headerReference w:type="default" r:id="rIdH"/>'
        '<w:footerReference w:type="default" r:id="rIdF1"/></w:sectPr></w:pPr>'
        "<w:r><w:t>A</w:t></w:r></w:p>"
        '<w:p><w:pPr><w:sectPr><w:footerReference w:type="default" r:id="rIdF2"/>'
        "</w:sectPr></w:pPr><w:r><w:t>B</w:t></w:r></w:p>"
        "<w:sectPr/>"
    )
    document = load(
        tmp_path,
        body,
        {
            "word/_rels/document.xml.rels": rels(
                ("rIdH", HEADER_TYPE, "header1.xml"),
                ("rIdF1", FOOTER_TYPE, "footer1.xml"),
                ("rIdF2", FOOTER_TYPE, "footer2.xml"),
            ),
            "word/header1.xml": f'<?xml version="1.0"?><w:hdr xmlns:w="{W}"/>',
            "word/footer1.xml": f'<?xml version="1.0"?><w:ftr xmlns:w="{W}"/>',
            "word/footer2.xml": f'<?xml version="1.0"?><w:ftr xmlns:w="{W}"/>',
        },
    )
    assert [len(document.sections), document.sections[1].index] == [3, 2]
    assert document.sections[1].headers[0].part == "word/header1.xml"  # 继承
    assert document.sections[1].footers[0].owned is True  # 自有
    assert document.sections[1].footers[0].part == "word/footer2.xml"
    assert [p.section for p in document.paragraphs] == [1, 2]


# ── 分页标记三种写法 ────────────────────────────────────────────


def test_page_break_markers_in_all_three_forms(tmp_path: Path) -> None:
    body = (
        "<w:p><w:pPr><w:pageBreakBefore/></w:pPr><w:r><w:t>PBB</w:t></w:r></w:p>"
        '<w:p><w:r><w:br w:type="page"/><w:t>BR</w:t></w:r></w:p>'
        '<w:p><w:r><w:br w:type="textWrapping"/><w:t>WRAP</w:t></w:r></w:p>'
        "<w:p><w:pPr><w:sectPr/></w:pPr><w:r><w:t>SECT</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>AFTER</w:t></w:r></w:p>"
        "<w:sectPr/>"
    )
    document = load(tmp_path, body)
    pbb, br, wrap, sect, after = document.paragraphs
    assert (pbb.page_break_before, pbb.has_page_break) == (True, True)
    assert (br.page_break_before, br.has_page_break) == (False, True)
    assert wrap.has_page_break is False
    assert (sect.section_break, sect.has_page_break) == (True, False)
    assert [p.section for p in document.paragraphs] == [1, 1, 1, 1, 2]
    assert (after.section_break, after.has_page_break) == (False, False)
