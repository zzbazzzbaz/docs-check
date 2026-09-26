"""偏差声明助手：在**底稿的 XML** 上改一处，再打包回字节。

技术设计 §9.2 的 `change`：规则测试写"改哪个对象的哪个属性"，不碰我们自己的模型。
实现方式是标准库 `zipfile` 解包 + `lxml` 改部件 + 重新打包；底稿仍是生成出来的。

对象用**可读的锚点名**定位（与项目"识别锚点宽松"的口径一致）。所有 `change` 都是
`bytes -> bytes` 的纯函数，可用 `change(...)` 串起来。
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCUMENT = "word/document.xml"
STYLES = "word/styles.xml"

Change = Callable[[bytes], bytes]
_El = etree._Element


def _w(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _text(p: _El) -> str:
    return "".join(t.text or "" for t in p.iter(_w("t")))


def _key(p: _El) -> str:
    return "".join(_text(p).split())


def _is_module_title(want: str) -> Callable[[_El], bool]:
    return lambda p: _key(p).upper() == want.upper()


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
    "图题": lambda p: _key(p).startswith("图"),
    "表题": lambda p: _key(p).startswith("表"),
    "文献条目": lambda p: _key(p).startswith("["),
    "附录子标题": lambda p: _key(p).startswith("附录") and _key(p) != "附录",
    "公式段落": lambda p: p.find(f".//{_w('oMath')}") is not None or p.find(f".//{_w('object')}") is not None,
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


def _first_line(target: str, chars: float) -> Change:
    def edit(root: _El) -> None:
        for p in _targets(root, target):
            ppr = _ppr(p)
            ind = ppr.find(_w("ind"))
            if ind is None:
                ind = etree.SubElement(ppr, _w("ind"))
            ind.set(_w("firstLineChars"), str(int(chars * 100)))

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


def combined(deviations: Iterable[Deviation]) -> Deviation:
    """把多个偏差合成一个。"""
    return Deviation(tuple(c for deviation in deviations for c in deviation.changes))
