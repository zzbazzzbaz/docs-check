"""查一个段落为什么两边算得不一样：把自研记录、WPS 记录、原始 XML 摆在一起。

    python -m docxfmt.why <docx> <文本片段> [最多打印几段，默认 2]
"""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

from . import own as ownmod
from .common import OUT, local_attrs, norm_text, read_json, w


def compact(el, depth: int = 0) -> str:
    if el is None:
        return "(无)"
    tag = el.tag.split("}")[-1]
    attrs = " ".join(f"{k}={v}" for k, v in local_attrs(el).items())
    kids = [c for c in el if isinstance(c.tag, str)]
    if depth >= 3 or not kids:
        return f"{tag}[{attrs}]"
    inner = " ".join(compact(c, depth + 1) for c in kids)
    return f"{tag}[{attrs}]{{{inner}}}"


def show_styles(doc, style_id: str) -> None:
    by_id = doc.styles.by_id
    for s in doc.styles.chain(style_id):
        star = " ←" if s.id == style_id else ""
        print(f"  样式 {s.id}/{s.name}{star}")
        print(f"      pPr: {compact(s.pPr)}")
        print(f"      rPr: {compact(s.rPr)}")
    if style_id not in by_id:
        print(f"  (样式表里没有 {style_id})")


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        return
    path = Path(sys.argv[1])
    frag = sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    doc = ownmod.OwnDoc(path)
    ownj = read_json(OUT / f"{path.stem}.own.json")
    wpsf = OUT / f"{path.stem}.wps.json"
    wpsj = read_json(wpsf) if wpsf.exists() else {"paragraphs": []}

    body = etree.fromstring(doc.z.read(ownmod.ZIP_DOC))
    nodes = ownmod.iter_paragraphs(body.find(w("body")))

    hits = [r for r in ownj["paragraphs"]
            if r["story"] == "main" and frag in r["text"]][:limit]
    if not hits:
        print("自研记录里没找到含", repr(frag), "的正文段落")
        return

    for rec in hits:
        print("=" * 78)
        print(f"[自研] {rec['text'][:60]!r}")
        print(f"   style={rec['style_id']}/{rec['style_name']} align={rec['align']!r} "
              f"outline={rec['outline']} line={rec['line']}{rec['line_rule'] or ''}")
        print(f"   缩进 首行={rec['ind_first']} 左={rec['ind_left']} 右={rec['ind_right']} "
              f"段前={rec['sp_before']} 段后={rec['sp_after']}")
        for r in rec["runs"]:
            if not r["text"]:
                continue
            print(f"   run {r['text'][:24]!r} ascii={r['ascii']!r} ea={r['ea']!r} "
                  f"size={r['size']} b={r['bold']}")

        t = norm_text(rec["text"])
        wrow = next((r for r in wpsj["paragraphs"] if norm_text(r["text"]) == t), None)
        if wrow is None:
            print("[WPS ] 没配上（可能文本被截断 / 未参与比对）")
        else:
            print(f"[WPS ] i={wrow['i']} align={wrow['align']!r} outline={wrow['outline']} "
                  f"line={wrow['line']}{wrow['line_rule'] or ''}")
            print(f"   缩进 首行={wrow['first_indent']} 左={wrow['left_indent']} "
                  f"右={wrow['right_indent']} 段前={wrow['space_before']} 段后={wrow['space_after']}")
            print(f"   west={wrow['west']}")
            print(f"   east={wrow['east']}")

        p = nodes[rec["ordinal"]]
        print("[XML  ] docDefaults.rPr :", compact(doc.styles.dd_rPr))
        print(f"[XML  ] 段落 pPr        : {compact(p.find(w('pPr')))}")
        for r in p.findall(w("r")):
            txt = "".join(x.text or "" for x in r.iter(w("t")))
            extra = "fldChar" if r.find(w("fldChar")) is not None else (
                "instrText" if r.find(w("instrText")) is not None else "")
            print(f"[XML  ]   run rPr: {compact(r.find(w('rPr')))}  <{extra}> t={txt[:24]!r}")
        show_styles(doc, rec["style_id"])
        print("[XML  ] 主题字体:", doc.theme.slot)


if __name__ == "__main__":
    main()
