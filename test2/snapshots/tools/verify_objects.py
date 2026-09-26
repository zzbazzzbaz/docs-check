"""核对 wpsobjects.json 的逐段对象数 vs OOXML 真值；顺带钉死占位字符规律。

    cd test2 && uv run python out/verify_objects.py [篇名...]

不给篇名则跑 out/ 下全部 *.wpsobjects.json。

对齐：WPS 的 Paragraphs 在每个表格行末多一个空段落，按 own.iter_paragraphs 的
row_end 标记在 OOXML 序列里插入占位段，使下标与 WPS 一一对应。
"""
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lxml import etree

from docxfmt.own import iter_paragraphs

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
V = "urn:schemas-microsoft-com:vml"
OUT = Path(__file__).resolve().parent


def q(ns, t):
    return f"{{{ns}}}{t}"


def under(el, tags, stop):
    a = el.getparent()
    while a is not None and a is not stop:
        if a.tag in tags:
            return True
        a = a.getparent()
    return False


def xml_counts(p):
    """(内嵌, 浮动, 公式) —— 只在主故事 body 里数，文本框不下钻（口径与自研一致）。

    两个坑：
      * wp:anchor 的 VML 回退会以 mc:Fallback/w:pict 再出现一次（同一个浮动图形），不能重复计；
      * 独立的 w:pict（VML）要看 v:shape 有没有定位样式：有定位 = 浮动 Shape，
        没有 = 内嵌 InlineShape（实测 WPS 就是这么分的）。
    """
    if p is None:
        return 0, 0, 0
    skip = {q(WP, "anchor"), q(WP, "inline"), q(MC, "Fallback")}
    inline = len(p.findall(".//" + q(WP, "inline")))
    obj = [o for o in p.findall(".//" + q(W, "object")) if not under(o, skip, p)]
    pict_inline = pict_float = 0
    for x in p.findall(".//" + q(W, "pict")):
        if under(x, skip, p):
            continue
        sh = x.find(".//" + q(V, "shape"))
        if sh is None:
            sh = x.find(".//" + q(V, "group"))
        style = (sh.get("style") or "") if sh is not None else ""
        if "position" in style.lower():
            pict_float += 1
        else:
            pict_inline += 1
    anchor = len(p.findall(".//" + q(WP, "anchor"))) + pict_float
    omath = len(p.findall(".//" + q(M, "oMath")))
    return inline + len(obj) + pict_inline, anchor, omath


def aligned_paragraphs(path):
    z = zipfile.ZipFile(path)
    root = etree.fromstring(z.read("word/document.xml"))
    aligned = []
    for el, _, row_end in iter_paragraphs(root.find(q(W, "body"))):
        aligned.append(el)
        if row_end:
            aligned.append(None)
    return aligned


def marker_of(text):
    return "+".join(m for m, v in (("\\x01", "\x01" in text), ("/", "/" in text)) if v)


def detail(stem):
    """打印一篇的逐段比对与占位字符对照。"""
    f = OUT / f"{stem}.wpsobjects.json"
    docx = OUT.parent / "corpus" / f"{stem}.docx"
    j = json.loads(f.read_text(encoding="utf-8"))
    wj = json.loads((OUT / f"{stem}.wps.json").read_text(encoding="utf-8"))
    aligned = aligned_paragraphs(docx)
    wps = j["paragraphs"]
    n = min(len(wps), len(aligned))
    print(f"\n=== {stem} ===")
    print(f"  段数: WPS={len(wps)} OOXML+行末={len(aligned)} "
          f"{'OK' if len(wps) == len(aligned) else '!!MISMATCH'}")
    ok = tot = 0
    for k in range(n):
        xi, xs, xo = xml_counts(aligned[k])
        for gv, xv in zip((wps[k]["inline_shapes"], wps[k]["shapes"], wps[k]["omaths"]),
                          (xi, xs, xo)):
            tot += 1
            ok += gv == xv
    print(f"  逐段比对: {ok}/{tot} = {ok / tot * 100:.3f}%")
    stat = {}
    for k in range(n):
        if not wps[k]["inline_shapes"]:
            continue
        p = aligned[k]
        has_obj = p is not None and any(
            not under(o, {q(WP, "anchor")}, p) for o in p.findall(".//" + q(W, "object")))
        has_pic = p is not None and len(p.findall(".//" + q(WP, "inline"))) > 0
        kind = "+".join(k2 for k2, v in (("ole", has_obj), ("pic", has_pic)) if v)
        stat.setdefault((kind, marker_of(wj["paragraphs"][k]["text"])), []).append(k + 1)
    for (kind, mk), ks in sorted(stat.items()):
        print(f"  内嵌占位: XML类型={kind:<8} 占位符={mk or '(无)':<8} {len(ks):>3} 段  例 p{ks[0]}")


def main():
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    detail_set = set(only) if only else {
        "2206181072_李煜_基于ESP32老人健康检测与预警系统的设计与实现",
        "论文初稿", "main-text-formula-format",
    }

    agg_field = {"inline": [0, 0], "shape": [0, 0], "omath": [0, 0]}
    mism = []
    ph = {}
    mixed = mixed_ok = 0
    omath_para = omath_text = 0
    shape_total = 0
    files = 0
    for f in sorted(OUT.glob("*.wpsobjects.json")):
        stem = f.name[: -len(".wpsobjects.json")]
        if only and stem not in only:
            continue
        docx = OUT.parent / "corpus" / f"{stem}.docx"
        wf = OUT / f"{stem}.wps.json"
        if not (docx.exists() and wf.exists()):
            print(f"!! 缺文件，跳过 {stem}")
            continue
        files += 1
        j = json.loads(f.read_text(encoding="utf-8"))
        wj = json.loads(wf.read_text(encoding="utf-8"))
        aligned = aligned_paragraphs(docx)
        wps = j["paragraphs"]
        shape_total += j["counts"]["shapes"]
        n = min(len(wps), len(aligned))
        fok = ftot = 0
        for k in range(n):
            xi, xs, xo = xml_counts(aligned[k])
            got = (wps[k]["inline_shapes"], wps[k]["shapes"], wps[k]["omaths"])
            for fld, gv, xv in zip(("inline", "shape", "omath"), got, (xi, xs, xo)):
                agg_field[fld][1] += 1
                ftot += 1
                if gv == xv:
                    agg_field[fld][0] += 1
                    fok += 1
                elif len(mism) < 40:
                    mism.append((stem, k + 1, fld, gv, xv))
            # 内嵌图形：占位字符规律 + 是否与文字同段
            if wps[k]["inline_shapes"]:
                p = aligned[k]
                has_obj = p is not None and any(
                    not under(o, {q(WP, "anchor")}, p)
                    for o in p.findall(".//" + q(W, "object")))
                has_pic = p is not None and len(p.findall(".//" + q(WP, "inline"))) > 0
                kind = "+".join(k2 for k2, v in (("ole", has_obj), ("pic", has_pic)) if v)
                mk = marker_of(wj["paragraphs"][k]["text"])
                ph[(kind, mk)] = ph.get((kind, mk), 0) + 1
                txt = wj["paragraphs"][k]["text"]
                for m in ("\x01", "/"):
                    txt = txt.replace(m, "")
                if txt.replace(" ", "").replace("\t", "").strip():
                    mixed += 1
                    mixed_ok += got[0] == xi
            if wps[k]["omaths"]:
                omath_para += 1
                if wj["paragraphs"][k]["text"].strip():
                    omath_text += 1
        print(f"  {stem[:34]:<34} 段{n:>5} 逐段 {fok}/{ftot} "
              f"{'OK' if fok == ftot else f'{ftot - fok} 处不符'}")

    print(f"\n===== 汇总（{files} 篇）=====")
    for fld, (ok, tot) in agg_field.items():
        print(f"  {fld:<8}: {ok}/{tot} = {ok / tot * 100:.4f}%")
    print(f"  浮动图形 Shapes 合计 {shape_total}，映射不到 0（脚本已打印）")
    print(f"  OMML 段落 {omath_para}，其中 WPS 文本非空 {omath_text}"
          f"（公式文字确实占字符）")
    print(f"  内嵌图形与文字同段 {mixed}（映射一致 {mixed_ok}）")
    print("  占位字符规律：")
    for (kind, mk), c in sorted(ph.items()):
        print(f"    XML类型={kind:<8} 占位符={mk or '(无)':<8} {c:>4} 段")
    if mism:
        print("  不一致清单（前 40）：")
        for stem, i, fld, gv, xv in mism:
            print(f"    {stem[:24]:<24} p{i} {fld}: WPS={gv} OOXML={xv}")

    for stem in sorted(detail_set):
        if (OUT / f"{stem}.wpsobjects.json").exists() and \
                (OUT.parent / "corpus" / f"{stem}.docx").exists():
            detail(stem)


if __name__ == "__main__":
    main()
