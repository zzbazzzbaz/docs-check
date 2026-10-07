"""L1 文档模型：把正文流解析成块序列（`w:p` 与 `w:tbl` 按文件顺序交错）。

口径照搬 `调研/test2/docxfmt/own*.py`（40 篇语料逐字段对到 99.999%），下面每条都是踩出来的：

- 内容控件 `w:sdt` **透传**：进 `sdtContent` 时段落计数器接着走，不重置
- 表格按 `tr` / `tc` 下钻（对表根直接递归会数出 0 段）；每个表格**行末**打 `row_end`
  （WPS 的 `Paragraphs` 会在行末多算一个空段，靠这个标记对账）
- 可见文本收 `w:t` 与 `m:t`；`w:tab` 只有在 `w:r` 里才算制表符（`w:pPr/w:tabs` 是制表位定义）；
  不收域代码与文本框内容；Word 控制符（`_CTRL`）不是可见文字
- `mc:Fallback` 里是同一个对象的兼容写法（DrawingML + VML 两份），一律跳过
- **文本框**（`w:txbxContent`）走单独一路，不进正文块序列，并记宿主段落号
- 单元格四边 = 直接写的 `tcBorders`，否则按**位置**取表级对应边（按同名边直接继承实测只有 64% 一致）
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import cast

from lxml import etree

from ..errors import BadDocument
from .effective import Resolver, StyleTable, ThemeFonts, interpret_elements, note_element, w
from .model import Borders, Box, Cell, Document, Objects, Para, Run, Story, Table
from .package import PART_DOCUMENT, PART_NUMBERING, PART_STYLES, PART_THEME, Package

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"

_FALLBACK = f"{{{MC_NS}}}Fallback"

# Word 内部控制字符：段落标记 / 换行 / 分页 / 域分隔 / 内嵌对象占位符…都不是可见文字
_CTRL = re.compile(r"[\r\n\v\f\a\x07\x0c\x01\x02\x05\x0e\x13\x14\x15]")

_NO_LINE = ("none", "nil")
_EDGES = ("top", "left", "bottom", "right")
_INSIDE = ("insideH", "insideV")


def m(tag: str) -> str:
    note_element(tag)
    return f"{{{M_NS}}}{tag}"


def wp(tag: str) -> str:
    note_element(tag)
    return f"{{{WP_NS}}}{tag}"


def _tag(el: etree._Element | None) -> str:
    if el is None:
        return ""
    return cast(str, el.tag).rsplit("}", 1)[-1]


def _visible(text: str | None) -> str:
    return _CTRL.sub("", text or "")


def _inside_txbx(el: etree._Element, stop: etree._Element) -> bool:
    """在 `w:txbxContent` 里吗（不含 stop 本身）。"""
    anc = el.getparent()
    while anc is not None and anc is not stop:
        if anc.tag == w("txbxContent"):
            return True
        anc = anc.getparent()
    return False


def _in_fallback(el: etree._Element, stop: etree._Element) -> bool:
    """在 `mc:Fallback` 里吗？Word 用 AlternateContent 同时写两份，是同一个对象。"""
    anc = el.getparent()
    while anc is not None and anc is not stop:
        if anc.tag == _FALLBACK:
            return True
        anc = anc.getparent()
    return False


def iter_paragraphs(node: etree._Element, in_table: bool = False) -> list[tuple[etree._Element, bool, bool]]:
    """按文档顺序取段落 -> [(元素, 是否在表格内, 是否表格行末)]。

    表格下钻、`w:sdt` 下钻、文本框不下钻。
    """
    out: list[tuple[etree._Element, bool, bool]] = []
    for child in node:
        if not isinstance(child.tag, str):
            continue
        if child.tag == w("p"):
            out.append((child, in_table, False))
        elif child.tag == w("tbl"):
            for tr in child.findall(w("tr")):
                mark = len(out)
                for tc in tr.findall(w("tc")):
                    out.extend(iter_paragraphs(tc, True))
                if len(out) > mark:
                    el, _, _ = out[-1]
                    out[-1] = (el, True, True)
        elif child.tag == w("sdt"):
            content = child.find(w("sdtContent"))
            if content is not None:
                out.extend(iter_paragraphs(content, in_table))
    return out


def para_runs(p: etree._Element) -> list[etree._Element]:
    """段落里的 run，只取**不在文本框里**的。"""
    return [r for r in p.iter(w("r")) if not _inside_txbx(r, p)]


def para_text(p: etree._Element) -> str:
    """可见文本：正文文字 + 公式文字，制表符记 `\\t`、换行记 `\\n`；域代码与文本框不收。

    两个坑：`w:tab` 有两处含义（`w:r` 里是制表符，`w:pPr/w:tabs` 里是制表位定义）；
    `m:t`（公式文字）也是可见文本，但它属于 `m:r`，没有对应的 `w:r`。
    """
    parts: list[str] = []
    for el in p.iter():
        if not isinstance(el.tag, str) or _inside_txbx(el, p) or _in_fallback(el, p):
            continue
        if el.tag == w("t") or el.tag == m("t"):
            parts.append(_visible(el.text))
        elif el.tag == w("tab") and _tag(el.getparent()) == "r":
            parts.append("\t")
        elif el.tag in (w("br"), w("cr")) and _tag(el.getparent()) == "r":
            parts.append("\n")
        elif el.tag == w("noBreakHyphen"):
            parts.append("\u2011")  # 不可断开连字符
        elif el.tag == w("softHyphen"):
            parts.append("\u00ad")  # 可选连字符
    return "".join(parts)


def object_counts(p: etree._Element) -> Objects:
    """段落里的对象计数（文本框内、`mc:Fallback` 里的不算）。

    公式：`m:oMathPara` 只是 `m:oMath` 的容器，只数 `m:oMath`，否则会重复。`m:oMathPara`
    的对齐（`m:jc`，缺省按规范记 `centerGroup`）单独记进 `omath_para_align`。
    """
    inline = floating = ole = omath = 0
    omath_para_align: str | None = None
    for el in p.iter():
        if not isinstance(el.tag, str) or _inside_txbx(el, p) or _in_fallback(el, p):
            continue
        if el.tag == wp("inline"):
            inline += 1
        elif el.tag == wp("anchor"):
            floating += 1
        elif el.tag == w("object"):
            ole += 1
        elif el.tag == m("oMath"):
            omath += 1
        elif el.tag == m("oMathPara"):
            jc = el.find(f"{m('oMathParaPr')}/{m('jc')}")
            omath_para_align = (jc.get(m("val")) if jc is not None else None) or "centerGroup"
    return Objects(
        inline_images=inline,
        floating_images=floating,
        ole=ole,
        omath=omath,
        omath_para_align=omath_para_align,
    )


def _edge(el: etree._Element | None) -> bool | None:
    """`w:top` 这类元素 -> 有没有线。元素存在且 `w:val` 不是 none/nil 就是有线。"""
    if el is None:
        return None
    val = el.get(w("val"))
    return val is None or val not in _NO_LINE


def _style_borders(styles: StyleTable, tbl: etree._Element) -> dict[str, bool]:
    """表格样式（含 `basedOn` 链）的 `tblBorders`，低层先入、高层覆盖。"""
    pr = tbl.find(w("tblPr"))
    st = pr.find(w("tblStyle")) if pr is not None else None
    sid = st.get(w("val")) if st is not None else None
    out: dict[str, bool] = {}
    for style in styles.chain(sid):
        borders = style.tbl_pr.find(w("tblBorders")) if style.tbl_pr is not None else None
        if borders is None:
            continue
        for edge in _EDGES + _INSIDE:
            value = _edge(borders.find(w(edge)))
            if value is not None:
                out[edge] = value
    return out


def _table_borders(styles: StyleTable, tbl: etree._Element) -> dict[str, bool]:
    """表级有效边框：表直接写的 `tblBorders` 覆盖表格样式的。"""
    out = _style_borders(styles, tbl)
    pr = tbl.find(w("tblPr"))
    borders = pr.find(w("tblBorders")) if pr is not None else None
    if borders is not None:
        for edge in _EDGES + _INSIDE:
            value = _edge(borders.find(w(edge)))
            if value is not None:
                out[edge] = value
    return out


def _style_conditional_borders(styles: StyleTable, tbl: etree._Element) -> bool:
    """该表所用表格样式链里，是否任一样式带条件格式边框（事实，不合成线）。"""
    pr = tbl.find(w("tblPr"))
    st = pr.find(w("tblStyle")) if pr is not None else None
    sid = st.get(w("val")) if st is not None else None
    return any(style.conditional_borders for style in styles.chain(sid))


def _cell_borders(
    tc: etree._Element, base: dict[str, bool], row: int, col: int, n_rows: int, n_cols: int
) -> Borders:
    """单元格四边 = 直接写的 `tcBorders`，否则按位置取表级对应边：

    上 -> 首行取 `top`、其余取 `insideH`；下 -> 末行取 `bottom`、其余取 `insideH`；
    左 / 右 -> 首列取 `left`、末列取 `right`、其余取 `insideV`。
    """
    position = {
        "top": "top" if row == 1 else "insideH",
        "bottom": "bottom" if row == n_rows else "insideH",
        "left": "left" if col == 1 else "insideV",
        "right": "right" if col == n_cols else "insideV",
    }
    pr = tc.find(w("tcPr"))
    direct = pr.find(w("tcBorders")) if pr is not None else None
    edges: dict[str, bool] = {}
    for edge in _EDGES:
        value = _edge(direct.find(w(edge))) if direct is not None else None
        edges[edge] = bool(base.get(position[edge], False)) if value is None else value
    return Borders(top=edges["top"], bottom=edges["bottom"], left=edges["left"], right=edges["right"])


def _style_id(ppr: etree._Element | None, resolver: Resolver) -> str | None:
    """段落直接写的 `pStyle`，没写就套默认段落样式。"""
    if ppr is not None:
        pstyle = ppr.find(w("pStyle"))
        if pstyle is not None and pstyle.get(w("val")):
            return pstyle.get(w("val"))
    return resolver.styles.default_para


def _record_run(
    r: etree._Element, p: etree._Element, style_id: str | None, resolver: Resolver, index: int
) -> Run:
    fmt = resolver.run(r.find(w("rPr")), style_id)
    text = "".join(_visible(t.text) for t in r.iter(w("t")) if not _inside_txbx(t, p))
    return Run(
        text=text,
        ea=fmt.ea,
        west=fmt.west,
        size=fmt.size,
        bold=fmt.bold,
        italic=fmt.italic,
        va=fmt.va,
        index=index,
        xml=r,
    )


def _record_para(
    p: etree._Element,
    story: Story,
    pid: int,
    resolver: Resolver,
    *,
    in_table: bool = False,
    row_end: bool = False,
    section: int | None = None,
    field_codes: tuple[str, ...] = (),
) -> Para:
    ppr = p.find(w("pPr"))
    style_id = _style_id(ppr, resolver)
    runs = tuple(_record_run(r, p, style_id, resolver, index) for index, r in enumerate(para_runs(p)))
    # 段落格式把缩进缇值换算成字符时要字号：用本段第一个有字号的 run，取不到才看段落标记的 rPr
    size_pt = next((r.size for r in runs if r.size), None)
    if size_pt is None and ppr is not None:
        mark = ppr.find(w("rPr"))
        size = mark.find(w("sz")) if mark is not None else None
        val = size.get(w("val")) if size is not None else None
        if val is not None:
            size_pt = int(val) / 2.0
    fmt = resolver.para(ppr, size_pt=size_pt)
    # 显式分页符：`w:br w:type="page"`（`w:pageBreakBefore` 是另一路，两者都算"这一页到此为止"）
    has_page_break = fmt.page_break_before or any(
        br.get(w("type")) == "page" for br in p.iter(w("br")) if not _inside_txbx(br, p)
    )
    return Para(
        id=pid,
        story=story,
        text=para_text(p),
        style=fmt.style_name,
        style_id=fmt.style_id,
        outline=fmt.outline,
        align=fmt.align,
        line_rule=fmt.line_rule,
        line_multiple=fmt.line_multiple,
        line_pt=fmt.line_pt,
        first_line_chars=fmt.first_line_chars,
        left_chars=fmt.left_chars,
        right_chars=fmt.right_chars,
        hanging_chars=fmt.hanging_chars,
        space_before_pt=fmt.space_before_pt,
        space_after_pt=fmt.space_after_pt,
        numbering=fmt.numbering,
        page_break_before=fmt.page_break_before,
        keep_with_next=fmt.keep_with_next,
        section_break=ppr is not None and ppr.find(w("sectPr")) is not None,
        has_page_break=has_page_break,
        runs=runs,
        objects=object_counts(p),
        field_codes=field_codes,
        in_table=in_table,
        row_end=row_end,
        section=section,
        xml=p,
    )


def _top_level_tables(body: etree._Element) -> list[etree._Element]:
    """只数顶层表格：嵌套表格不单独计，文本框与 `mc:Fallback` 里的不算。"""
    return [
        el
        for el in body.iter(w("tbl"))
        if not _inside_txbx(el, body)
        and not _in_fallback(el, body)
        and not any(anc.tag == w("tbl") for anc in el.iterancestors())
    ]


def _record_table(
    tbl: etree._Element, tid: int, by_element: dict[etree._Element, Para], resolver: Resolver
) -> Table:
    rows_el = tbl.findall(w("tr"))
    n_rows = len(rows_el)
    n_cols = max((len(tr.findall(w("tc"))) for tr in rows_el), default=0)
    base = _table_borders(resolver.styles, tbl)
    rows: list[tuple[Cell, ...]] = []
    for row, tr in enumerate(rows_el, 1):
        cells: list[Cell] = []
        for col, tc in enumerate(tr.findall(w("tc")), 1):
            paragraphs = tuple(by_element[el] for el, _, _ in iter_paragraphs(tc))
            cells.append(
                Cell(
                    row=row,
                    col=col,
                    borders=_cell_borders(tc, base, row, col, n_rows, n_cols),
                    paragraphs=paragraphs,
                    xml=tc,
                )
            )
        rows.append(tuple(cells))
    return Table(
        id=tid,
        n_rows=n_rows,
        n_cols=n_cols,
        rows=tuple(rows),
        style_conditional_borders=_style_conditional_borders(resolver.styles, tbl),
        xml=tbl,
    )


def _host_para(txbx: etree._Element, by_element: dict[etree._Element, Para]) -> int | None:
    """文本框的宿主段落：最近的 `w:p` 祖先（浮动文本框锚在它上面）。"""
    anc = txbx.getparent()
    while anc is not None and anc.tag != w("p"):
        anc = anc.getparent()
    para = by_element.get(anc) if anc is not None else None
    return para.id if para is not None else None


def _record_boxes(
    body: etree._Element, by_element: dict[etree._Element, Para], resolver: Resolver
) -> tuple[Box, ...]:
    boxes: list[Box] = []
    for txbx in body.iter(w("txbxContent")):
        if _in_fallback(txbx, body):
            continue
        inner = iter_paragraphs(txbx)
        paragraphs = tuple(
            _record_para(el, Story.TEXTBOX, i, resolver, in_table=in_tbl, row_end=row_end)
            for i, (el, in_tbl, row_end) in enumerate(inner)
        )
        boxes.append(
            Box(
                id=len(boxes) + 1,
                host=_host_para(txbx, by_element),
                paragraphs=paragraphs,
                xml=txbx,
            )
        )
    return tuple(boxes)


def _record_blocks(
    node: etree._Element,
    by_element: dict[etree._Element, Para],
    tables: dict[etree._Element, Table],
) -> tuple[Para | Table, ...]:
    """块序列：`w:p` / `w:tbl` 按文件顺序交错；`w:sdt` 透传。"""
    out: list[Para | Table] = []
    for child in node:
        if not isinstance(child.tag, str):
            continue
        if child.tag == w("p") and child in by_element:
            out.append(by_element[child])
        elif child.tag == w("tbl") and child in tables:
            out.append(tables[child])
        elif child.tag == w("sdt"):
            content = child.find(w("sdtContent"))
            if content is not None:
                out.extend(_record_blocks(content, by_element, tables))
    return tuple(out)


def resolver_for(pkg: Package) -> Resolver:
    """构建有效格式解析器。

    报告按需回溯要用同一个 `Resolver`；这里与 `parse_document` 共用同一构造，保证取值与
    来源是同一份实现（技术设计 §4.2）。
    """
    return Resolver(StyleTable(pkg.xml(PART_STYLES)), ThemeFonts(pkg.xml(PART_THEME)))


# 已知的格式属性容器：其内部（连同自身）都是"格式细节"而非"结构"，不计入未认识清单。
# 这些容器里的结构性子元素（样式、编号、分节等）由专门代码解读，本就不该在这条信号里重复出现。
_PROPERTY_CONTAINERS = frozenset(
    {
        "pPr",
        "rPr",
        "tblPr",
        "tblPrEx",
        "trPr",
        "tcPr",
        "sectPr",
        "pPrChange",
        "rPrChange",
        "tblPrChange",
        "trPrChange",
        "tcPrChange",
        "sectPrChange",
    }
)


def _unknown_elements(body: etree._Element, seen: set[str]) -> tuple[str, ...]:
    """`document.xml` 正文里出现过、但解析器从未查询过的 `w:` 元素局部名（排序去重）。

    只看主命名空间、只看结构位置：DrawingML / VML / `mc:Fallback` 等兼容写法由
    `mc:Fallback` 去重后跳过，格式属性容器（`pPr` / `rPr` / `tcPr` …）里的细节不计。
    清单只陈述事实，不判定。
    """
    prefix = f"{{{W_NS}}}"
    present: set[str] = set()

    def walk(el: etree._Element) -> None:
        for child in el:
            if not isinstance(child.tag, str) or not child.tag.startswith(prefix):
                continue
            name = child.tag[len(prefix) :]
            if name in _PROPERTY_CONTAINERS:
                continue
            present.add(name)
            walk(child)

    walk(body)
    return tuple(sorted(present - seen))


def _parse_body(pkg: Package, body: etree._Element) -> Document:
    """解析 `w:body`（不含分节）：块序列 + 段落 + 表格 + 文本框 + 域。"""
    resolver = resolver_for(pkg)

    flat = iter_paragraphs(body)

    # 域分析要在构造 Para 之前做完：Para 是 frozen 的，「起始域代码」必须一次填好
    from .fields import parse_fields  # 局部导入：fields 复用本模块的文本与对象口径

    fields = parse_fields([el for el, _, _ in flat])
    codes: dict[int, list[str]] = {}
    for field in fields:
        codes.setdefault(field.start, []).append(field.code)

    # 段落级 sectPr 结束它所在的那一节；这一段属于当前节，之后进入下一节
    paras: list[Para] = []
    section = 1
    for i, (el, in_table, row_end) in enumerate(flat):
        ppr = el.find(w("pPr"))
        break_here = ppr is not None and ppr.find(w("sectPr")) is not None
        paras.append(
            _record_para(
                el,
                Story.MAIN,
                i,
                resolver,
                in_table=in_table,
                row_end=row_end,
                section=section,
                field_codes=tuple(codes.get(i, ())),
            )
        )
        if break_here:
            section += 1
    by_element = {el: para for (el, _, _), para in zip(flat, paras, strict=True)}

    top = _top_level_tables(body)
    tables = [_record_table(el, i, by_element, resolver) for i, el in enumerate(top, 1)]
    by_table = dict(zip(top, tables, strict=True))

    return Document(
        blocks=_record_blocks(body, by_element, by_table),
        paragraphs=tuple(paras),
        tables=tuple(tables),
        boxes=_record_boxes(body, by_element, resolver),
        fields=fields,
        sections=(),
        has_numbering_part=pkg.has(PART_NUMBERING),
        xml=body,
    )


def parse_document(pkg: Package) -> Document:
    """解析 `word/document.xml`：块序列 + 全部段落 + 顶层表格 + 文本框 + 域 + 分节。

    解析全程收集"实际解读过的元素局部名"，据此得到 `Document.unknown_elements`（`FR-10.4`）。
    域与分节分别在 `fields.parse_fields`、`section.parse_sections` 里；这里只负责编排，
    并在构造 `Para` 之前先把起始域代码与分节号算好（`Para` 是 frozen 的）。
    """
    root = pkg.xml(PART_DOCUMENT)
    if root is None:
        raise BadDocument("缺少 word/document.xml")
    body = root.find(w("body"))
    if body is None:
        raise BadDocument("word/document.xml 里没有 w:body，文件可能已损坏")

    with interpret_elements() as seen:
        document = replace(_parse_body(pkg, body), unknown_elements=_unknown_elements(body, seen))

    from .section import parse_sections  # 局部导入：分节要复用本模块的段落构造

    return replace(document, sections=parse_sections(pkg, document))
