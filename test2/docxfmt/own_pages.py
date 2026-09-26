"""自研侧：页面设置 / 分节 / 页眉页脚，形状与 `wps_pages.py` 对齐（单位 pt）。

分节语义：**body 级的 `w:sectPr` 是最后一节**；每个 `w:pPr/w:sectPr` 结束它所在的那一节。
所以按文档顺序 = [各段落级 sectPr …] + [body 级 sectPr]。

页眉页脚按节继承：本节没引用该类型，就沿用上一节生效的那个部件（WPS 报的也是生效后的内容）。

    python -m docxfmt.own_pages [docx ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

from .common import OUT, corpus, local_attrs, w, write_json
from .own import ZIP_DOC, OwnDoc, iter_paragraphs, para_text


def _in_txbx(el, root) -> bool:
    anc = el.getparent()
    while anc is not None and anc is not root:
        if anc.tag == w("txbxContent"):
            return True
        anc = anc.getparent()
    return False

RELS = "word/_rels/document.xml.rels"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# w:pgNumType/@fmt → wdPageNumberStyle（WPS 侧报整数）
PGNUM = {"decimal": 0, "upperRoman": 1, "lowerRoman": 2, "upperLetter": 3,
         "lowerLetter": 4, "ordinal": 5, "cardinalText": 6, "ordinalText": 7,
         "hex": 8, "chicago": 9}


def _pt(v) -> float | None:
    return None if v is None else round(float(v) / 20.0, 2)


class PagesDoc:
    def __init__(self, path: Path):
        self.doc = OwnDoc(path)
        self.z = self.doc.z
        self.rels = self._rels()

    def _rels(self) -> dict[str, str]:
        out: dict[str, str] = {}
        raw = self.doc._read(RELS)
        if not raw:
            return out
        for rel in etree.fromstring(raw):
            target = (rel.get("Target") or "").lstrip("/")
            out[rel.get("Id")] = target if target.startswith("word/") else "word/" + target
        return out

    def _one_hf(self, kind: str, typ: str, has_ref: bool, part: str | None) -> dict:
        rec = {"type": typ, "text": None, "paragraphs": [],
               "has_reference": has_ref, "part": part, "page_fields": 0}
        if part and part in self.z.namelist():
            root = etree.fromstring(self.z.read(part))
            # 文本框不下钻：与主对账、与 WPS 的 Range 语义都一致（WPS 不数图形内的域）
            paras = iter_paragraphs(root)
            rec["text"] = "".join(para_text(p) for p, _, _ in paras)
            rec["paragraphs"] = [self.doc.para_record(p, kind, i, intbl, rowend)
                                 for i, (p, intbl, rowend) in enumerate(paras)]
            # PAGE 域两种写法都要数：w:fldChar+w:instrText 与 w:fldSimple
            rec["page_fields"] = (
                sum(1 for t in root.iter(w("instrText"))
                    if (t.text or "").strip().startswith("PAGE") and not _in_txbx(t, root))
                + sum(1 for f in root.iter(w("fldSimple"))
                      if (f.get(w("instr")) or "").strip().startswith("PAGE")
                      and not _in_txbx(f, root))
            )
        return rec

    def sections(self) -> list[dict]:
        body = etree.fromstring(self.z.read(ZIP_DOC)).find(w("body"))
        sects: list = []
        for p in body.iter(w("p")):
            ppr = p.find(w("pPr"))
            if ppr is not None and ppr.find(w("sectPr")) is not None:
                sects.append(ppr.find(w("sectPr")))
        body_sect = body.find(w("sectPr"))
        if body_sect is not None:
            sects.append(body_sect)

        even_odd = False
        settings = self.doc._read("word/settings.xml")
        if settings:
            even_odd = etree.fromstring(settings).find(w("evenAndOddHeaders")) is not None

        carried: dict[tuple[str, str], str | None] = {}
        out = []
        for i, sect in enumerate(sects, 1):
            sz = local_attrs(sect.find(w("pgSz"))) if sect.find(w("pgSz")) is not None else {}
            mar = local_attrs(sect.find(w("pgMar"))) if sect.find(w("pgMar")) is not None else {}
            typ = sect.find(w("type"))
            pgnum = sect.find(w("pgNumType"))
            fmt = pgnum.get(w("fmt")) if pgnum is not None else None

            groups = {}
            for kind in ("header", "footer"):
                recs = []
                for t in ("default", "first", "even"):
                    ref = next((e for e in sect.findall(w(kind + "Reference"))
                                if e.get(w("type"), "default") == t), None)
                    if ref is not None:
                        part = self.rels.get(ref.get(f"{{{R}}}id"))
                        carried[(kind, t)] = part if part in self.z.namelist() else None
                    recs.append(self._one_hf(kind, t, ref is not None, carried.get((kind, t))))
                groups[kind] = recs

            out.append({
                "index": i,
                "type": (typ.get(w("val")) if typ is not None else None) or "nextPage",
                "page": {
                    "w_pt": _pt(sz.get("w")), "h_pt": _pt(sz.get("h")),
                    "orientation": "landscape" if sz.get("orient") == "landscape" else "portrait",
                    "top_pt": _pt(mar.get("top")), "bottom_pt": _pt(mar.get("bottom")),
                    "left_pt": _pt(mar.get("left")), "right_pt": _pt(mar.get("right")),
                    "header_pt": _pt(mar.get("header")), "footer_pt": _pt(mar.get("footer")),
                    "paper_size": None,
                },
                "page_number_format": (PGNUM.get(fmt) if fmt else 0),
                "page_number_fmt_name": fmt,
                "different_first_page": sect.find(w("titlePg")) is not None,
                "odd_and_even_pages": even_odd,
                "headers": groups["header"],
                "footers": groups["footer"],
            })
        return out

    def dump(self) -> dict:
        return {"path": str(self.doc.path), "tool": "own", "sections": self.sections()}


def dump(path) -> dict:
    return PagesDoc(Path(path)).dump()


def main() -> None:
    args = sys.argv[1:] or [str(p) for p in corpus()]
    for arg in args:
        p = Path(arg)
        data = dump(p)
        write_json(OUT / f"{p.stem}.ownpages.json", data)
        print(f"own_pages: {p.name}  {len(data['sections'])} 节")


if __name__ == "__main__":
    main()
