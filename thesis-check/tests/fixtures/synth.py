"""偏差声明助手：在**底稿的 XML** 上改一处，再打包回字节。

技术设计 §9.2 的 `change`：规则测试写"改哪个对象的哪个属性"，不碰我们自己的模型。
实现方式是标准库 `zipfile` 解包 + `lxml` 改部件 + 重新打包；底稿仍是生成出来的。

对象用**可读的锚点名**定位（与项目"识别锚点宽松"的口径一致）。所有 `change` 都是
`bytes -> bytes` 的纯函数，可用 `change(...)` 串起来。
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
DOCUMENT = "word/document.xml"
STYLES = "word/styles.xml"
HEADER = "word/header1.xml"
FOOTER = "word/footer1.xml"

Change = Callable[[bytes], bytes]
_El = etree._Element


def _w(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _m(tag: str) -> str:
    return f"{{{M}}}{tag}"


def _text(p: _El) -> str:
    return "".join(t.text or "" for t in p.iter(_w("t")))


def _key(p: _El) -> str:
    return "".join(_text(p).split())


def _is_module_title(want: str) -> Callable[[_El], bool]:
    return lambda p: _key(p).upper() == want.upper() and not _is_toc(p)


def _style_val(p: _El) -> str:
    ppr = p.find(_w("pPr"))
    style = ppr.find(_w("pStyle")) if ppr is not None else None
    return (style.get(_w("val")) or "") if style is not None else ""


def _is_toc(p: _El) -> bool:
    return _style_val(p) in ("TOC1", "TOC2", "TOC3")


def _body_text(p: _El, prefix: str) -> bool:
    """正文区以 `prefix` 开头的段落（排除目录里同名的条目）。"""
    return _key(p).startswith(prefix) and not _is_toc(p)


# 锚点名 -> 段落判据。名字面向规则文档里的"对象"列，不面向 XML。
TARGETS: dict[str, Callable[[_El], bool]] = {
    "中文摘要标题": _is_module_title("摘要"),
    "英文摘要标题": _is_module_title("ABSTRACT"),
    "目录标题": _is_module_title("目录"),
    "参考文献标题": _is_module_title("参考文献"),
    "致谢标题": _is_module_title("致谢"),
    "附录标题": _is_module_title("附录"),
    "中文关键词行": lambda p: _key(p).startswith("关键词"),
    "英文关键词行": lambda p: _key(p).lower().startswith("keywords"),
    "本科生毕业设计行": lambda p: _key(p) == "本科生毕业设计（论文）",
    "题目行": lambda p: _key(p).startswith("题目"),
    "信息行": lambda p: any(
        _key(p).startswith(k) for k in ("学生姓名", "学号", "院系", "专业年级", "指导教师")
    ),
    "学生姓名行": lambda p: _key(p).startswith("学生姓名"),
    "日期行": lambda p: all(mark in _key(p) for mark in "年月日"),
    "中文摘要正文": lambda p: _key(p).startswith(("本设计", "测试表明")),
    "中文摘要正文末段": lambda p: _key(p).startswith("测试表明"),
    "英文摘要正文": lambda p: _key(p).startswith("Thisdesign"),
    # 正文标题（排除目录条目）
    "第一章标题": lambda p: _body_text(p, "第一章"),
    "第二章标题": lambda p: _body_text(p, "第二章"),
    "第三章标题": lambda p: _body_text(p, "第三章"),
    "二级标题": lambda p: _key(p).endswith("研究背景"),
    "三级标题": lambda p: _key(p).endswith("现状分析"),
    "三级以下标题": lambda p: _key(p).startswith("（1）"),
    "正文段落": lambda p: _key(p).startswith("这是第"),
    # 目录条目：层级看样式名
    "目录条目": _is_toc,
    "目录一级条目": lambda p: _style_val(p) == "TOC1",
    "目录二级条目": lambda p: _style_val(p) == "TOC2",
    "目录三级条目": lambda p: _style_val(p) == "TOC3",
    "图题": lambda p: re.match(r"^图\d+-\d+", _key(p)) is not None,
    "表题": lambda p: re.match(r"^表\d+-\d+", _key(p)) is not None,
    "图块": lambda p: p.find(f".//{_w('drawing')}") is not None,
    "引用标注": lambda p: any(re.fullmatch(r"\[\d+\]", _run_text_value(r)) for r in p.iter(_w("r"))),
    "文献条目": lambda p: _key(p).startswith("["),
    "文献条目2": lambda p: _key(p).startswith("[2]"),
    "致谢正文": lambda p: _key(p).startswith(("感谢导师", "感谢家人")),
    "附录正文": lambda p: _key(p).startswith(("论文的附录", "此处为程序代码")),
    "附录子标题": lambda p: _key(p).startswith("附录") and _key(p) != "附录",
    "公式段落": lambda p: p.find(f".//{_m('oMath')}") is not None or p.find(f".//{_w('object')}") is not None,
    "空段落": lambda p: _text(p).strip() == "" and p.find(f".//{_w('fldChar')}") is None,
}


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _zip(parts: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _edit(part: str, edit: Callable[[_El], None]) -> Change:
    def apply(data: bytes) -> bytes:
        parts = _parts(data)
        root = etree.fromstring(parts[part])
        edit(root)
        parts[part] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        return _zip(parts)

    return apply


def change(*changes: Change) -> Change:
    """把多个改动串成一个。"""

    def apply(data: bytes) -> bytes:
        for item in changes:
            data = item(data)
        return data

    return apply


def _targets(root: _El, target: str) -> list[_El]:
    predicate = TARGETS[target]
    body = root.find(_w("body"))
    if body is None:
        return []
    return [p for p in body.iter(_w("p")) if predicate(p)]


def _rpr(run: _El) -> _El:
    rpr = run.find(_w("rPr"))
    if rpr is None:
        rpr = etree.Element(_w("rPr"))
        run.insert(0, rpr)
    return rpr


def _rfonts(run: _El) -> _El:
    rpr = _rpr(run)
    fonts = rpr.find(_w("rFonts"))
    if fonts is None:
        fonts = etree.Element(_w("rFonts"))
        rpr.insert(0, fonts)
    return fonts


def _ppr(p: _El) -> _El:
    ppr = p.find(_w("pPr"))
    if ppr is None:
        ppr = etree.Element(_w("pPr"))
        p.insert(0, ppr)
    return ppr


def _runs(p: _El) -> Iterator[_El]:
    yield from p.iter(_w("r"))


def _ea(target: str, font: str) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            for run in _runs(p):
                _rfonts(run).set(_w("eastAsia"), font)

    return _edit(DOCUMENT, edit)


def _west(target: str, font: str) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            for run in _runs(p):
                fonts = _rfonts(run)
                fonts.set(_w("ascii"), font)
                fonts.set(_w("hAnsi"), font)

    return _edit(DOCUMENT, edit)


def _size(target: str, pt: float) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            for run in _runs(p):
                rpr = _rpr(run)
                sz = rpr.find(_w("sz"))
                if sz is None:
                    sz = etree.SubElement(rpr, _w("sz"))
                sz.set(_w("val"), str(int(pt * 2)))

    return _edit(DOCUMENT, edit)


def _bold(target: str, on: bool = True) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            for run in _runs(p):
                rpr = _rpr(run)
                existing = rpr.find(_w("b"))
                if existing is not None:
                    rpr.remove(existing)
                if on:
                    rpr.insert(0, etree.Element(_w("b")))

    return _edit(DOCUMENT, edit)


def _align(target: str, value: str) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            ppr = _ppr(p)
            jc = ppr.find(_w("jc"))
            if jc is None:
                jc = etree.SubElement(ppr, _w("jc"))
            jc.set(_w("val"), value)

    return _edit(DOCUMENT, edit)


def _line_spacing(target: str, multiple: float) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            ppr = _ppr(p)
            spacing = ppr.find(_w("spacing"))
            if spacing is None:
                spacing = etree.SubElement(ppr, _w("spacing"))
            spacing.set(_w("line"), str(int(multiple * 240)))
            spacing.set(_w("lineRule"), "auto")

    return _edit(DOCUMENT, edit)


def _line_exact(target: str, pt: float) -> Change:
    """把行距写成**固定值**（`lineRule=exact`）：FR-3.5 应直接判不合格。"""

    def edit(root: _El) -> None:
        for p in _targets(root, target):
            ppr = _ppr(p)
            spacing = ppr.find(_w("spacing"))
            if spacing is None:
                spacing = etree.SubElement(ppr, _w("spacing"))
            spacing.set(_w("line"), str(int(pt * 20)))
            spacing.set(_w("lineRule"), "exact")

    return _edit(DOCUMENT, edit)


def _page_break(target: str, on: bool) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            ppr = _ppr(p)
            existing = ppr.find(_w("pageBreakBefore"))
            if existing is not None:
                ppr.remove(existing)
            if on:
                ppr.insert(0, etree.Element(_w("pageBreakBefore")))

    return _edit(DOCUMENT, edit)


def _insert_blank_after(target: str) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            parent = p.getparent()
            if parent is not None:
                parent.insert(parent.index(p) + 1, etree.Element(_w("p")))

    return _edit(DOCUMENT, edit)


def _delete(target: str) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            parent = p.getparent()
            if parent is not None:
                parent.remove(p)

    return _edit(DOCUMENT, edit)


def _rename_style(old: str, new: str) -> Change:
    def edit(root: _El) -> None:
        for name in root.iter(_w("name")):
            if name.get(_w("val")) == old:
                name.set(_w("val"), new)

    return _edit(STYLES, edit)


def _run_text_value(run: _El) -> str:
    return "".join(t.text or "" for t in run.iter(_w("t")))


def _target_runs(root: _El, target: str, prefix: str) -> Iterator[_El]:
    """目标段落里**文本以 `prefix` 开头**的 run（按行内片段改动用）。"""
    for p in _targets(root, target):
        for run in _runs(p):
            if _run_text_value(run).startswith(prefix):
                yield run


def _run_ea(target: str, prefix: str, font: str) -> Change:
    def edit(root: _El) -> None:
        for run in _target_runs(root, target, prefix):
            _rfonts(run).set(_w("eastAsia"), font)

    return _edit(DOCUMENT, edit)


def _run_west(target: str, prefix: str, font: str) -> Change:
    def edit(root: _El) -> None:
        for run in _target_runs(root, target, prefix):
            fonts = _rfonts(run)
            fonts.set(_w("ascii"), font)
            fonts.set(_w("hAnsi"), font)

    return _edit(DOCUMENT, edit)


def _run_size(target: str, prefix: str, pt: float) -> Change:
    def edit(root: _El) -> None:
        for run in _target_runs(root, target, prefix):
            rpr = _rpr(run)
            sz = rpr.find(_w("sz"))
            if sz is None:
                sz = etree.SubElement(rpr, _w("sz"))
            sz.set(_w("val"), str(int(pt * 2)))

    return _edit(DOCUMENT, edit)


def _run_bold(target: str, prefix: str, on: bool = True) -> Change:
    def edit(root: _El) -> None:
        for run in _target_runs(root, target, prefix):
            rpr = _rpr(run)
            existing = rpr.find(_w("b"))
            if existing is not None:
                rpr.remove(existing)
            if on:
                rpr.insert(0, etree.Element(_w("b")))

    return _edit(DOCUMENT, edit)


def _run_text(target: str, prefix: str, text: str) -> Change:
    def edit(root: _El) -> None:
        for run in _target_runs(root, target, prefix):
            texts = list(run.iter(_w("t")))
            if not texts:
                continue
            texts[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            texts[0].text = text
            for extra in texts[1:]:
                extra.text = ""

    return _edit(DOCUMENT, edit)


def _run_va(target: str, prefix: str, value: str) -> Change:
    """改目标段落里以 `prefix` 开头那个 run 的 `w:vertAlign`。"""

    def edit(root: _El) -> None:
        for run in _target_runs(root, target, prefix):
            rpr = _rpr(run)
            existing = rpr.find(_w("vertAlign"))
            if existing is not None:
                rpr.remove(existing)
            etree.SubElement(rpr, _w("vertAlign")).set(_w("val"), value)

    return _edit(DOCUMENT, edit)


def _first_line(target: str, chars: float) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            ppr = _ppr(p)
            ind = ppr.find(_w("ind"))
            if ind is None:
                ind = etree.SubElement(ppr, _w("ind"))
            ind.set(_w("firstLineChars"), str(int(chars * 100)))

    return _edit(DOCUMENT, edit)


# ── 行内文本替换 / 大纲级别 / 插入合规段落 ─────────────────────


def _run_replace(target: str, prefix: str, old: str, new: str) -> Change:
    def edit(root: _El) -> None:
        for run in _target_runs(root, target, prefix):
            texts = list(run.iter(_w("t")))
            if texts:
                texts[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                texts[0].text = (texts[0].text or "").replace(old, new)

    return _edit(DOCUMENT, edit)


def _outline(target: str, level: int) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            ppr = _ppr(p)
            existing = ppr.find(_w("outlineLvl"))
            if existing is not None:
                ppr.remove(existing)
            etree.SubElement(ppr, _w("outlineLvl")).set(_w("val"), str(level))

    return _edit(DOCUMENT, edit)


_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _compliant_line(text: str) -> _El:
    """全合规正文行：宋体 / TNR / 小四 / 1.5 倍 / 首行缩进 2 字符 / 两端对齐。"""
    p = etree.Element(_w("p"))
    ppr = etree.SubElement(p, _w("pPr"))
    etree.SubElement(ppr, _w("jc")).set(_w("val"), "both")
    spacing = etree.SubElement(ppr, _w("spacing"))
    spacing.set(_w("line"), "360")
    spacing.set(_w("lineRule"), "auto")
    etree.SubElement(ppr, _w("ind")).set(_w("firstLineChars"), "200")
    run = etree.SubElement(p, _w("r"))
    rpr = etree.SubElement(run, _w("rPr"))
    fonts = etree.SubElement(rpr, _w("rFonts"))
    fonts.set(_w("ascii"), "Times New Roman")
    fonts.set(_w("hAnsi"), "Times New Roman")
    fonts.set(_w("eastAsia"), "宋体")
    etree.SubElement(rpr, _w("sz")).set(_w("val"), "24")
    node = etree.SubElement(run, _w("t"))
    node.set(_XML_SPACE, "preserve")
    node.text = text
    return p


def _insert_line(target: str, text: str, *, before: bool) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            parent = p.getparent()
            if parent is None:
                continue
            parent.insert(parent.index(p) + (0 if before else 1), _compliant_line(text))
            if before:
                break  # 只插在第一处之前（如模块标题），不影响其它同锚点段落

    return _edit(DOCUMENT, edit)


# ── 页眉 / 页脚部件 ────────────────────────────────────────────


def _hf_ea(part: str, font: str) -> Change:
    def edit(root: _El) -> None:
        for run in root.iter(_w("r")):
            _rfonts(run).set(_w("eastAsia"), font)

    return _edit(part, edit)


def _hf_west(part: str, font: str) -> Change:
    def edit(root: _El) -> None:
        for run in root.iter(_w("r")):
            fonts = _rfonts(run)
            fonts.set(_w("ascii"), font)
            fonts.set(_w("hAnsi"), font)

    return _edit(part, edit)


def _hf_size(part: str, pt: float) -> Change:
    def edit(root: _El) -> None:
        for run in root.iter(_w("r")):
            rpr = _rpr(run)
            existing = rpr.find(_w("sz"))
            if existing is None:
                existing = etree.SubElement(rpr, _w("sz"))
            existing.set(_w("val"), str(int(pt * 2)))

    return _edit(part, edit)


def _hf_align(part: str, value: str) -> Change:
    def edit(root: _El) -> None:
        for p in root.iter(_w("p")):
            ppr = _ppr(p)
            existing = ppr.find(_w("jc"))
            if existing is not None:
                ppr.remove(existing)
            etree.SubElement(ppr, _w("jc")).set(_w("val"), value)

    return _edit(part, edit)


def _hf_text(part: str, text: str) -> Change:
    def edit(root: _El) -> None:
        for t in root.iter(_w("t")):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = text
            break

    return _edit(part, edit)


# ── 分节 / 页面设置 ────────────────────────────────────────────


def _sect_prs(root: _El) -> list[tuple[_El, _El | None]]:
    body = root.find(_w("body"))
    if body is None:
        return []
    out: list[tuple[_El, _El | None]] = []
    for p in body.iter(_w("p")):
        ppr = p.find(_w("pPr"))
        sect = ppr.find(_w("sectPr")) if ppr is not None else None
        if sect is not None:
            out.append((sect, p))
    body_sect = body.find(_w("sectPr"))
    if body_sect is not None:
        out.append((body_sect, None))
    return out


def _sect_edit(index: int, edit: Callable[[_El], None]) -> Change:
    def apply(root: _El) -> None:
        items = _sect_prs(root)
        if 1 <= index <= len(items):
            edit(items[index - 1][0])

    return _edit(DOCUMENT, apply)


def _add_reference(kind: str, index: int) -> Change:
    def edit(sect: _El) -> None:
        node = etree.Element(_w(f"{kind}Reference"))
        node.set(_w("type"), "default")
        node.set(f"{{{R}}}id", "rIdF1" if kind == "footer" else "rIdH1")
        sect.insert(0, node)

    return _sect_edit(index, edit)


def _remove_reference(kind: str, index: int) -> Change:
    def edit(sect: _El) -> None:
        for node in sect.findall(_w(f"{kind}Reference")):
            sect.remove(node)

    return _sect_edit(index, edit)


def _dangling_reference(kind: str, index: int) -> Change:
    """加一个指向不存在部件的引用：显式切断上一节的继承（用于「本节无页码」）。"""

    def edit(sect: _El) -> None:
        node = etree.Element(_w(f"{kind}Reference"))
        node.set(_w("type"), "default")
        node.set(f"{{{R}}}id", "rIdMissing")
        sect.insert(0, node)

    return _sect_edit(index, edit)


def _set_page_number_format(index: int, fmt: str) -> Change:
    def edit(sect: _El) -> None:
        node = sect.find(_w("pgNumType"))
        if node is None:
            node = etree.SubElement(sect, _w("pgNumType"))
        node.set(_w("fmt"), fmt)

    return _sect_edit(index, edit)


def _set_page_size(index: int) -> Change:
    def edit(sect: _El) -> None:
        node = sect.find(_w("pgSz"))
        if node is None:
            node = etree.SubElement(sect, _w("pgSz"))
        node.set(_w("w"), "12240")
        node.set(_w("h"), "15840")

    return _sect_edit(index, edit)


def _set_margin(index: int, side: str, value: str) -> Change:
    def edit(sect: _El) -> None:
        node = sect.find(_w("pgMar"))
        if node is None:
            node = etree.SubElement(sect, _w("pgMar"))
        node.set(_w(side), value)

    return _sect_edit(index, edit)


def _remove_section_break(index: int) -> Change:
    def apply(root: _El) -> None:
        items = _sect_prs(root)
        if not (1 <= index <= len(items)):
            return
        sect, para = items[index - 1]
        if para is not None:
            parent = para.getparent()
            if parent is not None:
                parent.remove(para)
        else:
            parent = sect.getparent()
            if parent is not None:
                parent.remove(sect)

    return _edit(DOCUMENT, apply)


def _add_auto_numbering(target: str, num_id: int = 5) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            ppr = _ppr(p)
            numpr = etree.SubElement(ppr, _w("numPr"))
            ilvl = etree.SubElement(numpr, _w("ilvl"))
            ilvl.set(_w("val"), "0")
            num = etree.SubElement(numpr, _w("numId"))
            num.set(_w("val"), str(num_id))

    return _edit(DOCUMENT, edit)


@dataclass(frozen=True, slots=True)
class Deviation:
    """一个偏差声明：底稿 + 串好的改动。`CASE` 用它跑"只报这一条"。"""

    changes: tuple[Change, ...]

    def apply(self, base: bytes) -> bytes:
        return change(*self.changes)(base)


def ea(target: str, font: str) -> Deviation:
    return Deviation((_ea(target, font),))


def west(target: str, font: str) -> Deviation:
    return Deviation((_west(target, font),))


def size(target: str, pt: float) -> Deviation:
    return Deviation((_size(target, pt),))


def bold(target: str, on: bool = True) -> Deviation:
    return Deviation((_bold(target, on),))


def alignment(target: str, value: str) -> Deviation:
    return Deviation((_align(target, value),))


def line_spacing(target: str, multiple: float) -> Deviation:
    return Deviation((_line_spacing(target, multiple),))


def line_exact(target: str, pt: float) -> Deviation:
    """把行距改成固定值 `pt`（`lineRule=exact`）。"""
    return Deviation((_line_exact(target, pt),))


def page_break(target: str, on: bool = True) -> Deviation:
    """加 / 去目标段落的 `w:pageBreakBefore`。"""
    return Deviation((_page_break(target, on),))


def run_va(target: str, prefix: str, value: str) -> Deviation:
    """改目标段落里以 `prefix` 开头那个 run 的上下标。"""
    return Deviation((_run_va(target, prefix, value),))


def insert_blank_after(target: str) -> Deviation:
    return Deviation((_insert_blank_after(target),))


def delete(target: str) -> Deviation:
    return Deviation((_delete(target),))


def rename_style(old: str, new: str) -> Deviation:
    return Deviation((_rename_style(old, new),))


def run_ea(target: str, prefix: str, font: str) -> Deviation:
    """只改目标段落里以 `prefix` 开头那个 run 的中文字体。"""
    return Deviation((_run_ea(target, prefix, font),))


def run_west(target: str, prefix: str, font: str) -> Deviation:
    """只改目标段落里以 `prefix` 开头那个 run 的西文字体。"""
    return Deviation((_run_west(target, prefix, font),))


def run_size(target: str, prefix: str, pt: float) -> Deviation:
    """只改目标段落里以 `prefix` 开头那个 run 的字号。"""
    return Deviation((_run_size(target, prefix, pt),))


def run_bold(target: str, prefix: str, on: bool = True) -> Deviation:
    """只改目标段落里以 `prefix` 开头那个 run 的加粗。"""
    return Deviation((_run_bold(target, prefix, on),))


def run_text(target: str, prefix: str, text: str) -> Deviation:
    """只改目标段落里以 `prefix` 开头那个 run 的文本。"""
    return Deviation((_run_text(target, prefix, text),))


def first_line(target: str, chars: float) -> Deviation:
    return Deviation((_first_line(target, chars),))


def run_replace(target: str, prefix: str, old: str, new: str) -> Deviation:
    """在目标段落的某个 run 内做一次子串替换（编号 / 类型标识等文本微调）。"""
    return Deviation((_run_replace(target, prefix, old, new),))


def outline_level(target: str, level: int) -> Deviation:
    """改目标段落的大纲级别（`w:outlineLvl`，0 起）。"""
    return Deviation((_outline(target, level),))


def insert_line_after(target: str, text: str) -> Deviation:
    """在目标段落后插入一个全合规正文行。"""
    return Deviation((_insert_line(target, text, before=False),))


def insert_line_before(target: str, text: str) -> Deviation:
    """在目标段落前插入一个全合规正文行。"""
    return Deviation((_insert_line(target, text, before=True),))


def header_ea(font: str) -> Deviation:
    return Deviation((_hf_ea(HEADER, font),))


def header_size(pt: float) -> Deviation:
    return Deviation((_hf_size(HEADER, pt),))


def header_align(value: str) -> Deviation:
    return Deviation((_hf_align(HEADER, value),))


def header_text(text: str) -> Deviation:
    return Deviation((_hf_text(HEADER, text),))


def footer_align(value: str) -> Deviation:
    return Deviation((_hf_align(FOOTER, value),))


def footer_page_west(font: str) -> Deviation:
    return Deviation((_hf_west(FOOTER, font),))


def footer_page_size(pt: float) -> Deviation:
    return Deviation((_hf_size(FOOTER, pt),))


def add_header_reference(index: int) -> Deviation:
    return Deviation((_add_reference("header", index),))


def add_footer_reference(index: int) -> Deviation:
    return Deviation((_add_reference("footer", index),))


def dangling_footer_reference(index: int) -> Deviation:
    return Deviation((_dangling_reference("footer", index),))


def remove_header_reference(index: int) -> Deviation:
    return Deviation((_remove_reference("header", index),))


def remove_footer_reference(index: int) -> Deviation:
    return Deviation((_remove_reference("footer", index),))


def page_number_format(index: int, fmt: str) -> Deviation:
    return Deviation((_set_page_number_format(index, fmt),))


def page_size(index: int) -> Deviation:
    return Deviation((_set_page_size(index),))


def page_margin(index: int, side: str, value: str) -> Deviation:
    return Deviation((_set_margin(index, side, value),))


def remove_section_break(index: int) -> Deviation:
    return Deviation((_remove_section_break(index),))


def auto_numbering(target: str, num_id: int = 5) -> Deviation:
    return Deviation((_add_auto_numbering(target, num_id),))


def combined(deviations: Iterable[Deviation]) -> Deviation:
    """把多个偏差合成一个。"""
    return Deviation(tuple(c for deviation in deviations for c in deviation.changes))
