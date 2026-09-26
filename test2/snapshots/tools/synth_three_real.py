"""从 corpus/论文初稿.docx 复制一份，去掉指定表的直接边框，只留表样式 21（三线表）。

    uv run python out/synth_three_real.py
"""
import shutil
import zipfile
from pathlib import Path

from lxml import etree

OUT = Path(__file__).resolve().parent
SRC = OUT.parent / "corpus" / "论文初稿.docx"
DST = OUT / "synth-three-style-only.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def q(t):
    return f"{{{W}}}{t}"


def main():
    z = zipfile.ZipFile(SRC)
    doc = etree.fromstring(z.read("word/document.xml"))
    tbls = doc.find(q("body")).findall(q("tbl"))
    t1 = tbls[0]
    pr = t1.find(q("tblPr"))
    b = pr.find(q("tblBorders"))
    if b is not None:
        pr.remove(b)
    removed = 0
    for tc in t1.iter(q("tc")):
        tcpr = tc.find(q("tcPr"))
        if tcpr is None:
            continue
        tb = tcpr.find(q("tcBorders"))
        if tb is not None:
            tcpr.remove(tb)
            removed += 1
    print(f"表1: 去掉 tblBorders + {removed} 个 tcBorders，只留样式 21")
    newdoc = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as w:
        for item in z.infolist():
            data = z.read(item.filename)
            if item.filename == "word/document.xml":
                data = newdoc
            w.writestr(item, data)
    print(f"wrote {DST}")


if __name__ == "__main__":
    main()
