"""核对 wpsfields.json 的域列表 vs OOXML 真值（fldChar/instrText/fldSimple + w:object）。

    cd test2 && uv run python out/verify_fields.py [篇名...]

对齐：WPS 的 Paragraphs 在每个表格行末多一个空段落，用 own.iter_paragraphs 的
row_end 标记插入占位段，使下标与 WPS 一一对应。文本框不下钻（与 WPS doc.Fields 一致）。

已知差异（脚本会单列）：OOXML 没有为 OLE 对象写 fldChar，WPS 会给每个 w:object
合成一个 EMBED 域。这里把 w:object 也当成 EMBED 域参与比对。
"""
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lxml import etree

from docxfmt.own import iter_paragraphs

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
V = "urn:schemas-microsoft-com:vml"
OUT = Path(__file__).resolve().parent


def w(t):
    return f"{{{W}}}{t}"


def first_word(text):
    toks = (text or "").strip().split()
    return toks[0].upper() if toks else None


def aligned_paragraphs(root):
    aligned = []
    for el, _, row_end in iter_paragraphs(root.find(w("body"))):
        aligned.append(el)
        if row_end:
            aligned.append(None)
    return aligned


# 结果里有这些元素就算“这一段是域结果”——用来定 end_para（域结果最后一字的段落）。
_RESULT_TAGS = ("t", "tab", "br", "cr", "noBreakHyphen", "softHyphen",
                "drawing", "pict", "object", "sym", "footnoteReference",
                "endnoteReference", "commentReference")
_RESULT = {w(t) for t in _RESULT_TAGS}


def _in_txbx(el, stop):
    a = el.getparent()
    while a is not None and a is not stop:
        if a.tag == w("txbxContent"):
            return True
        a = a.getparent()
    return False


def _shape_anchor(el, stop):
    """文本框是否算 WPS 的 SHAPE 域（实测）：
    legacy VML 文本框（w:pict 下的 v:textbox）、样式不是 position:absolute（即**内联**），
    且不在 mc:Fallback 里。浮动的文本框（DrawingML wp:anchor 或 position:absolute）不算，
    它们进 doc.Shapes 而不是 doc.Fields。"""
    in_pict = in_fb = floating = False
    a = el.getparent()
    while a is not None and a is not stop:
        if a.tag == w("pict"):
            in_pict = True
        if a.tag == f"{{{MC}}}Fallback":
            in_fb = True
        if a.tag in (f"{{{V}}}shape", f"{{{V}}}rect", f"{{{V}}}group"):
            # 最外层 VML 容器的样式说了算（组内子形状可能写 absolute，但组本身是内联）
            floating = "position:absolute" in (a.get("style") or "")
        a = a.getparent()
    return in_pict and not in_fb and not floating


def ooxml_fields(docx):
    """OOXML 正文域，按“域起点”的文档顺序返回 [{code, code_text, para, end_para}]。

    除 fldChar/instrText/fldSimple 外，还要补三类 WPS 会算成域、OOXML 却没有域标记的东西：
      * w:object（OLE 对象）→ WPS 合成 EMBED 域；
      * 正文里的 w:hyperlink（结构超链接）→ WPS 合成 HYPERLINK 域；
      * 正文里的 w:txbxContent（文本框/形状锚点）→ WPS 合成 SHAPE 域。
    文本框**内部**的域不算（WPS 不算，与「文本框不下钻」一致）。

    end_para 取域结果最后一字的段落；否则退化成 end fldChar 所在的段落（TOC 的
    end fldChar 会落在目录后一段，直接用会多 1 段）。
    """
    z = zipfile.ZipFile(docx)
    root = etree.fromstring(z.read("word/document.xml"))
    aligned = aligned_paragraphs(root)
    fields, stack, order = [], [], 0
    for idx, p in enumerate(aligned):
        if p is None:
            continue
        for el in p.iter():
            tag = el.tag
            if tag == w("txbxContent"):
                if _shape_anchor(el, p):
                    order += 1
                    fields.append({"order": order, "code": "SHAPE", "code_text": None,
                                   "para": idx + 1, "end_para": idx + 1})
                continue
            if _in_txbx(el, p):
                continue
            if tag in _RESULT:
                for rec in stack:
                    rec["last"] = idx + 1
            if tag == w("fldSimple"):
                order += 1
                instr = el.get(w("instr")) or ""
                fields.append({"order": order, "code": first_word(instr),
                               "code_text": instr.strip(), "para": idx + 1,
                               "end_para": idx + 1})
            elif tag == w("fldChar"):
                kind = el.get(w("fldCharType"))
                if kind == "begin":
                    order += 1
                    stack.append({"order": order, "parts": [], "para": idx + 1,
                                  "last": None})
                elif kind == "end" and stack:
                    rec = stack.pop()
                    txt = "".join(rec["parts"]).strip()
                    fields.append({"order": rec["order"], "code": first_word(txt),
                                   "code_text": txt, "para": rec["para"],
                                   "end_para": rec["last"] or rec["para"]})
            elif tag == w("instrText") and stack:
                stack[-1]["parts"].append(el.text or "")
            elif tag == w("object"):
                order += 1
                fields.append({"order": order, "code": "EMBED", "code_text": None,
                               "para": idx + 1, "end_para": idx + 1})
            elif tag == w("hyperlink"):
                order += 1
                fields.append({"order": order, "code": "HYPERLINK", "code_text": None,
                               "para": idx + 1, "end_para": idx + 1})
    fields.sort(key=lambda r: r["order"])
    return fields


def by_code(rows):
    d = {}
    for r in rows:
        d[r["code"]] = d.get(r["code"], 0) + 1
    return d


def detail(stem):
    f = OUT / f"{stem}.wpsfields.json"
    docx = OUT.parent / "corpus" / f"{stem}.docx"
    j = json.loads(f.read_text(encoding="utf-8"))
    xs = ooxml_fields(docx)
    ws = j["fields"]
    print(f"\n=== {stem} ===")
    print(f"  域数: WPS={len(ws)} OOXML={len(xs)} "
          f"{'OK' if len(ws) == len(xs) else '!!MISMATCH'}")
    print(f"  WPS  by_code: {j['counts']['by_code']}")
    print(f"  OOXML by_code: {by_code(xs)}")
    print(f"  WPS  toc_spans: {j['toc_spans']}")
    toc = [(r["para"], r["end_para"]) for r in xs if r["code"] == "TOC"]
    print(f"  OOXML TOC 跨度: {toc}")
    for k in range(max(len(ws), len(xs))):
        wv = ws[k] if k < len(ws) else None
        xv = xs[k] if k < len(xs) else None
        line = f"    #{k + 1:>3}"
        if wv and xv and wv["code"] == xv["code"] and wv["para"] == xv["para"]:
            continue
        print(f"{line} WPS={wv and (wv['code'], wv['para'], wv['end_para'])}"
              f" OOXML={xv and (xv['code'], xv['para'], xv['end_para'])}")


def main():
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    agg = {"n": 0, "code_ok": 0, "para_ok": 0, "endpara_ok": 0, "total": 0}
    mism = []
    typemap = {}
    obj_total = 0
    files = 0
    for f in sorted(OUT.glob("*.wpsfields.json")):
        stem = f.name[: -len(".wpsfields.json")]
        if only and stem not in only:
            continue
        docx = OUT.parent / "corpus" / f"{stem}.docx"
        if not docx.exists():
            print(f"!! 缺 docx，跳过 {stem}")
            continue
        files += 1
        j = json.loads(f.read_text(encoding="utf-8"))
        xs = ooxml_fields(docx)
        ws = j["fields"]
        obj_total += sum(1 for x in xs if x["code"] == "EMBED")
        for r in ws:
            typemap.setdefault((r["code"], r["type"]), 0)
            typemap[(r["code"], r["type"])] += 1
        n = min(len(ws), len(xs))
        f_code = f_para = f_end = 0
        for k in range(n):
            f_code += ws[k]["code"] == xs[k]["code"]
            f_para += ws[k]["para"] == xs[k]["para"]
            f_end += ws[k]["end_para"] == xs[k]["end_para"]
        agg["n"] += len(ws)
        agg["total"] += max(len(ws), len(xs))
        agg["code_ok"] += f_code
        agg["para_ok"] += f_para
        agg["endpara_ok"] += f_end
        if len(ws) != len(xs) or f_code != n or f_para != n or f_end != n:
            mism.append((stem, len(ws), len(xs), n, f_code, f_para, f_end))
        print(f"  {stem[:38]:<38} WPS={len(ws):>3} OOXML={len(xs):>3} "
              f"code {f_code}/{n} para {f_para}/{n} end {f_end}/{n}")

    print(f"\n===== 汇总（{files} 篇）=====")
    print(f"  域总数 WPS={agg['n']}  逐位对齐数={agg['total']}")
    print(f"  code 一致 {agg['code_ok']}/{agg['total']} = "
          f"{agg['code_ok'] / max(agg['total'], 1) * 100:.3f}%")
    print(f"  para 一致 {agg['para_ok']}/{agg['total']} = "
          f"{agg['para_ok'] / max(agg['total'], 1) * 100:.3f}%")
    print(f"  end_para 一致 {agg['endpara_ok']}/{agg['total']} = "
          f"{agg['endpara_ok'] / max(agg['total'], 1) * 100:.3f}%")
    print(f"  OLE→EMBED 共 {obj_total} 个")
    print("  code → type 映射表：")
    for (code, typ), c in sorted(typemap.items()):
        print(f"    {code:<16} → {typ:<4} n={c}")
    if mism:
        print("  不一致（总数列）：")
        for stem, lw, lx, n, fc, fp, fe in mism:
            print(f"    {stem[:34]:<34} WPS={lw} OOXML={lx} n={n} code={fc} para={fp} end={fe}")

    for stem in sorted(only):
        if (OUT / f"{stem}.wpsfields.json").exists() and \
                (OUT.parent / "corpus" / f"{stem}.docx").exists():
            detail(stem)


if __name__ == "__main__":
    main()
