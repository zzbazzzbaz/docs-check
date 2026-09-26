"""兼容 dump：把解析结果渲染成 `test2` 快照的形状，**只调试 / 等价性关卡用**。

四套与 `test2/docxfmt/own*.py` 一一对应：`own`（段落与字符）、`ownpages`（分节 / 页眉页脚 /
页面设置）、`ownborders`（表格边框）、`owntextbox`（文本框），外加 `ownindex`（整篇索引，
对应 `test2/docxfmt/index.py`）。字段名、单位、`None` 的用法
逐一对齐，方便直接和 `test2/snapshots/*.json.gz` 比对。

产品模型与对账口径有意不同，这里按需从节点保留的 lxml 引用回溯原始值，只为让关卡可逐字段
比对，不进入生产链路：

- 缩进在模型里已归一到**字符**，而 test2 快照用的缩进是**缇值 / 20（pt）**；
- 模型只收**真实域**，快照里还带 WPS 口径的合成域（EMBED / HYPERLINK / SHAPE）；
- 缩进、显式属性、公式编号、VML 图形计数（`w:pict`）在模型里没有对应字段。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from lxml import etree

from .document import (
    _CTRL,
    _edge,
    _in_fallback,
    _inside_txbx,
    _table_borders,
    m,
    para_runs,
    para_text,
    wp,
)
from .effective import Resolver, StyleTable, ThemeFonts, _Entry, _local_attrs, w
from .model import Document, HeaderFooter, Para, Section, Story, Table
from .package import PART_STYLES, PART_THEME, Package
from .section import _part_content

# `w:pgNumType/@fmt` -> wdPageNumberStyle（WPS 报整数），与 `own_pages.py` 一致
PGNUM = {
    "decimal": 0,
    "upperRoman": 1,
    "lowerRoman": 2,
    "upperLetter": 3,
    "lowerLetter": 4,
    "ordinal": 5,
    "cardinalText": 6,
    "ordinalText": 7,
    "hex": 8,
    "chicago": 9,
}

_EDGES = ("top", "left", "bottom", "right")
_INSIDE = ("insideH", "insideV")
_FORMULA_NO = re.compile(r"\((\d+)\s*-\s*(\d+)\)")


def _pt(entry: _Entry | None) -> float | None:
    return None if entry is None else cast(float, entry[0]) / 20.0


def _num(entry: _Entry | None) -> float | None:
    return None if entry is None else cast(float, entry[0])


def _text(entry: _Entry | None) -> str | None:
    return None if entry is None else str(entry[0])


def _flag(entry: _Entry | None) -> bool | None:
    return None if entry is None else bool(entry[0])


def _lines(entry: _Entry | None) -> float | None:
    value = _num(entry)
    return None if value is None else value / 100.0


def _resolver(pkg: Package) -> Resolver:
    return Resolver(StyleTable(pkg.xml(PART_STYLES)), ThemeFonts(pkg.xml(PART_THEME)))


def _pict_floating(pict: etree._Element) -> bool:
    """VML 图形是浮动的吗（判据与 `own.py` 一致：定位样式或 wrap）。"""
    for shape in pict.iter():
        if not isinstance(shape.tag, str):
            continue
        style = shape.get("style") or ""
        if "mso-position" in style or "position:absolute" in style:
            return True
        if etree.QName(shape).localname == "wrap":
            return True
    return False


def _objects6(p: etree._Element) -> dict[str, int]:
    """段落对象计数（6 槽，含 `w:pict`），文本框与 `mc:Fallback` 里的不算。"""
    n = {"inline": 0, "anchor": 0, "pict_inline": 0, "pict_float": 0, "ole": 0, "omath": 0}
    for el in p.iter():
        if not isinstance(el.tag, str) or _inside_txbx(el, p) or _in_fallback(el, p):
            continue
        if el.tag == wp("inline"):
            n["inline"] += 1
        elif el.tag == wp("anchor"):
            n["anchor"] += 1
        elif el.tag == w("pict"):
            n["pict_float" if _pict_floating(el) else "pict_inline"] += 1
        elif el.tag == w("object"):
            n["ole"] += 1
        elif el.tag == m("oMath"):
            n["omath"] += 1
    return n


def _line_breaks(p: etree._Element) -> int:
    """段内手动换行数（`w:br` textWrapping 与 `w:cr`）。分页 / 分栏的 `w:br` 不算。"""
    count = 0
    for el in p.iter():
        if not isinstance(el.tag, str) or _inside_txbx(el, p):
            continue
        is_break = el.tag == w("br") and (el.get(w("type")) or "textWrapping") == "textWrapping"
        if el.tag == w("cr") or is_break:
            count += 1
    return count


def _para_explicit(ppr: etree._Element | None) -> dict[str, object]:
    """段落直接写的属性（快照里的 `explicit`）。"""
    out: dict[str, object] = {}
    if ppr is None:
        return out
    jc = ppr.find(w("jc"))
    if jc is not None and jc.get(w("val")):
        out["align"] = jc.get(w("val"))
    ind = ppr.find(w("ind"))
    if ind is not None:
        attrs = _local_attrs(ind)
        if "firstLine" in attrs:
            out["ind_first"] = float(attrs["firstLine"]) / 20.0
        elif "firstLineChars" in attrs:
            out["ind_first_chars"] = float(attrs["firstLineChars"]) / 100.0
    spacing = ppr.find(w("spacing"))
    if spacing is not None:
        attrs = _local_attrs(spacing)
        if "line" in attrs:
            out["line"] = float(attrs["line"]) / 20.0
    outline = ppr.find(w("outlineLvl"))
    if outline is not None and outline.get(w("val")) is not None:
        out["outline"] = int(cast(str, outline.get(w("val"))))
    return out


def _run_explicit(rpr: etree._Element | None) -> dict[str, object]:
    """run 直接写的属性（快照里的 `explicit`）：只认 ascii / eastAsia / sz / b。"""
    out: dict[str, object] = {}
    if rpr is None:
        return out
    fonts = rpr.find(w("rFonts"))
    if fonts is not None:
        if fonts.get(w("ascii")):
            out["ascii"] = fonts.get(w("ascii"))
        if fonts.get(w("eastAsia")):
            out["ea"] = fonts.get(w("eastAsia"))
    size = rpr.find(w("sz"))
    if size is not None and size.get(w("val")):
        out["size"] = int(cast(str, size.get(w("val")))) / 2.0
    if rpr.find(w("b")) is not None:
        val = rpr.find(w("b"))
        raw = val.get(w("val")) if val is not None else None
        out["bold"] = True if raw is None else raw not in ("0", "false", "off", "no")
    return out


def _chars_to_pt(hundredths: float | None, size: float | None) -> float | None:
    """1/100 字符 -> pt（乘段落首 run 字号），与 `own.py` 的 `chars_pt` 同口径。"""
    if hundredths and size:
        return round(hundredths / 100.0 * size, 2)
    return None


def _run_dict(
    run_text: str, rpr: etree._Element | None, para_style_id: str | None, resolver: Resolver
) -> dict[str, object]:
    picked = resolver.raw_rpr(rpr, para_style_id)
    return {
        "text": run_text,
        "size": _num(picked.get("size")),
        "bold": _flag(picked.get("bold")),
        "italic": _flag(picked.get("italic")),
        "underline": _text(picked.get("underline")),
        "va": _text(picked.get("va")),
        "ascii": _text(picked.get("west")),
        "ea": _text(picked.get("ea")),
        "rstyle": _text(picked.get("rstyle")),
        "explicit": _run_explicit(rpr),
    }


def _formula_no(p: etree._Element, resolver: Resolver, para_style_id: str | None) -> dict[str, object] | None:
    """公式编号 `(章号-序号)` 的位置及所在 run 的字体 / 字号。"""
    match = _FORMULA_NO.search(para_text(p))
    if match is None:
        return None
    index = match.start() + 1
    position = 0
    for run in para_runs(p):
        length = len(para_text(run))
        if position <= index < position + length:
            picked = resolver.raw_rpr(run.find(w("rPr")), para_style_id)
            return {
                "no": f"{match.group(1)}-{match.group(2)}",
                "ascii": _text(picked.get("west")),
                "ea": _text(picked.get("ea")),
                "size": _num(picked.get("size")),
            }
        position += length
    return None


def _para_dict(
    para: Para,
    *,
    story: str,
    ordinal: int,
    field_codes: tuple[str, ...],
    resolver: Resolver,
    part: str | None = None,
) -> dict[str, object]:
    """一个段落记录，逐字段对齐 `OwnDoc.para_record`。"""
    pe = para.xml
    ppr = pe.find(w("pPr"))
    picked = resolver.raw_ppr(ppr)
    objects = _objects6(pe)
    text = para.text
    # 快照的空段落口径先剥掉 Word 控制符（`w:br` 记成 `\n`），但不 trim 空白
    stripped = _CTRL.sub("", text)

    size = _run_size(para, ppr)
    first_twips_pt = _pt(picked.get("first_line_twips"))
    first_hundredths = _num(picked.get("first_line_chars"))
    first_chars = None if not first_hundredths else first_hundredths / 100.0
    first_pt = first_twips_pt
    if first_chars is not None:
        first_pt = _chars_to_pt(first_hundredths, size) or first_pt
    if not first_pt:
        hang = _chars_to_pt(_num(picked.get("hanging_chars")), size) or _pt(picked.get("hanging_twips"))
        if hang:
            first_pt = -hang

    line = _pt(picked.get("line"))
    line_rule = _text(picked.get("line_rule"))
    if line is None:
        line, line_rule = 12.0, "auto"  # 文档从未写过行距时，有效值是单倍

    run_records = [_run_dict(run.text, run.xml.find(w("rPr")), para.style_id, resolver) for run in para.runs]
    record: dict[str, object] = {
        "story": story,
        "ordinal": ordinal,
        "text": text,
        "in_table": para.in_table,
        "row_end": para.row_end,
        "text_empty": (not stripped) and objects["inline"] == 0,
        "is_empty": (not stripped) and not any(objects.values()),
        "objects": objects,
        "has_figure": (objects["inline"] + objects["anchor"]) > 0,
        "has_formula": (objects["ole"] + objects["omath"]) > 0,
        "field_codes": list(field_codes),
        "line_breaks": _line_breaks(pe),
        "formula_no": _formula_no(pe, resolver, para.style_id),
        "style_id": para.style_id,
        "style_name": para.style,
        "align": _text(picked.get("align")) or "left",
        "outline": para.outline,
        "page_break_before": para.page_break_before,
        "has_page_break": para.has_page_break,
        "sect_break": para.section_break,
        "keep_with_next": bool(para.keep_with_next),
        "ind_left": _pt(picked.get("left_twips")),
        "ind_right": _pt(picked.get("right_twips")),
        "ind_first": first_pt,
        "ind_first_chars": first_chars,
        "ind_first_twips_pt": first_twips_pt,
        "ind_hanging": _pt(picked.get("hanging_twips")),
        "sp_before": _pt(picked.get("space_before_twips")),
        "sp_after": _pt(picked.get("space_after_twips")),
        "sp_before_lines": _lines(picked.get("space_before_lines")),
        "sp_after_lines": _lines(picked.get("space_after_lines")),
        "line": line,
        "line_rule": line_rule,
        "num_id": para.numbering.num_id if para.numbering is not None else None,
        "explicit": _para_explicit(ppr),
        "runs": run_records,
    }
    if part is not None:
        record["part"] = part
    return record


def _run_size(para: Para, ppr: etree._Element | None) -> float | None:
    """换算缩进字符数用的字号：本段第一个有字号的 run，取不到才看段落标记的 rPr。"""
    size = next((run.size for run in para.runs if run.size), None)
    if size is None and ppr is not None:
        mark = ppr.find(w("rPr"))
        sz = mark.find(w("sz")) if mark is not None else None
        if sz is not None and sz.get(w("val")):
            size = int(cast(str, sz.get(w("val")))) / 2.0
    return size


def _fields(doc: Document) -> list[dict[str, object]]:
    """正文里的域：真实域取模型，合成域（EMBED / HYPERLINK / SHAPE）按快照口径补。"""
    # 域的深度跨段落累计：TOC 域从一段开始，可以一直包到几十段之后
    depths: dict[int, int] = {}
    stack = 0
    for para in doc.paragraphs:
        for el in para.xml.iter():
            if not isinstance(el.tag, str) or _inside_txbx(el, para.xml) or _in_fallback(el, para.xml):
                continue
            if el.tag == w("fldChar"):
                kind = el.get(w("fldCharType"))
                if kind == "begin":
                    depths[id(el)] = stack
                    stack += 1
                elif kind == "end" and stack:
                    stack -= 1
            elif el.tag == w("fldSimple"):
                depths[id(el)] = stack

    out: list[dict[str, object]] = [
        {
            "code": field.code,
            "para": field.start,
            "end_para": field.end,
            "depth": depths.get(id(field.xml), 0),
            "synthetic": False,
            "end_para_content": field.end_content,
        }
        for field in doc.fields
    ]

    for para in doc.paragraphs:
        for el in para.xml.iter():
            if not isinstance(el.tag, str) or _inside_txbx(el, para.xml) or _in_fallback(el, para.xml):
                continue
            synthetic = None
            if el.tag == w("object"):
                synthetic = "EMBED"
            elif el.tag == w("hyperlink"):
                synthetic = "HYPERLINK"
            elif el.tag == w("pict"):
                synthetic = "SHAPE"
            if synthetic:
                out.append(
                    {
                        "code": synthetic,
                        "para": para.id,
                        "end_para": para.id,
                        "depth": None,
                        "synthetic": True,
                        "end_para_content": para.id,
                    }
                )

    out.sort(key=lambda field: (cast(int, field["para"]), cast(str, field["code"])))
    return out


def dump_own(pkg: Package, doc: Document) -> dict[str, object]:
    resolver = _resolver(pkg)
    paragraphs = [
        _para_dict(p, story=p.story.value, ordinal=p.id, field_codes=p.field_codes, resolver=resolver)
        for p in doc.paragraphs
    ]
    cache: dict[str, tuple[tuple[Para, ...], int]] = {}
    for story, kind in (("header", Story.HEADER), ("footer", Story.FOOTER)):
        parts = sorted(n for n in pkg.names() if n.startswith(f"word/{story}") and n.endswith(".xml"))
        ordinal = 0
        for part in parts:
            inner, _ = _part_content(pkg, part, kind, resolver, cache)
            for para in inner:
                paragraphs.append(
                    _para_dict(
                        para,
                        story=story,
                        ordinal=ordinal,
                        field_codes=(),
                        resolver=resolver,
                        part=part,
                    )
                )
                ordinal += 1
    return {
        "path": str(pkg.path),
        "tool": "own",
        "paragraphs": paragraphs,
        "fields": _fields(doc),
        "meta": {"n_tables": len(doc.tables), "n_paragraphs": len(paragraphs)},
    }


def _hf_dict(header_footer: HeaderFooter, resolver: Resolver) -> dict[str, object]:
    return {
        "type": header_footer.ref_type,
        "text": header_footer.text if header_footer.part is not None else None,
        "paragraphs": [
            _para_dict(
                p,
                story=p.story.value,
                ordinal=p.id,
                field_codes=(),
                resolver=resolver,
            )
            for p in header_footer.paragraphs
        ],
        "has_reference": header_footer.owned,
        "part": header_footer.part,
        "page_fields": header_footer.page_fields,
    }


def _section_dict(section: Section, resolver: Resolver) -> dict[str, object]:
    fmt = section.page_number_format
    return {
        "index": section.index,
        "type": section.type,
        "page": {
            "w_pt": section.width_pt,
            "h_pt": section.height_pt,
            "orientation": section.orientation,
            "top_pt": section.top_pt,
            "bottom_pt": section.bottom_pt,
            "left_pt": section.left_pt,
            "right_pt": section.right_pt,
            "header_pt": section.header_pt,
            "footer_pt": section.footer_pt,
            "paper_size": None,
        },
        "page_number_format": (PGNUM.get(fmt) if fmt else 0),
        "page_number_fmt_name": fmt,
        "different_first_page": section.different_first_page,
        "odd_and_even_pages": section.odd_and_even_pages,
        "headers": [_hf_dict(hf, resolver) for hf in section.headers],
        "footers": [_hf_dict(hf, resolver) for hf in section.footers],
    }


def dump_pages(pkg: Package, doc: Document) -> dict[str, object]:
    resolver = _resolver(pkg)
    return {
        "path": str(pkg.path),
        "tool": "own",
        "sections": [_section_dict(section, resolver) for section in doc.sections],
    }


def _cell_edges(
    tc: etree._Element, base: dict[str, bool], row: int, col: int, n_rows: int, n_cols: int
) -> dict[str, object]:
    """单元格四边 + 是否直接写（快照里的 `direct_*`）。"""
    position = {
        "top": "top" if row == 1 else "insideH",
        "bottom": "bottom" if row == n_rows else "insideH",
        "left": "left" if col == 1 else "insideV",
        "right": "right" if col == n_cols else "insideV",
    }
    pr = tc.find(w("tcPr"))
    direct = pr.find(w("tcBorders")) if pr is not None else None
    out: dict[str, object] = {}
    for edge in _EDGES:
        value = _edge(direct.find(w(edge))) if direct is not None else None
        out[edge] = bool(base.get(position[edge], False)) if value is None else value
        out["direct_" + edge] = bool(value)
    return out


def dump_borders(pkg: Package, doc: Document) -> dict[str, object]:
    resolver = _resolver(pkg)
    tables: list[dict[str, object]] = []
    for index, table in enumerate(doc.tables, 1):
        rows = table.xml.findall(w("tr"))
        n_cols = max((len(row.findall(w("tc"))) for row in rows), default=0)
        base = _table_borders(resolver.styles, table.xml)
        cells: list[dict[str, object]] = []
        for row, tr in enumerate(rows[:2], 1):
            for col, tc in enumerate(tr.findall(w("tc"))[:3], 1):
                cells.append(
                    {
                        "r": row,
                        "c": col,
                        "edges": _cell_edges(tc, base, row, col, len(rows), n_cols),
                    }
                )
        tables.append(
            {
                "i": index,
                "rows": table.n_rows,
                "cols": table.n_cols,
                "edges": {edge: base.get(edge) for edge in _EDGES + _INSIDE},
                "cells": cells,
            }
        )
    return {
        "path": str(pkg.path),
        "tool": "own",
        "counts": {"tables": len(tables), "sample": "前2行x前3列"},
        "tables": tables,
    }


def _samples(para: Para) -> dict[str, object]:
    """文本框段落样本：中文字体 / 字号优先取第一个中文字所在 run，否则取第一个 ASCII。"""

    def first(kind: str, key: str) -> object:
        for run in para.runs:
            text = run.text
            if kind == "east" and any("\u4e00" <= c <= "\u9fff" for c in text):
                return getattr(run, key)
            if kind == "west" and any(c.isascii() and c.isalnum() for c in text):
                return getattr(run, key)
        return None

    ea = first("east", "ea")
    west = first("west", "west")
    return {
        "text": para.text,
        "font_ea": ea,
        "font_ascii": west,
        "size": first("east", "size") or first("west", "size"),
        "align": para.align,
        "list_type": para.numbering.num_id if para.numbering is not None else None,
    }


def dump_textbox(pkg: Package, doc: Document) -> dict[str, object]:
    boxes: list[dict[str, object]] = []
    for box in doc.boxes:
        boxes.append(
            {
                "i": box.id,
                "anchor_para": box.host,
                "text": "".join(p.text for p in box.paragraphs),
                "paragraphs": [_samples(p) for p in box.paragraphs],
            }
        )
    with_text = sum(1 for box in boxes if cast(str, box["text"]).strip())
    return {
        "path": str(pkg.path),
        "tool": "own",
        "counts": {"boxes": len(boxes), "boxes_with_text": with_text},
        "boxes": boxes,
    }


# ── ownindex：整篇索引的参考形状 ────────────────────────────────
#
# 与 `test2/docxfmt/index.py` 的 `DocIndex.dump()` 逐字段对齐。索引这一块没有 WPS 裁判，
# 对账的是"解析器提供了参考实现所需的全部事实"——所以**照搬参考算法**（含它宽松的引用
# 正则与 `toc 1/2/3` 口径），产品索引 `thesischeck.index` 是另一条更严格的收集路径。

_INDEX_ZW = "\u200b"
_INDEX_CHAPTER = re.compile(r"^第([一二三四五六七八九十]+|\d+)章")
_INDEX_CN = {char: value for value, char in enumerate("一二三四五六七八九十", 1)}
_INDEX_FIGURE = re.compile(r"^图\s*(\d+)\s*-\s*(\d+)")
_INDEX_TABLE = re.compile(r"^表\s*(\d+)\s*-\s*(\d+)")
_INDEX_FORMULA = re.compile(r"\((\d+)\s*-\s*(\d+)\)")
_INDEX_TOC_STYLE = re.compile(r"^toc\s*([123])$")
_INDEX_CITE = re.compile(r"^\[?\s*(\d+(?:\s*[-–,，]\s*\d+)*)\s*\]?$")
_INDEX_MODULES: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("中文摘要", lambda text: text == "摘要"),
    ("英文摘要", lambda text: text == "ABSTRACT"),
    ("目录", lambda text: text == "目录"),
    ("正文", lambda text: re.match(r"^第[一二三四五六七八九十]+章", text) is not None),
    ("参考文献", lambda text: text == "参考文献"),
    ("致谢", lambda text: text == "致谢"),
    ("附录", lambda text: text.startswith("附录")),
)


@dataclass(frozen=True, slots=True)
class _IndexRecord:
    text: str
    style_name: str | None
    outline: int | None
    has_formula: bool
    ole: int
    omath: int
    runs: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True, slots=True)
class _IndexModule:
    name: str
    start: int
    end: int


def _index_key_text(text: str) -> str:
    """参考实现的识别锚点：去所有空白，再去掉开头的零宽空格。"""
    return re.sub(r"\s+", "", text or "").lstrip(_INDEX_ZW)


def _index_chapter_no(text: str) -> int | None:
    match = _INDEX_CHAPTER.match(text)
    if match is None:
        return None
    group = match.group(1)
    return int(group) if group.isdigit() else _INDEX_CN.get(group[0], 0) or None


def _index_is_toc_like(record: _IndexRecord) -> bool:
    return _INDEX_TOC_STYLE.match((record.style_name or "").strip().lower()) is not None


def _index_records(doc: Document) -> list[_IndexRecord]:
    return [
        _IndexRecord(
            text=para.text,
            style_name=para.style,
            outline=para.outline,
            has_formula=(para.objects.ole + para.objects.omath) > 0,
            ole=para.objects.ole,
            omath=para.objects.omath,
            runs=tuple((run.text, run.va) for run in para.runs),
        )
        for para in doc.paragraphs
    ]


def _index_blocks(doc: Document) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for block in doc.blocks:
        if isinstance(block, Para):
            blocks.append({"kind": "p", "paras": [block.id]})
        elif isinstance(block, Table):
            paras = [cell_para.id for row in block.rows for cell in row for cell_para in cell.paragraphs]
            blocks.append({"kind": "tbl", "paras": paras, "rows": block.n_rows, "cols": block.n_cols})
    for i, entry in enumerate(blocks):
        entry["i"] = i
    return blocks


def _index_module_spans(records: list[_IndexRecord]) -> list[_IndexModule]:
    bounds: list[tuple[str, int]] = []
    for name, predicate in _INDEX_MODULES:
        hit = next(
            (
                i
                for i, record in enumerate(records)
                if predicate(_index_key_text(record.text)) and not _index_is_toc_like(record)
            ),
            None,
        )
        if hit is not None:
            bounds.append((name, hit))
    spans: list[_IndexModule] = []
    previous_name, previous_start = "封面", 0
    for name, start in bounds:
        if start > previous_start:
            spans.append(_IndexModule(previous_name, previous_start, start - 1))
        previous_name, previous_start = name, start
    spans.append(_IndexModule(previous_name, previous_start, len(records) - 1))
    return spans


def _index_module_dicts(spans: list[_IndexModule]) -> list[dict[str, object]]:
    return [{"name": span.name, "from": span.start, "to": span.end} for span in spans]


def _index_zone(spans: list[_IndexModule], name: str) -> _IndexModule | None:
    return next((span for span in spans if span.name == name), None)


def _index_chapters(records: list[_IndexRecord], spans: list[_IndexModule]) -> list[dict[str, object]]:
    zone = _index_zone(spans, "正文")
    if zone is None:
        return []
    found: list[tuple[int, str, int, int | None, str | None]] = []
    for i in range(zone.start, zone.end + 1):
        record = records[i]
        if _index_is_toc_like(record):
            continue
        key = _index_key_text(record.text)
        no = _index_chapter_no(key)
        if no is not None:
            found.append((no, key[:24], i, record.outline, record.style_name))
    out: list[dict[str, object]] = []
    for position, (no, text, para, outline, style_name) in enumerate(found):
        end = found[position + 1][2] - 1 if position + 1 < len(found) else zone.end
        out.append(
            {
                "no": no,
                "text": text,
                "para": para,
                "outline": outline,
                "style_name": style_name,
                "is_heading1": outline == 0,
                "to": end,
            }
        )
    return out


def _index_floats(records: list[_IndexRecord]) -> dict[str, object]:
    figures: list[dict[str, object]] = []
    tables: list[dict[str, object]] = []
    formulas: list[dict[str, object]] = []
    objects = 0
    for i, record in enumerate(records):
        text = _index_key_text(record.text)
        figure = _INDEX_FIGURE.match(text)
        if figure:
            figures.append({"no": f"{figure.group(1)}-{figure.group(2)}", "para": i})
        table = _INDEX_TABLE.match(text)
        if table:
            tables.append({"no": f"{table.group(1)}-{table.group(2)}", "para": i})
        if record.has_formula:
            objects += record.ole + record.omath
            formula = _INDEX_FORMULA.search(record.text)
            no = f"{formula.group(1)}-{formula.group(2)}" if formula else None
            formulas.append({"no": no, "para": i})
    return {"figure": figures, "table": tables, "formula": formulas, "formula_objects": objects}


def _index_citations(records: list[_IndexRecord], spans: list[_IndexModule]) -> list[dict[str, object]]:
    zone = _index_zone(spans, "正文")
    out: list[dict[str, object]] = []
    if zone is None:
        return out
    seen: dict[int, int] = {}
    for i in range(zone.start, zone.end + 1):
        for text, va in records[i].runs:
            if va != "superscript" or not text.strip():
                continue
            match = _INDEX_CITE.match(text.strip())
            if match is None:
                continue
            for part in re.split(r"[,，]", match.group(1)):
                numbers = [int(x) for x in re.split(r"[-–]", part.strip()) if x.strip().isdigit()]
                if len(numbers) == 2:
                    numbers = list(range(numbers[0], numbers[1] + 1))
                for number in numbers:
                    if number not in seen:
                        seen[number] = len(seen) + 1
                        out.append({"no": number, "para": i, "order": seen[number]})
    return out


def _index_toc_entries(records: list[_IndexRecord], doc: Document) -> list[dict[str, object]]:
    toc = next((field for field in doc.fields if field.code == "TOC"), None)
    if toc is None:
        return []
    out: list[dict[str, object]] = []
    for i in range(toc.start, toc.end + 1):
        record = records[i]
        match = _INDEX_TOC_STYLE.match((record.style_name or "").strip().lower())
        if match:
            out.append({"level": int(match.group(1)), "text": record.text[:40], "para": i})
    return out


def dump_index(pkg: Package, doc: Document) -> dict[str, object]:
    records = _index_records(doc)
    spans = _index_module_spans(records)
    return {
        "path": str(pkg.path),
        "tool": "own",
        "blocks": _index_blocks(doc),
        "modules": _index_module_dicts(spans),
        "chapters": _index_chapters(records, spans),
        "floats": _index_floats(records),
        "citations": _index_citations(records, spans),
        "toc_entries": _index_toc_entries(records, doc),
    }


_SUITES = {
    "own": dump_own,
    "ownpages": dump_pages,
    "ownborders": dump_borders,
    "owntextbox": dump_textbox,
    "ownindex": dump_index,
}


def dump_suite(suite: str, pkg: Package, doc: Document) -> dict[str, object]:
    return _SUITES[suite](pkg, doc)
