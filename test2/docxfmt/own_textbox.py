"""自研侧：文本框内容（`w:txbxContent`）。

自研的**正文口径不下钻文本框**，这是单独一路，供 `GLB-28`（正文 / 表格 / **文本框**都要查）
与文本框内容核对使用。

    python -m docxfmt.own_textbox [docx ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

from .common import OUT, corpus, w, write_json
from .own import ZIP_DOC, OwnDoc, _in_fallback, iter_paragraphs


def _host_para(txbx, index: dict):
    """文本框的宿主段落：最近的 `w:p` 祖先（浮动文本框锚定在它上面）。"""
    a = txbx.getparent()
    while a is not None and a.tag != w("p"):
        a = a.getparent()
    return index.get(id(a)) if a is not None else None


def _samples(rec: dict) -> dict:
    """与 WPS 侧同口径：中文字体/字号优先取第一个中文字所在 run，没有则取第一个 ASCII 的。"""
    def first(kind, key):
        for r in rec["runs"]:
            t = r["text"]
            if kind == "east" and any("\u4e00" <= c <= "\u9fff" for c in t):
                return r.get(key)
            if kind == "west" and any(c.isascii() and c.isalnum() for c in t):
                return r.get(key)
        return None

    ea, west = first("east", "ea"), first("west", "ascii")
    return {"text": rec["text"], "font_ea": ea, "font_ascii": west,
            "size": first("east", "size") or first("west", "size"),
            "align": rec["align"], "list_type": rec["num_id"]}


def boxes(path) -> dict:
    doc = OwnDoc(path)
    body = etree.fromstring(doc.z.read(ZIP_DOC)).find(w("body"))
    paras = iter_paragraphs(body)
    index = {id(p): i for i, (p, _, _) in enumerate(paras)}

    out = []
    for n, txbx in enumerate(body.iter(w("txbxContent")), 1):
        # mc:AlternateContent 会把同一个文本框写成 DrawingML(Choice) + VML(Fallback) 两份，
        # Fallback 那份要跳过（实测 校园便利店 2 vs 1 就是这个）
        if _in_fallback(txbx, body):
            continue
        inner = [p for p, _, _ in iter_paragraphs(txbx)]
        recs = [doc.para_record(p, "textbox", i) for i, p in enumerate(inner)]
        out.append({
            "i": n,
            "anchor_para": _host_para(txbx, index),
            "text": "".join(r["text"] for r in recs),
            "paragraphs": [_samples(r) for r in recs],
        })
    with_text = sum(1 for b in out if b["text"].strip())
    return {"path": str(doc.path), "tool": "own",
            "counts": {"boxes": len(out), "boxes_with_text": with_text},
            "boxes": out}


def dump(path) -> dict:
    return boxes(Path(path))


def main() -> None:
    args = sys.argv[1:] or [str(p) for p in corpus()]
    for arg in args:
        p = Path(arg)
        data = dump(p)
        write_json(OUT / f"{p.stem}.owntextbox.json", data)
        print(f"own_textbox: {p.name}  {data['counts']['boxes']} 框")


if __name__ == "__main__":
    main()
