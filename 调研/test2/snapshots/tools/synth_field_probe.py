"""合成一个含 fldSimple + 文本框内域的 docx，用于验证这两条口径。"""
import shutil
import zipfile
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XMLNS = "http://www.w3.org/XML/1998/namespace"
SRC = Path("corpus/校园便利店饮料补货周期优化研究.docx")
DST = Path("out/synth-textbox-field.docx")


def w(t):
    return f"{{{W}}}{t}"


def add_field(paragraph, instr):
    r = etree.SubElement(paragraph, w("r"))
    etree.SubElement(r, w("fldChar")).set(w("fldCharType"), "begin")
    r = etree.SubElement(paragraph, w("r"))
    it = etree.SubElement(r, w("instrText"))
    it.set(f"{{{XMLNS}}}space", "preserve")
    it.text = instr
    r = etree.SubElement(paragraph, w("r"))
    etree.SubElement(r, w("fldChar")).set(w("fldCharType"), "separate")
    r = etree.SubElement(paragraph, w("r"))
    etree.SubElement(r, w("t")).text = "3"
    r = etree.SubElement(paragraph, w("r"))
    etree.SubElement(r, w("fldChar")).set(w("fldCharType"), "end")


def main():
    z = zipfile.ZipFile(SRC)
    root = etree.fromstring(z.read("word/document.xml"))
    body = root.find(w("body"))

    # 正文第一段：插一个 fldSimple PAGE
    first_p = body.find(w("p"))
    fs = etree.SubElement(first_p, w("fldSimple"))
    fs.set(w("instr"), " PAGE  \\* MERGEFORMAT ")
    r = etree.SubElement(fs, w("r"))
    etree.SubElement(r, w("t")).text = "1"

    # 两个文本框：各插一个复杂域 PAGE
    for tx in root.findall(".//" + w("txbxContent")):
        add_field(tx.find(w("p")), " PAGE  \\* MERGEFORMAT ")

    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as out:
        for item in z.infolist():
            if item.filename == "word/document.xml":
                out.writestr(item, data)
            else:
                out.writestr(item, z.read(item.filename))
    print("wrote", DST)


if __name__ == "__main__":
    main()
