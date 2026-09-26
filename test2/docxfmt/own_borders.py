"""自研侧：表格边框的**有效值**（先算级联，再给单元格四边"有没有线"）。

优先级按规则的判定口径：单元格直接 `tcPr/tcBorders` → 表 `tblPr/tblBorders` → 表格样式
`w:tblStyle` 的 `tblPr/tblBorders`。表格样式的**条件格式**（`tblStylePr`）自研认，
但 **WPS 不认**（实测），所以语料里靠表样式做三线表的表会与 WPS 不一致，已记入 README。

采样口径与 `wps_borders.py` 对齐：**前 2 行 × 前 3 列**。

    python -m docxfmt.own_borders [docx ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

from .common import OUT, corpus, w, write_json
from .own import ZIP_DOC, OwnDoc

EDGES = ("top", "left", "bottom", "right")
NO_LINE = ("none", "nil")


def _edge(el):
    """`w:top` 这类元素 → 有没有线。元素存在且 val 不是 none/nil 就是有线。"""
    if el is None:
        return None
    v = el.get(w("val"))
    return v is None or v not in NO_LINE


class BorderDoc:
    def __init__(self, path: Path):
        self.doc = OwnDoc(path)
        self.body = etree.fromstring(self.doc.z.read(ZIP_DOC)).find(w("body"))
        self.styles: dict = {}
        raw = self.doc._read("word/styles.xml")
        if raw:
            for s in etree.fromstring(raw).iter(w("style")):
                self.styles[s.get(w("styleId"))] = s

    def _style_borders(self, tbl) -> dict:
        """表格样式（含 basedOn 链）的 tblBorders，低层先入、高层覆盖。"""
        out: dict = {}
        pr = tbl.find(w("tblPr"))
        st = pr.find(w("tblStyle")) if pr is not None else None
        sid = st.get(w("val")) if st is not None else None
        chain, seen = [], set()
        while sid and sid not in seen:
            seen.add(sid)
            style = self.styles.get(sid)
            if style is None:
                break
            chain.append(style)
            b = style.find(w("basedOn"))
            sid = b.get(w("val")) if b is not None else None
        for style in reversed(chain):        # 祖先 → 自身
            el = style.find(w("tblPr"))
            b = el.find(w("tblBorders")) if el is not None else None
            if b is not None:
                for e in EDGES + ("insideH", "insideV"):
                    v = _edge(b.find(w(e)))
                    if v is not None:
                        out[e] = v
        return out

    def _table_borders(self, tbl) -> tuple[dict, dict]:
        """→ (表级有效值, 仅样式值)。"""
        pr = tbl.find(w("tblPr"))
        b = pr.find(w("tblBorders")) if pr is not None else None
        style = self._style_borders(tbl)
        out = dict(style)                    # 样式是底
        if b is not None:                    # 表直接写的高于样式
            for e in EDGES + ("insideH", "insideV"):
                v = _edge(b.find(w(e)))
                if v is not None:
                    out[e] = v
        return out, style

    def _cell_edges(self, tc, tbl_base: dict, r: int, c: int, nrows: int, ncols: int) -> dict:
        """单元格四边 = 单元格直接写的 `tcBorders`，否则按**位置**取表级的对应边：

        * 上：首行取表 `top`，其余取表 `insideH`
        * 下：末行取表 `bottom`，其余取表 `insideH`
        * 左：首列取表 `left`，其余取表 `insideV`
        * 右：末列取表 `right`，其余取表 `insideV`

        （这是 `Cell.Borders` 的语义：表级边框按内外位置落到单元格上。实测「直接继承表级同名边」
        在 bottom 上只有 64% 一致，按位置映射才对得上。）
        """
        pos = {
            "top": "top" if r == 1 else "insideH",
            "bottom": "bottom" if r == nrows else "insideH",
            "left": "left" if c == 1 else "insideV",
            "right": "right" if c == ncols else "insideV",
        }
        pr = tc.find(w("tcPr"))
        b = pr.find(w("tcBorders")) if pr is not None else None
        out = {}
        for e in EDGES:
            v = _edge(b.find(w(e))) if b is not None else None
            out[e] = bool(tbl_base.get(pos[e], False)) if v is None else v
            out["direct_" + e] = bool(v)
        return out

    def tables(self) -> list[dict]:
        out = []
        # 只数**顶层**表格（嵌套表格不单独计，实测 WPS 只给顶层，6 vs 5）
        top = [t for t in self.body.iter(w("tbl"))
               if not any(a.tag == w("tbl") for a in t.iterancestors())]
        for i, tbl in enumerate(top, 1):
            rows = tbl.findall(w("tr"))
            base, _style_base = self._table_borders(tbl)
            ncols = max((len(r.findall(w("tc"))) for r in rows), default=0)
            sr, sc = min(2, len(rows)), min(3, ncols)
            cells = []
            for r, tr in enumerate(rows[:sr], 1):
                for c, tc in enumerate(tr.findall(w("tc"))[:sc], 1):
                    cells.append({"r": r, "c": c,
                                  "edges": self._cell_edges(tc, base, r, c, len(rows), ncols)})
            out.append({"i": i, "rows": len(rows),
                        "cols": max((len(r.findall(w("tc"))) for r in rows), default=0),
                        "edges": {e: base.get(e) for e in EDGES + ("insideH", "insideV")},
                        "cells": cells})
        return out

    def dump(self) -> dict:
        t = self.tables()
        return {"path": str(self.doc.path), "tool": "own",
                "counts": {"tables": len(t), "sample": "前2行x前3列"},
                "tables": t}


def dump(path) -> dict:
    return BorderDoc(Path(path)).dump()


def main() -> None:
    args = sys.argv[1:] or [str(p) for p in corpus()]
    for arg in args:
        p = Path(arg)
        data = dump(p)
        write_json(OUT / f"{p.stem}.ownborders.json", data)
        print(f"own_borders: {p.name}  {data['counts']['tables']} 表")


if __name__ == "__main__":
    main()
