"""文档模型：块序列、段落编号、表格边框、文本框。

每条口径都对 `test2/docxfmt/own*.py` 的已验证实现：sdt 透传、表格行末标记、
可见文本的两处坑、`mc:Fallback` 去重、单元格边框的**位置映射**。
样张在内存里拼最小 docx，不读语料。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from thesischeck.parse import package as pkg
from thesischeck.parse.document import para_text, parse_document
from thesischeck.parse.model import Borders, Document, Para, Story, Table

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
V = "urn:schemas-microsoft-com:vml"

MIN_TYPES = b'<?xml version="1.0"?><Types/>'


def make_docx(body: str, *, styles: str | None = None, theme: str | None = None) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{W}" xmlns:m="{M}" xmlns:wp="{WP}" xmlns:mc="{MC}"'
        f' xmlns:r="{R}" xmlns:v="{V}"><w:body>{body}</w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(pkg.PART_CONTENT_TYPES, MIN_TYPES)
        archive.writestr(pkg.PART_DOCUMENT, document.encode())
        if styles is not None:
            archive.writestr(pkg.PART_STYLES, styles.encode())
        if theme is not None:
            archive.writestr(pkg.PART_THEME, theme.encode())
    return buf.getvalue()


def load(tmp_path: Path, body: str, *, styles: str | None = None) -> Document:
    path = tmp_path / "d.docx"
    path.write_bytes(make_docx(body, styles=styles))
    with pkg.Package.open(path) as opened:
        return parse_document(opened)


def para(text: str = "") -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" if text else "<w:p/>"


def table(cells: list[list[str]], tbl_pr: str = "") -> str:
    rows = "".join("<w:tr>" + "".join(f"<w:tc>{cell}</w:tc>" for cell in row) + "</w:tr>" for row in cells)
    return f"<w:tbl>{tbl_pr}{rows}</w:tbl>"


def flatten(document: Document) -> list[Para]:
    out: list[Para] = []
    for block in document.blocks:
        if isinstance(block, Table):
            out.extend(p for row in block.rows for cell in row for p in cell.paragraphs)
        else:
            out.append(block)
    return out


# ── 块序列与段落编号 ────────────────────────────────────────────


def test_blocks_interleave_paragraphs_and_tables(tmp_path: Path) -> None:
    body = para("A") + table([[para("T")]]) + para("B")
    document = load(tmp_path, body)
    assert [type(b).__name__ for b in document.blocks] == ["Para", "Table", "Para"]
    assert [p.text for p in document.paragraphs] == ["A", "T", "B"]
    assert [p.id for p in document.paragraphs] == [0, 1, 2]


def test_content_control_is_transparent_and_does_not_reset_numbering(tmp_path: Path) -> None:
    body = (
        para("A")
        + "<w:sdt><w:sdtContent>"
        + "<w:sdt><w:sdtContent>"
        + para("B")
        + "</w:sdtContent></w:sdt>"
        + "</w:sdtContent></w:sdt>"
        + para("C")
    )
    document = load(tmp_path, body)
    assert [p.text for p in document.paragraphs] == ["A", "B", "C"]
    assert [p.id for p in document.paragraphs] == [0, 1, 2]
    assert len(document.blocks) == 3


def test_table_inside_content_control_is_counted(tmp_path: Path) -> None:
    body = "<w:sdt><w:sdtContent>" + table([[para("T")]]) + "</w:sdtContent></w:sdt>"
    document = load(tmp_path, body)
    assert len(document.tables) == 1
    assert [type(b).__name__ for b in document.blocks] == ["Table"]


def test_blocks_cover_every_paragraph_exactly_once(tmp_path: Path) -> None:
    body = para("A") + table([[para("x"), para("y")], [para("z")]]) + para("B") + para("C")
    document = load(tmp_path, body)
    assert flatten(document) == list(document.paragraphs)


def test_table_row_end_marks_the_last_paragraph_of_each_row(tmp_path: Path) -> None:
    body = table([[para("a"), para("b")], [para("c")]])
    document = load(tmp_path, body)
    assert [p.text for p in document.paragraphs] == ["a", "b", "c"]
    assert all(p.in_table for p in document.paragraphs)
    assert [p.row_end for p in document.paragraphs] == [False, True, True]


def test_substituting_a_table_does_not_disturb_paragraph_numbering(tmp_path: Path) -> None:
    """表格自身不占段落号；换一个表格（同格数）后续段落编号不动。"""
    plain = '<w:tblPr><w:tblBorders><w:top w:val="single"/></w:tblBorders></w:tblPr>'
    body_a = para("A") + table([[para("T")]], plain) + para("B")
    body_b = para("A") + table([[para("T")]]) + para("B")
    ids = [[p.id for p in load(tmp_path, body).paragraphs] for body in (body_a, body_b)]
    assert ids == [[0, 1, 2], [0, 1, 2]]
    assert len(load(tmp_path, body_a).blocks) == 3


def test_table_without_cell_paragraphs_consumes_no_number(tmp_path: Path) -> None:
    body = para("A") + "<w:tbl><w:tr><w:tc><w:tcPr/></w:tc></w:tr></w:tbl>" + para("B")
    document = load(tmp_path, body)
    assert [p.id for p in document.paragraphs] == [0, 1]
    assert document.tables[0].rows[0][0].paragraphs == ()


# ── 可见文本 ────────────────────────────────────────────────────


def test_visible_text_keeps_math_and_drops_field_codes(tmp_path: Path) -> None:
    body = (
        "<w:p><w:r><w:t>A</w:t></w:r>"
        "<w:r><w:instrText> PAGE </w:instrText></w:r>"
        "<m:oMath><m:r><m:t>X</m:t></m:r></m:oMath></w:p>"
    )
    document = load(tmp_path, body)
    assert document.paragraphs[0].text == "AX"
    assert document.paragraphs[0].objects.omath == 1


def test_control_characters_are_not_visible_text(tmp_path: Path) -> None:
    """`w:t` 里混进来的换行不是可见文字；只有 `w:br` / `w:cr` 才算换行。"""
    document = load(tmp_path, "<w:p><w:r><w:t>A\nB</w:t><w:br/><w:t>C</w:t></w:r></w:p>")
    assert document.paragraphs[0].text == "AB\nC"


def test_tab_definition_is_not_a_tab_character(tmp_path: Path) -> None:
    body = (
        '<w:p><w:pPr><w:tabs><w:tab w:val="left" w:pos="420"/></w:tabs></w:pPr>'
        "<w:r><w:t>a</w:t></w:r><w:r><w:tab/><w:t>b</w:t></w:r></w:p>"
    )
    assert load(tmp_path, body).paragraphs[0].text == "a\tb"
    assert (
        load(tmp_path, '<w:p><w:pPr><w:tabs><w:tab w:pos="1"/></w:tabs></w:pPr></w:p>').paragraphs[0].text
        == ""
    )


def test_breaks_and_special_hyphens(tmp_path: Path) -> None:
    body = "<w:p><w:r><w:t>a</w:t><w:br/><w:cr/><w:noBreakHyphen/><w:softHyphen/></w:r></w:p>"
    assert load(tmp_path, body).paragraphs[0].text == "a\n\n\u2011\u00ad"


def test_textbox_content_is_not_visible_text(tmp_path: Path) -> None:
    body = (
        "<w:p><w:r><w:t>HOST</w:t></w:r><w:r><w:pict><v:shape><v:textbox>"
        "<w:txbxContent><w:p><w:r><w:t>BOX</w:t></w:r></w:p></w:txbxContent>"
        "</v:textbox></v:shape></w:pict></w:r></w:p>"
    )
    document = load(tmp_path, body)
    assert [p.text for p in document.paragraphs] == ["HOST"]
    assert para_text(document.paragraphs[0].xml) == "HOST"


# ── run 的有效格式 ──────────────────────────────────────────────


STYLES = f"""<?xml version="1.0"?>
<w:styles xmlns:w="{W}">
  <w:docDefaults><w:rPrDefault><w:rPr>
    <w:rFonts w:ascii="Arial"/><w:sz w:val="24"/>
  </w:rPr></w:rPrDefault></w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="正文"/>
    <w:pPr><w:jc w:val="center"/></w:pPr>
    <w:rPr><w:rFonts w:eastAsia="宋体"/><w:b/></w:rPr>
  </w:style>
  <w:style w:type="table" w:styleId="Base">
    <w:name w:val="Base"/>
    <w:tblPr><w:tblBorders><w:top w:val="single"/></w:tblBorders></w:tblPr>
  </w:style>
  <w:style w:type="table" w:styleId="Grid">
    <w:name w:val="Grid"/><w:basedOn w:val="Base"/>
    <w:tblPr><w:tblBorders><w:bottom w:val="single"/></w:tblBorders></w:tblPr>
  </w:style>
</w:styles>"""


def test_runs_carry_effective_format(tmp_path: Path) -> None:
    document = load(tmp_path, para("abc"), styles=STYLES)
    record = document.paragraphs[0]
    assert (record.style, record.style_id, record.align) == ("正文", "Normal", "center")
    run = record.runs[0]
    assert (run.ea, run.west, run.size, run.bold, run.italic) == ("宋体", "Arial", 12.0, True, None)
    assert run.index == 0


def test_textbox_runs_are_collected_on_their_own_story(tmp_path: Path) -> None:
    body = (
        "<w:p><w:r><w:t>HOST</w:t></w:r><w:r><w:pict><v:shape><v:textbox>"
        "<w:txbxContent><w:p><w:r><w:t>BOX</w:t></w:r></w:p></w:txbxContent>"
        "</v:textbox></v:shape></w:pict></w:r></w:p>"
    )
    document = load(tmp_path, body)
    assert document.boxes[0].host == document.paragraphs[0].id
    boxed = document.boxes[0].paragraphs
    assert [p.story for p in boxed] == [Story.TEXTBOX]
    assert [p.text for p in boxed] == ["BOX"]
    assert boxed[0].runs[0].text == "BOX"


def test_textbox_in_fallback_is_skipped(tmp_path: Path) -> None:
    body = (
        "<w:p><w:r><w:t>H</w:t></w:r><w:r><mc:AlternateContent>"
        '<mc:Choice Requires="wps"><w:drawing><wp:inline/></w:drawing></mc:Choice>'
        "<mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent>"
        + para("FALLBACK")
        + "</w:txbxContent></v:textbox></v:shape></w:pict></mc:Fallback>"
        "</mc:AlternateContent></w:r></w:p>"
    )
    document = load(tmp_path, body)
    assert document.boxes == ()
    assert document.paragraphs[0].objects.inline_images == 1


# ── 对象计数 ────────────────────────────────────────────────────


def test_inline_and_floating_drawings_are_counted_separately(tmp_path: Path) -> None:
    body = (
        "<w:p><w:r><w:drawing><wp:inline/></w:drawing></w:r>"
        "<w:r><w:drawing><wp:anchor/></w:drawing></w:r></w:p>"
    )
    objects = load(tmp_path, body).paragraphs[0].objects
    assert (objects.inline_images, objects.floating_images) == (1, 1)


def test_formula_counts_objects_and_omml_without_double_counting(tmp_path: Path) -> None:
    body = (
        "<w:p><w:r><w:object/></w:r>"
        "<m:oMathPara><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></m:oMathPara>"
        "<m:oMath><m:r><m:t>y</m:t></m:r></m:oMath></w:p>"
    )
    objects = load(tmp_path, body).paragraphs[0].objects
    assert (objects.ole, objects.omath) == (1, 2)


def test_display_equation_justification_defaults_to_center_group(tmp_path: Path) -> None:
    body = "<w:p><m:oMathPara><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></m:oMathPara></w:p>"
    assert load(tmp_path, body).paragraphs[0].objects.omath_para_align == "centerGroup"


def test_display_equation_justification_reads_jc(tmp_path: Path) -> None:
    body = (
        '<w:p><m:oMathPara><m:oMathParaPr><m:jc m:val="left"/></m:oMathParaPr>'
        "<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></m:oMathPara></w:p>"
    )
    assert load(tmp_path, body).paragraphs[0].objects.omath_para_align == "left"


def test_inline_math_has_no_display_justification(tmp_path: Path) -> None:
    body = "<w:p><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></w:p>"
    assert load(tmp_path, body).paragraphs[0].objects.omath_para_align is None


def test_fallback_objects_are_not_double_counted(tmp_path: Path) -> None:
    body = (
        '<w:p><w:r><mc:AlternateContent><mc:Choice Requires="wps">'
        "<w:drawing><wp:inline/></w:drawing></mc:Choice>"
        "<mc:Fallback><w:drawing><wp:anchor/></w:drawing></mc:Fallback>"
        "</mc:AlternateContent></w:r></w:p>"
    )
    objects = load(tmp_path, body).paragraphs[0].objects
    assert (objects.inline_images, objects.floating_images) == (1, 0)


# ── 表格边框 ────────────────────────────────────────────────────


def tc_borders(inner: str) -> str:
    return f"<w:tcPr><w:tcBorders>{inner}</w:tcBorders></w:tcPr>"


TBL_PR = (
    "<w:tblPr><w:tblBorders>"
    '<w:top w:val="single"/><w:bottom w:val="single"/>'
    '<w:left w:val="none"/><w:right w:val="none"/>'
    '<w:insideH w:val="none"/><w:insideV w:val="single"/>'
    "</w:tblBorders></w:tblPr>"
)


def test_cell_borders_follow_positional_mapping(tmp_path: Path) -> None:
    """上下按首末行取 top/bottom、内部取 insideH；左右按首末列取 left/right、内部取 insideV。"""
    body = table([[para("a"), para("b")], [para("c"), para("d")], [para("e"), para("f")]], TBL_PR)
    table_record = load(tmp_path, body).tables[0]
    assert (table_record.id, table_record.n_rows, table_record.n_cols) == (1, 3, 2)
    assert table_record.rows[0][0].borders == Borders(top=True, bottom=False, left=False, right=True)
    assert table_record.rows[0][1].borders == Borders(top=True, bottom=False, left=True, right=False)
    assert table_record.rows[1][0].borders == Borders(top=False, bottom=False, left=False, right=True)
    assert table_record.rows[2][0].borders == Borders(top=False, bottom=True, left=False, right=True)


def test_direct_cell_borders_win_and_nil_means_no_line(tmp_path: Path) -> None:
    override = tc_borders('<w:top w:val="nil"/><w:bottom w:val="single"/>')
    body = table([[para("a")], [f"<w:tc>{override}{para('b')}</w:tc>"]], TBL_PR)
    table_record = load(tmp_path, body).tables[0]
    assert table_record.rows[0][0].borders.top is True
    assert table_record.rows[1][0].borders.top is False
    assert table_record.rows[1][0].borders.bottom is True


def test_table_style_borders_follow_based_on_chain(tmp_path: Path) -> None:
    body = table([[para("a")], [para("b")]], '<w:tblPr><w:tblStyle w:val="Grid"/></w:tblPr>')
    document = load(tmp_path, body, styles=STYLES)
    cells = document.tables[0].rows
    assert cells[0][0].borders.top is True  # 来自 Base
    assert cells[1][0].borders.bottom is True  # 来自 Grid
    assert cells[1][0].borders.top is False  # Grid 没写 insideH


CONDITIONAL_STYLES = f"""<?xml version="1.0"?>
<w:styles xmlns:w="{W}">
  <w:style w:type="table" w:styleId="Cond">
    <w:name w:val="Cond"/>
    <w:tblPr><w:tblBorders><w:top w:val="single"/></w:tblBorders></w:tblPr>
    <w:tblStylePr w:type="firstRow">
      <w:tcPr><w:tcBorders><w:bottom w:val="single"/></w:tcBorders></w:tcPr>
    </w:tblStylePr>
  </w:style>
</w:styles>"""


def test_table_style_conditional_borders_are_recorded_as_a_fact(tmp_path: Path) -> None:
    """条件格式（`tblStylePr`）里的边框不合成，但作为事实记下，供三线表规则降级判定。"""
    body = table([[para("a")], [para("b")]], '<w:tblPr><w:tblStyle w:val="Cond"/></w:tblPr>')
    with_conditional = load(tmp_path, body, styles=CONDITIONAL_STYLES)
    assert with_conditional.tables[0].style_conditional_borders is True

    plain = load(tmp_path, body, styles=STYLES)
    assert plain.tables[0].style_conditional_borders is False


def test_table_direct_borders_override_style(tmp_path: Path) -> None:
    tbl_pr = '<w:tblPr><w:tblStyle w:val="Grid"/><w:tblBorders><w:top w:val="none"/></w:tblBorders></w:tblPr>'
    body = table([[para("a")]], tbl_pr)
    assert load(tmp_path, body, styles=STYLES).tables[0].rows[0][0].borders.top is False


def test_nested_table_is_not_counted_but_its_paragraphs_are(tmp_path: Path) -> None:
    inner = table([[para("N")]])
    body = table([[para("o") + inner]])
    document = load(tmp_path, body)
    assert len(document.tables) == 1
    assert [p.text for p in document.tables[0].rows[0][0].paragraphs] == ["o", "N"]
    assert [p.text for p in document.paragraphs] == ["o", "N"]


def test_table_in_textbox_is_not_a_top_level_table(tmp_path: Path) -> None:
    inner = table([[para("T")]])
    body = (
        "<w:p><w:r><w:pict><v:shape><v:textbox><w:txbxContent>"
        + inner
        + "</w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>"
    )
    document = load(tmp_path, body)
    assert document.tables == ()


# ── 未认识元素清单（FR-10.4）────────────────────────────────────


def test_unknown_elements_are_recorded_without_raising(tmp_path: Path) -> None:
    """宽容解析要记账：没专门处理的结构进清单，处理过的元素不误报。"""
    body = (
        '<w:p><w:bookmarkStart w:id="0"/><w:proofErr w:type="spellStart"/>'
        "<w:ins><w:r><w:t>X</w:t></w:r></w:ins><w:r><w:t>Y</w:t></w:r></w:p>"
    )
    document = load(tmp_path, body)
    assert document.paragraphs[0].text == "XY"  # 正文没有被丢
    assert {"bookmarkStart", "proofErr", "ins"} <= set(document.unknown_elements)
    assert not {"p", "r", "t", "body"} & set(document.unknown_elements)


def test_known_property_subtrees_are_not_reported(tmp_path: Path) -> None:
    """格式属性容器（`pPr` / `rPr` 里的细节）不算"未认识结构"，避免格式噪音当结构报警。"""
    body = (
        '<w:p><w:pPr><w:keepLines/><w:tabs><w:tab w:pos="1"/></w:tabs></w:pPr>'
        '<w:r><w:rPr><w:lang w:val="zh-CN"/><w:szCs w:val="24"/></w:rPr>'
        "<w:t>a</w:t></w:r></w:p>"
    )
    document = load(tmp_path, body)
    assert document.unknown_elements == ()
