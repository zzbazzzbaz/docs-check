"""核对 wpspages.json 与 OOXML 真值（页面/分节/布尔/页码格式）。"""
import json, re, sys, zipfile
from pathlib import Path
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
def q(t): return f"{{{W}}}{t}"

FMT2STYLE = {"decimal": 0, "upperRoman": 1, "lowerRoman": 2, "upperLetter": 3,
             "lowerLetter": 4, "chineseCounting": 37}

CASES = {
    "2206181072_李煜_基于ESP32老人健康检测与预警系统的设计与实现": "corpus/2206181072_李煜_基于ESP32老人健康检测与预警系统的设计与实现.docx",
    "global-header-format": "corpus/global-header-format.docx",
    "global-footer-page-number-format": "corpus/global-footer-page-number-format.docx",
    "论文2206181106_王雨诺_基于RAG技术的智能交互系统的设计与实现 - 副本": "corpus/论文2206181106_王雨诺_基于RAG技术的智能交互系统的设计与实现 - 副本.docx",
    "probe_pages_synth": "out/probe_pages_synth.docx",
}


def ooxml_sections(path):
    z = zipfile.ZipFile(path)
    root = etree.fromstring(z.read("word/document.xml"))
    body = root.find(q("body"))
    sects = []
    for p in body.iter(q("p")):
        ppr = p.find(q("pPr"))
        if ppr is not None and ppr.find(q("sectPr")) is not None:
            sects.append(ppr.find(q("sectPr")))
    for sp in body.findall(q("sectPr")):
        sects.append(sp)
    try:
        st = etree.fromstring(z.read("word/settings.xml"))
        even = st.find(q("evenAndOddHeaders")) is not None
    except KeyError:
        even = False
    return sects, even


def main():
    for stem, path in CASES.items():
        j = json.loads(Path(f"out/{stem}.wpspages.json").read_text(encoding="utf-8"))
        sects, even = ooxml_sections(path)
        secs = j["sections"]
        print(f"\n=== {stem} ===")
        print(f"  节数: WPS={len(secs)} OOXML={len(sects)}"
              f" {'OK' if len(secs) == len(sects) else '!!MISMATCH'}")
        n_margin = n_tp = n_even = n_fmt = 0
        for i, (s, sp) in enumerate(zip(secs, sects)):
            pg = s["page"]
            mar = sp.find(q("pgMar"))
            if mar is not None:
                for key, jk in (("top", "top_pt"), ("bottom", "bottom_pt"),
                                ("left", "left_pt"), ("right", "right_pt"),
                                ("header", "header_pt"), ("footer", "footer_pt")):
                    v = mar.get(q(key))
                    if v is None:
                        continue
                    expect = round(int(v) / 20.0, 2)
                    got = pg[jk]
                    if got is None or abs(got - expect) > 0.11:
                        print(f"  !! sec{i+1}.{jk}: WPS={got} OOXML={expect} (twips={v})")
                    else:
                        n_margin += 1
            tp = sp.find(q("titlePg")) is not None
            if s["different_first_page"] != tp:
                print(f"  !! sec{i+1}.different_first_page: WPS={s['different_first_page']} OOXML={tp}")
            else:
                n_tp += 1
            if s["odd_and_even_pages"] != even:
                print(f"  !! sec{i+1}.odd_and_even: WPS={s['odd_and_even_pages']} OOXML={even}")
            else:
                n_even += 1
            pn = sp.find(q("pgNumType"))
            fmt = pn.get(q("fmt")) if pn is not None else None
            expect_style = FMT2STYLE.get(fmt, 0 if fmt is None else None)
            got_style = s["page_number_format"]
            if expect_style is not None and got_style != expect_style:
                print(f"  !! sec{i+1}.page_number_format: WPS={got_style} OOXML fmt={fmt} → {expect_style}")
            else:
                n_fmt += 1
        print(f"  逐节比对: 页边距{n_margin} titlePg{n_tp} evenOdd{n_even} pgNumFmt{n_fmt}"
              f" (共 {len(secs)} 节 × 4 项)")
        # 页眉文本抽样
        for i in (0, 1, 2, 3, len(secs) - 1):
            if i < len(secs):
                hs = [h for h in secs[i]["headers"] if h["paragraphs"]]
                txt = hs[0]["paragraphs"][0]["text"] if hs else "(空)"
                print(f"    sec{i+1} default header: {txt[:34]!r}")


if __name__ == "__main__":
    main()
