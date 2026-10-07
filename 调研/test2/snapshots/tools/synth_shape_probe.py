"""合成：正文里放 legacy VML 文本框（内联 / 浮动各一），看 WPS 是否合成 SHAPE 域。"""
import zipfile
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
V = "urn:schemas-microsoft-com:vml"
O = "urn:schemas-microsoft-com:office:office"
SRC = Path("corpus/校园便利店饮料补货周期优化研究.docx")
DST = Path("out/synth-shape-vml.docx")


def w(t):
    return f"{{{W}}}{t}"


def v(t):
    return f"{{{V}}}{t}"


def o(t):
    return f"{{{O}}}{t}"


def textbox_para(body, inline: bool, label: str):
    p = etree.SubElement(body, w("p"))
    r = etree.SubElement(p, w("r"))
    pict = etree.SubElement(r, w("pict"))
    style = ("mso-position-vertical-relative:line;width:100pt;height:20pt;"
             if inline else
             "position:absolute;left:0pt;margin-left:10pt;margin-top:10pt;"
             "width:100pt;height:20pt;z-index:1;")
    sh = etree.SubElement(pict, v("shape"))
    sh.set("id", f"_x_s{label}")
    sh.set("type", "#_x0000_t202")
    sh.set("style", style)
    tb = etree.SubElement(sh, v("textbox"))
    content = etree.SubElement(tb, w("txbxContent"))
    cp = etree.SubElement(content, w("p"))
    cr = etree.SubElement(cp, w("r"))
    etree.SubElement(cr, w("t")).text = label


def build(kind: str):
    z = zipfile.ZipFile(SRC)
    root = etree.fromstring(z.read("word/document.xml"))
    body = root.find(w("body"))

    if kind == "both":
        p = etree.SubElement(body, w("p"))
        r = etree.SubElement(p, w("r"))
        pict = etree.SubElement(r, w("pict"))
        st = etree.SubElement(pict, v("shapetype"))
        st.set("id", "_x0000_t202")
        st.set("coordsize", "21600,21600")
        st.set(o("spt"), "202")
        st.set("path", "m,l,21600r21600,l21600,xe")
        textbox_para(body, True, "INLINEBOX")
        textbox_para(body, False, "FLOATBOX")
    else:
        textbox_para(body, kind == "inline", "INLINEBOX" if kind == "inline" else "FLOATBOX")

    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    dst = DST if kind == "both" else DST.with_name(f"synth-shape-{kind}.docx")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
        for item in z.infolist():
            if item.filename == "word/document.xml":
                out.writestr(item, data)
            else:
                out.writestr(item, z.read(item.filename))
    print("wrote", dst)


def main():
    for kind in ("inline", "float"):
        build(kind)


if __name__ == "__main__":
    main()
