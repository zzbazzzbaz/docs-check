"""合成：内联 DrawingML 文本框 / 带自动编号的 VML 文本框，用于探查 WPS 侧信号。"""
import zipfile
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
V = "urn:schemas-microsoft-com:vml"
O = "urn:schemas-microsoft-com:office:office"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
SRC = Path("corpus/2206181072_李煜_基于ESP32老人健康检测与预警系统的设计与实现.docx")


def q(ns, t):
    return f"{{{ns}}}{t}"


def sub(parent, ns, t, **attrs):
    el = etree.SubElement(parent, q(ns, t))
    for k, v in attrs.items():
        el.set(k, v)
    return el


def run_text(parent, text):
    r = sub(parent, W, "r")
    sub(r, W, "t").text = text
    return r


def vml_textbox(body, label, numbered=False, empty=False, num_id="1"):
    p = sub(body, W, "p")
    r = sub(p, W, "r")
    pict = sub(r, W, "pict")
    st = sub(pict, V, "shapetype")
    st.set("id", "_x0000_t202")
    st.set("coordsize", "21600,21600")
    st.set(q(O, "spt"), "202")
    st.set("path", "m,l,21600r21600,l21600,xe")
    sh = sub(pict, V, "shape")
    sh.set("id", f"_x_s{label}")
    sh.set("type", "#_x0000_t202")
    sh.set("style", "mso-position-vertical-relative:line;width:200pt;height:40pt;")
    tb = sub(sh, V, "textbox")
    content = sub(tb, W, "txbxContent")
    rows = [""] if empty else [f"{label} 编号行", "第二段"]
    for i, txt in enumerate(rows):
        cp = sub(content, W, "p")
        if numbered and i == 0:
            ppr = sub(cp, W, "pPr")
            npr = sub(ppr, W, "numPr")
            sub(npr, W, "ilvl").set(q(W, "val"), "0")
            sub(npr, W, "numId").set(q(W, "val"), num_id)
        run_text(cp, txt)


def inline_drawing(body, label):
    p = sub(body, W, "p")
    r = sub(p, W, "r")
    dr = sub(r, W, "drawing")
    inl = sub(dr, WP, "inline")
    inl.set("distT", "0")
    inl.set("distB", "0")
    inl.set("distL", "0")
    inl.set("distR", "0")
    sub(inl, WP, "extent").set("cx", "3600000")
    sub(inl, WP, "extent").set("cy", "720000")
    ee = sub(inl, WP, "effectExtent")
    for k in ("l", "t", "r", "b"):
        ee.set(k, "0")
    sub(inl, WP, "docPr").set("id", "900")
    sub(inl, WP, "docPr").set("name", "InlineDML")
    sub(inl, WP, "cNvGraphicFramePr")
    g = sub(inl, A, "graphic")
    gd = sub(g, A, "graphicData")
    gd.set("uri", "http://schemas.microsoft.com/office/word/2010/wordprocessingShape")
    wsp = sub(gd, WPS, "wsp")
    sub(wsp, WPS, "cNvSpPr").set("txBox", "1")
    sppr = sub(wsp, WPS, "spPr")
    xfrm = sub(sppr, A, "xfrm")
    off = sub(xfrm, A, "off")
    off.set("x", "0")
    off.set("y", "0")
    ext = sub(xfrm, A, "ext")
    ext.set("cx", "3600000")
    ext.set("cy", "720000")
    pg = sub(sppr, A, "prstGeom")
    pg.set("prst", "rect")
    sub(pg, A, "avLst")
    txbx = sub(wsp, WPS, "txbx")
    content = sub(txbx, W, "txbxContent")
    cp = sub(content, W, "p")
    run_text(cp, f"{label} 内联DML文本")
    sub(wsp, WPS, "bodyPr")


def build():
    z = zipfile.ZipFile(SRC)
    root = etree.fromstring(z.read("word/document.xml"))
    body = root.find(q(W, "body"))
    sect = body.find(q(W, "sectPr"))
    idx = list(body).index(sect)
    vml_textbox(body, "NUMBOX", numbered=True)
    vml_textbox(body, "PLAINBOX", numbered=False)
    vml_textbox(body, "EMPTYBOX", numbered=False, empty=True)
    vml_textbox(body, "ZEROBOX", numbered=True, num_id="0")
    inline_drawing(body, "IDML")
    # 刚 append 到了 sectPr 之后，把新块移到 sectPr 之前
    sect_idx = list(body).index(sect)
    for el in list(body)[sect_idx + 1:]:
        body.remove(el)
        body.insert(idx, el)
    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    dst = Path("out/synth-inline-dml.docx")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
        for item in z.infolist():
            out.writestr(item, data if item.filename == "word/document.xml" else z.read(item.filename))
    print("wrote", dst)


if __name__ == "__main__":
    build()
