"""分节 · 页眉页脚 · 页面设置。

口径照搬 `test2/docxfmt/own_pages.py`（40 篇语料逐字段对到 100%）：

- 分节：段落级 `w:sectPr` 结束它所在的那一节，按文档顺序排；body 级 `w:sectPr` 是最后一节
- 页眉页脚按节继承：本节没写该类型的引用，就沿用上一节生效的部件；`owned` 区分"本节自有"
  与"继承而来"（WPS 的 `link_to_previous` 对账字段）
- 页面设置读 `w:pgSz` / `w:pgMar` / `w:pgNumType/@fmt`，长度一律 pt（缇 / 20）
- 分页标记在段落事实上：分节符 `Para.section_break`、`w:br w:type="page"` `Para.has_page_break`、
  `w:pageBreakBefore` `Para.page_break_before`
"""

from __future__ import annotations

from typing import cast

from lxml import etree

from .document import _inside_txbx, _record_para, iter_paragraphs
from .effective import Resolver, StyleTable, ThemeFonts, _local_attrs, w
from .model import Document, HeaderFooter, Para, Run, Section, Story
from .package import PART_DOCUMENT, PART_SETTINGS, PART_STYLES, PART_THEME, Package

R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# `w:headerReference` / `w:footerReference` 的三种类型；缺省是 default
REF_TYPES = ("default", "first", "even")


def _pt(value: str | None) -> float | None:
    """缇 -> pt；取不到就是 None。"""
    return None if value is None else round(float(value) / 20.0, 2)


def _page_fields(root: etree._Element) -> int:
    """部件里的 PAGE 域个数。

    两种写法都要数：`w:fldChar` + `w:instrText` 与 `w:fldSimple`；文本框里的域不算
    （与主对账、与 WPS 的 Range 语义一致——WPS 不数图形内的域）。
    """
    return sum(
        1
        for el in root.iter(w("instrText"))
        if (el.text or "").strip().startswith("PAGE") and not _inside_txbx(el, root)
    ) + sum(
        1
        for el in root.iter(w("fldSimple"))
        if (el.get(w("instr")) or "").strip().startswith("PAGE") and not _inside_txbx(el, root)
    )


def _fld_char_type(r: etree._Element) -> str | None:
    fld = r.find(w("fldChar"))
    return None if fld is None else fld.get(w("fldCharType"))


def _is_page_instr(r: etree._Element) -> bool:
    instr = r.find(w("instrText"))
    if instr is None:
        return False
    text = cast(str, instr.text or "")
    return text.strip().startswith("PAGE")


def _page_field_elements(root: etree._Element) -> set[int]:
    """PAGE 域区间内的 `w:r` / `w:fldSimple` 内的 run 元素 id 集合。

    从含 PAGE `instrText` 的 run 向前找最近的 `begin`、向后找最近的 `end`，区间内的 run
    全收（缓存的结果 run 也在内）；没有 `separate` / 结果时区间里仍有 `instrText` run。
    `w:fldSimple` 直接收其内部 run。
    """
    ids: set[int] = set()
    for p in root.iter(w("p")):
        runs = list(p.iter(w("r")))
        for i, r in enumerate(runs):
            if not _is_page_instr(r):
                continue
            start = i
            while start >= 0 and _fld_char_type(runs[start]) != "begin":
                start -= 1
            stop = i
            while stop < len(runs) and _fld_char_type(runs[stop]) != "end":
                stop += 1
            for r2 in runs[max(start, 0) : min(stop + 1, len(runs))]:
                ids.add(id(r2))
    for simple in root.iter(w("fldSimple")):
        if (simple.get(w("instr")) or "").strip().startswith("PAGE") and not _inside_txbx(simple, root):
            ids.update(id(r) for r in simple.iter(w("r")))
    return ids


def _part_content(
    pkg: Package,
    part: str,
    story: Story,
    resolver: Resolver,
    cache: dict[str, tuple[tuple[Para, ...], int]],
    page_cache: dict[str, tuple[tuple[Run, ...], tuple[Para, ...]]] | None = None,
) -> tuple[tuple[Para, ...], int]:
    """页眉/页脚部件的段落与 PAGE 域数；同一部件只构造一次。

    `page_cache` 给定时顺带记下 PAGE 域区间内的 run / 段落（复用**同一棵树**，否则元素
    身份对不上）。
    """
    cached = cache.get(part)
    if cached is not None:
        return cached
    root = pkg.xml(part)
    result: tuple[tuple[Para, ...], int] = ((), 0)
    if root is not None:
        paragraphs = tuple(
            _record_para(el, story, i, resolver, in_table=in_table, row_end=row_end)
            for i, (el, in_table, row_end) in enumerate(iter_paragraphs(root))
        )
        result = (paragraphs, _page_fields(root))
        if page_cache is not None:
            page_cache[part] = _page_number_content(paragraphs, _page_field_elements(root))
    cache[part] = result
    return result


def _page_number_content(
    paragraphs: tuple[Para, ...], ids: set[int]
) -> tuple[tuple[Run, ...], tuple[Para, ...]]:
    """从已构造的段落里摘出 PAGE 域区间内的 run 与承载它们的段落。"""
    runs = tuple(run for para in paragraphs for run in para.runs if id(run.xml) in ids)
    paras = tuple(para for para in paragraphs if any(id(run.xml) in ids for run in para.runs))
    return runs, paras


def parse_sections(pkg: Package, doc: Document) -> tuple[Section, ...]:
    """按文档顺序解析分节；`doc.xml` 是 `w:body`。"""
    body = doc.xml
    resolver = Resolver(StyleTable(pkg.xml(PART_STYLES)), ThemeFonts(pkg.xml(PART_THEME)))

    # 分节符：段落级的按文档顺序在前，body 级的最后
    props: list[etree._Element] = []
    for p in body.iter(w("p")):
        ppr = p.find(w("pPr"))
        sect_pr = ppr.find(w("sectPr")) if ppr is not None else None
        if sect_pr is not None:
            props.append(sect_pr)
    body_props = body.find(w("sectPr"))
    if body_props is not None:
        props.append(body_props)

    rels = pkg.relationships(PART_DOCUMENT)
    settings = pkg.xml(PART_SETTINGS)
    even_odd = settings is not None and settings.find(w("evenAndOddHeaders")) is not None

    cache: dict[str, tuple[tuple[Para, ...], int]] = {}
    page_cache: dict[str, tuple[tuple[Run, ...], tuple[Para, ...]]] = {}
    # 各类型页眉/页脚已生效的部件，按节往下传
    carried: dict[tuple[str, str], str | None] = {}
    sections: list[Section] = []
    for index, sect in enumerate(props, 1):
        size_el = sect.find(w("pgSz"))
        margin_el = sect.find(w("pgMar"))
        size = _local_attrs(size_el) if size_el is not None else {}
        margin = _local_attrs(margin_el) if margin_el is not None else {}
        typ = sect.find(w("type"))
        pgnum = sect.find(w("pgNumType"))

        groups: dict[str, list[HeaderFooter]] = {"header": [], "footer": []}
        for kind, story in (("header", Story.HEADER), ("footer", Story.FOOTER)):
            for ref_type in REF_TYPES:
                ref = next(
                    (
                        e
                        for e in sect.findall(w(kind + "Reference"))
                        if e.get(w("type"), "default") == ref_type
                    ),
                    None,
                )
                if ref is not None:
                    rel = rels.get(ref.get(f"{{{R_NS}}}id") or "")
                    part = rel.target if rel is not None else None
                    carried[(kind, ref_type)] = part if part is not None and pkg.has(part) else None
                part = carried.get((kind, ref_type))
                paragraphs, page_fields = (
                    _part_content(pkg, part, story, resolver, cache, page_cache)
                    if part is not None
                    else ((), 0)
                )
                page_runs, page_paras = page_cache.get(part, ((), ())) if part is not None else ((), ())
                groups[kind].append(
                    HeaderFooter(
                        kind=kind,
                        ref_type=ref_type,
                        owned=ref is not None,
                        part=part,
                        text="".join(p.text for p in paragraphs),
                        page_fields=page_fields,
                        paragraphs=paragraphs,
                        page_number_runs=page_runs,
                        page_number_paragraphs=page_paras,
                    )
                )

        sections.append(
            Section(
                index=index,
                type=(typ.get(w("val")) if typ is not None else None) or "nextPage",
                orientation="landscape" if size.get("orient") == "landscape" else "portrait",
                width_pt=_pt(size.get("w")),
                height_pt=_pt(size.get("h")),
                top_pt=_pt(margin.get("top")),
                bottom_pt=_pt(margin.get("bottom")),
                left_pt=_pt(margin.get("left")),
                right_pt=_pt(margin.get("right")),
                header_pt=_pt(margin.get("header")),
                footer_pt=_pt(margin.get("footer")),
                page_number_format=pgnum.get(w("fmt")) if pgnum is not None else None,
                different_first_page=sect.find(w("titlePg")) is not None,
                odd_and_even_pages=even_odd,
                headers=tuple(groups["header"]),
                footers=tuple(groups["footer"]),
                xml=sect,
            )
        )
    return tuple(sections)
