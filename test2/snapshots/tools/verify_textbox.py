"""核对 wpstextbox.json vs OOXML `w:txbxContent` 直接解析结果。

    cd test2 && uv run python out/verify_textbox.py [篇名...]

不给篇名则跑 out/ 下全部 *.wpstextbox.json。
对齐：
  * OOXML 的框 = `w:txbxContent` 且不在 `mc:Fallback` 里（AlternateContent 的 VML 回退是同一个对象）。
  * 锚定段落：框外层最近的 `w:p`，在 iter_paragraphs（+ 行末占位）序列里的下标 +1 == WPS 段号。
"""
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lxml import etree

from docxfmt.own import iter_paragraphs, para_text

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
OUT = Path(__file__).resolve().parent


def q(t):
    return f"{{{W}}}{t}"


def under(el, tags, stop):
    a = el.getparent()
    while a is not None and a is not stop:
        if a.tag in tags:
            return True
        a = a.getparent()
    return False


def para_size(p):
    for r in p.iter(q("r")):
        sz = r.find(f'{q("rPr")}/{q("sz")}')
        if sz is not None and sz.get(q("val")):
            return int(sz.get(q("val"))) / 2.0
    for path in (f'{q("pPr")}/{q("rPr")}/{q("sz")}',):
        sz = p.find(path)
        if sz is not None and sz.get(q("val")):
            return int(sz.get(q("val"))) / 2.0
    return None


def para_fonts(p):
    ascii_ = ea = None
    for r in p.iter(q("r")):
        rf = r.find(f'{q("rPr")}/{q("rFonts")}')
        if rf is not None:
            ascii_ = ascii_ or rf.get(q("ascii"))
            ea = ea or rf.get(q("eastAsia"))
    if ascii_ is None and ea is None:
        rf = p.find(f'{q("pPr")}/{q("rPr")}/{q("rFonts")}')
        if rf is not None:
            ascii_ = rf.get(q("ascii"))
            ea = rf.get(q("eastAsia"))
    return ascii_, ea


def para_numbered(p):
    npr = p.find(f'{q("pPr")}/{q("numPr")}')
    if npr is None:
        return False
    num = npr.find(q("numId"))
    if num is None:
        return True
    return num.get(q("val")) not in (None, "0")


def box_paras(txbx):
    """文本框内的段落（不含更深层 txbxContent）。"""
    out = []
    for p in txbx.findall(f".//{q('p')}"):
        if under(p, {q("txbxContent")}, txbx):
            continue
        out.append(p)
    return out


def anchor_para(el, body):
    """框外层最近的 body 段落元素（不越过 txbxContent）。"""
    a = el.getparent()
    while a is not None:
        if a.tag == q("txbxContent"):
            return None
        if a.tag == q("p"):
            return a
        a = a.getparent()
    return None


def parse_ooxml(docx):
    z = zipfile.ZipFile(docx)
    root = etree.fromstring(z.read("word/document.xml"))
    body = root.find(q("body"))
    aligned = []
    for el, _, row_end in iter_paragraphs(body):
        aligned.append(el)
        if row_end:
            aligned.append(None)
    idx = {id(el): k for k, el in enumerate(aligned)}

    boxes = []
    for txbx in root.iter(q("txbxContent")):
        if under(txbx, {f"{{{MC}}}Fallback"}, root):
            continue
        a = anchor_para(txbx, body)
        paras = box_paras(txbx)
        boxes.append({
            "anchor": idx.get(id(a)) + 1 if a is not None and id(a) in idx else None,
            "paras": [para_text(p) for p in paras],
            "sizes": [para_size(p) for p in paras],
            "fonts": [para_fonts(p) for p in paras],
            "nums": [para_numbered(p) for p in paras],
        })
    return boxes


def resolve(docx_path):
    if docx_path.startswith("/in/"):
        return OUT.parent / "corpus" / docx_path[len("/in/"):]
    if docx_path.startswith("/out/"):
        return OUT / docx_path[len("/out/"):]
    return Path(docx_path)


def main():
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    agg = {"box": [0, 0], "para": [0, 0], "text": [0, 0], "size": [0, 0],
           "anchor": [0, 0]}
    mism = []
    files = 0
    for f in sorted(OUT.glob("*.wpstextbox.json")):
        stem = f.name[: -len(".wpstextbox.json")]
        if only and stem not in only:
            continue
        j = json.loads(f.read_text(encoding="utf-8"))
        docx = resolve(j["path"])
        if not docx.exists():
            print(f"!! 缺 docx，跳过 {stem}")
            continue
        files += 1
        ox = parse_ooxml(docx)
        wb = j["boxes"]

        agg["box"][0] += len(wb) == len(ox)
        agg["box"][1] += 1
        fok = ftot = 0

        # 按 anchor 分组配对（同 anchor 多框按出现次序）
        by_anchor = {}
        for b in ox:
            by_anchor.setdefault(b["anchor"], []).append(b)
        for b in wb:
            cand = by_anchor.get(b["anchor_para"])
            ob = cand.pop(0) if cand else None
            if ob is None:
                mism.append((stem, b["i"], "无对应 OOXML 框", f"anchor={b['anchor_para']}", ""))
                ftot += 1
                continue
            wparas = b["paragraphs"]
            ftot += 1
            if len(wparas) == len(ob["paras"]):
                fok += 1
                agg["para"][0] += 1
            else:
                mism.append((stem, b["i"], "段数", len(wparas), len(ob["paras"])))
            agg["para"][1] += 1

            wt = "".join(p["text"] for p in wparas)
            ot = "".join(ob["paras"])
            agg["text"][1] += 1
            if wt == ot:
                agg["text"][0] += 1
            else:
                mism.append((stem, b["i"], "文本", wt[:60], ot[:60]))

            for k, wp in enumerate(wparas):
                osz = ob["sizes"][k] if k < len(ob["sizes"]) else None
                wsz = wp["size"]
                if osz is None or wsz is None or wsz >= 9999999:
                    continue
                agg["size"][1] += 1
                if abs(osz - wsz) <= 0.5:
                    agg["size"][0] += 1
                else:
                    mism.append((stem, b["i"], f"字号 p{k + 1}", wsz, osz))
        # anchor 独立核对：按文本配对（不用 anchor），再看 anchor 是否一致
        used = set()
        for b in wb:
            wt = "".join(p["text"] for p in b["paragraphs"])
            for j, ob in enumerate(ox):
                if j not in used and "".join(ob["paras"]) == wt:
                    used.add(j)
                    agg["anchor"][1] += 1
                    if b["anchor_para"] == ob["anchor"]:
                        agg["anchor"][0] += 1
                    else:
                        mism.append((stem, b["i"], "anchor",
                                     b["anchor_para"], ob["anchor"]))
                    break
        print(f"  {stem[:40]:<40} WPS框{len(wb):>3} OOXML框{len(ox):>3} "
              f"{'OK' if len(wb) == len(ox) else '!!框数不符'}")

    print(f"\n===== 汇总（{files} 篇）=====")
    for k, (ok, tot) in agg.items():
        if tot:
            print(f"  {k:<6}: {ok}/{tot} = {ok / tot * 100:.2f}%")
    print(f"  不一致 {len(mism)} 条" + ("（前 30）" if mism else ""))
    for row in mism[:30]:
        print(f"    {row[0][:26]:<26} box{row[1]:<3} {row[2]}: WPS={row[3]!r} OOXML={row[4]!r}")


if __name__ == "__main__":
    main()
