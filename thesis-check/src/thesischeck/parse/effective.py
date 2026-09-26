"""L1 有效格式：把 OOXML 的级联合成为**已归一的 Python 值**。

级联顺序（低 -> 高）::

    字符：docDefaults.rPrDefault -> 段落样式链 rPr -> 字符样式链 rPr -> run 直接 rPr
    段落：docDefaults.pPrDefault -> 段落样式链 pPr -> 段落直接 pPr

段落没写 ``pStyle`` 时套默认段落样式（``w:default="1"``）。
字体分槽：中文读 ``eastAsia``，西文读 ``ascii``（缺失时退回 ``hAnsi``）。
``xxxTheme`` 引用经主题解出真实字体名；主题里 EastAsia 为空时回退到同 scheme 的 latin。

取值与回溯共用同一份实现：``Resolver.para`` / ``Resolver.run`` 接受可选 ``trace``，
把每个属性的**胜出来源**追加进去，绝不另写一份"查来源"的代码。
来源标签取值固定为 ``run`` / ``字符样式:<id>`` / ``样式:<样式名>`` / ``默认段落样式`` /
``docDefaults`` / ``主题字体``；其中 ``run`` 指"对象自身直接设置"（run 的 rPr 或段落的 pPr）。

取不到值一律 ``None``——``None`` 是"无法判定"，不是"不符合"。
本模块只做取值与归一，不做任何判定。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from lxml import etree

from .model import LineRule, NumPr

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

_LINE_RULES = frozenset({"auto", "exact", "atLeast"})
_OFF_VALUES = frozenset({"0", "false", "off", "no"})

# ascii/asciiTheme 是同一个槽的两种互斥写法：近层写了主题引用就顶掉远层的显式值
FONT_SLOTS = (
    ("ascii", "asciiTheme"),
    ("hAnsi", "hAnsiTheme"),
    ("eastAsia", "eastAsiaTheme"),
    ("cs", "cstheme"),
)

_Value = float | str | bool
_Entry = tuple[_Value, str]
_Layer = tuple[str, etree._Element | None]


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def a(tag: str) -> str:
    return f"{{{A_NS}}}{tag}"


def _local_attrs(el: etree._Element) -> dict[str, str]:
    """按本地名取属性：`w:left` 与裸 `left` 都要认（后者不符合规范但真实文档里出现过）。"""
    return {cast(str, k).rsplit("}", 1)[-1]: cast(str, v) for k, v in el.attrib.items()}


def _onoff(el: etree._Element) -> bool:
    """开关类属性：缺省为真，``0/false/off/no`` 为假。"""
    val = el.get(w("val"))
    return True if val is None else val not in _OFF_VALUES


@dataclass(frozen=True, slots=True)
class StyleDef:
    """一个样式定义。``is_default`` 是 ``w:default="1"``。"""

    id: str
    name: str
    kind: str | None
    is_default: bool
    based_on: str | None
    rpr: etree._Element | None
    ppr: etree._Element | None
    tbl_pr: etree._Element | None


class StyleTable:
    """样式表 + ``docDefaults``。只读，构造一次。"""

    def __init__(self, root: etree._Element | None) -> None:
        self.by_id: dict[str, StyleDef] = {}
        self.dd_rpr: etree._Element | None = None
        self.dd_ppr: etree._Element | None = None
        self.default_para: str | None = None
        if root is None:
            return
        for el in root.iter(w("style")):
            sid = el.get(w("styleId"))
            if not sid:
                continue
            name = el.find(w("name"))
            based_on = el.find(w("basedOn"))
            self.by_id[sid] = StyleDef(
                id=sid,
                name=(name.get(w("val")) if name is not None else None) or "",
                kind=el.get(w("type")),
                is_default=el.get(w("default")) in ("1", "true"),
                based_on=based_on.get(w("val")) if based_on is not None else None,
                rpr=el.find(w("rPr")),
                ppr=el.find(w("pPr")),
                tbl_pr=el.find(w("tblPr")),
            )
        defaults = root.find(w("docDefaults"))
        if defaults is not None:
            rpr = defaults.find(w("rPrDefault"))
            if rpr is not None:
                self.dd_rpr = rpr.find(w("rPr"))
            ppr = defaults.find(w("pPrDefault"))
            if ppr is not None:
                self.dd_ppr = ppr.find(w("pPr"))
        self.default_para = next(
            (s.id for s in self.by_id.values() if s.kind == "paragraph" and s.is_default),
            None,
        )

    def chain(self, style_id: str | None) -> list[StyleDef]:
        """样式链，祖先 -> 自身；带环保护。"""
        out: list[StyleDef] = []
        seen: set[str] = set()
        while style_id and style_id not in seen:
            seen.add(style_id)
            style = self.by_id.get(style_id)
            if style is None:
                break
            out.append(style)
            style_id = style.based_on
        return list(reversed(out))

    def label(self, style: StyleDef) -> str:
        if style.id == self.default_para:
            return "默认段落样式"
        return f"样式:{style.name or style.id}"


class ThemeFonts:
    """主题字体：``minorAscii`` / ``majorEastAsia`` 之类的引用在这里解成真实字体名。"""

    def __init__(self, root: etree._Element | None) -> None:
        self._slot: dict[str, str] = {}
        if root is None:
            return
        scheme = root.find(f".//{a('fontScheme')}")
        if scheme is None:
            return
        for el in scheme:
            tag = etree.QName(el).localname
            if tag not in ("majorFont", "minorFont"):
                continue
            prefix = "major" if tag == "majorFont" else "minor"
            latin = el.find(a("latin"))
            ea = el.find(a("ea"))
            cs = el.find(a("cs"))
            if latin is not None and (latin_name := latin.get("typeface")):
                self._slot[prefix + "HAnsi"] = latin_name
                self._slot[prefix + "Ascii"] = latin_name
            if ea is not None and (ea_name := ea.get("typeface")):
                self._slot[prefix + "EastAsia"] = ea_name
            if cs is not None and (cs_name := cs.get("typeface")):
                self._slot[prefix + "Bidi"] = cs_name

    def resolve(self, theme_name: str | None) -> str | None:
        if not theme_name:
            return None
        value = self._slot.get(theme_name)
        if value:
            return value
        # 主题里 ea 为空时，回退到同 scheme 的 latin
        if theme_name.endswith("EastAsia"):
            return self._slot.get(theme_name[: -len("EastAsia")] + "HAnsi")
        return None


@dataclass(frozen=True, slots=True)
class Source:
    """一个属性的胜出来源。``label`` 是上面固定的六种之一。"""

    prop: str
    label: str


def source_of(trace: Sequence[Source], prop: str) -> str | None:
    """回溯：某属性最后一次被哪一层设置（同一属性按级联顺序追加，最后一条即胜出）。"""
    for source in reversed(trace):
        if source.prop == prop:
            return source.label
    return None


@dataclass(frozen=True, slots=True)
class RunFormat:
    """一个 run 的**有效**字符格式。``None`` = 取不到。"""

    ea: str | None
    west: str | None
    size: float | None
    bold: bool | None
    italic: bool | None
    va: str | None


@dataclass(frozen=True, slots=True)
class ParaFormat:
    """一个段落的**有效**段落格式（缩进一律以字符计）。``None`` = 取不到。"""

    style_id: str | None
    style_name: str | None
    align: str | None
    outline: int | None
    line_rule: LineRule
    line_multiple: float | None
    line_pt: float | None
    first_line_chars: float | None
    left_chars: float | None
    right_chars: float | None
    hanging_chars: float | None
    space_before_pt: float | None
    space_after_pt: float | None
    numbering: NumPr | None
    page_break_before: bool
    keep_with_next: bool | None


def _cascade_rpr(layers: Sequence[_Layer], theme: ThemeFonts) -> dict[str, _Entry]:
    """字符级级联。层按低 -> 高给，后写覆盖先写。"""
    picked: dict[str, _Entry] = {}
    slots: dict[str, tuple[bool, str, str]] = {}
    for label, pr in layers:
        if pr is None:
            continue
        fonts = pr.find(w("rFonts"))
        if fonts is not None:
            attrs = _local_attrs(fonts)
            for plain, themed in FONT_SLOTS:
                if plain in attrs:
                    slots[plain] = (False, attrs[plain], label)
                elif themed in attrs:
                    slots[plain] = (True, attrs[themed], label)
        size = pr.find(w("sz"))
        if size is not None and (size_val := size.get(w("val"))) is not None:
            picked["size"] = (int(size_val) / 2.0, label)
        for tag, prop in (("b", "bold"), ("i", "italic")):
            el = pr.find(w(tag))
            if el is not None:
                picked[prop] = (_onoff(el), label)
        va = pr.find(w("vertAlign"))
        if va is not None and (va_val := va.get(w("val"))) is not None:
            picked["va"] = (va_val, label)

    def resolve_slot(slot: str) -> tuple[str | None, str | None]:
        entry = slots.get(slot)
        if entry is None:
            return None, None
        is_theme, value, label = entry
        if is_theme:
            return theme.resolve(value), "主题字体"
        return value, label

    west, west_label = resolve_slot("ascii")
    if not west:
        west, west_label = resolve_slot("hAnsi")
    if west:
        picked["west"] = (west, west_label or "")
    ea, ea_label = resolve_slot("eastAsia")
    if ea:
        picked["ea"] = (ea, ea_label or "")
    return picked


def _cascade_ppr(layers: Sequence[_Layer]) -> dict[str, _Entry]:
    """段落级级联。层按低 -> 高给，后写覆盖先写。"""
    picked: dict[str, _Entry] = {}
    for label, pr in layers:
        if pr is None:
            continue
        jc = pr.find(w("jc"))
        if jc is not None and (jc_val := jc.get(w("val"))) is not None:
            picked["align"] = (jc_val, label)
        ind = pr.find(w("ind"))
        if ind is not None:
            attrs = _local_attrs(ind)
            for attr, key in (
                ("left", "left_twips"),
                ("start", "left_twips"),
                ("right", "right_twips"),
                ("end", "right_twips"),
                ("leftChars", "left_chars"),
                ("rightChars", "right_chars"),
                ("firstLine", "first_line_twips"),
                ("firstLineChars", "first_line_chars"),
                ("hanging", "hanging_twips"),
                ("hangingChars", "hanging_chars"),
            ):
                if attr in attrs:
                    picked[key] = (float(attrs[attr]), label)
        spacing = pr.find(w("spacing"))
        if spacing is not None:
            attrs = _local_attrs(spacing)
            for attr, key in (
                ("before", "space_before_twips"),
                ("after", "space_after_twips"),
                ("line", "line"),
                ("lineRule", "line_rule"),
            ):
                if attr in attrs:
                    picked[key] = (attrs[attr] if key == "line_rule" else float(attrs[attr]), label)
        outline = pr.find(w("outlineLvl"))
        if outline is not None and (outline_val := outline.get(w("val"))) is not None:
            picked["outline"] = (float(int(outline_val)), label)
        page_break = pr.find(w("pageBreakBefore"))
        if page_break is not None:
            picked["page_break_before"] = (_onoff(page_break), label)
        keep_next = pr.find(w("keepNext"))
        if keep_next is not None:
            picked["keep_with_next"] = (_onoff(keep_next), label)
        numpr = pr.find(w("numPr"))
        if numpr is not None:
            num_id = numpr.find(w("numId"))
            if num_id is not None and (num_id_val := num_id.get(w("val"))) is not None:
                picked["num_id"] = (float(int(num_id_val)), label)
            ilvl = numpr.find(w("ilvl"))
            if ilvl is not None and (ilvl_val := ilvl.get(w("val"))) is not None:
                picked["num_ilvl"] = (float(int(ilvl_val)), label)
    return picked


def _chars(chars: _Entry | None, twips: _Entry | None, size_pt: float | None) -> tuple[float, str] | None:
    """缩进归一为字符：优先 ``*Chars``（1/100 字符）；缺失时才用缇值 ÷ 20 ÷ 字号。"""
    if chars is not None and float(chars[0]) != 0.0:
        return float(chars[0]) / 100.0, chars[1]
    if twips is not None and size_pt:
        return float(twips[0]) / 20.0 / size_pt, twips[1]
    return None


def _float(picked: dict[str, _Entry], key: str) -> float | None:
    entry = picked.get(key)
    return float(entry[0]) if entry is not None else None


def _str(picked: dict[str, _Entry], key: str) -> str | None:
    entry = picked.get(key)
    return str(entry[0]) if entry is not None else None


def _bool(picked: dict[str, _Entry], key: str) -> bool | None:
    entry = picked.get(key)
    return bool(entry[0]) if entry is not None else None


def _emit(trace: list[Source] | None, prop: str, entry: _Entry | None) -> None:
    if trace is not None and entry is not None:
        trace.append(Source(prop, str(entry[1])))


class Resolver:
    """有效格式的唯一入口。持样式表与主题，按需解析段落/字符格式。"""

    __slots__ = ("styles", "theme")

    def __init__(self, styles: StyleTable, theme: ThemeFonts) -> None:
        self.styles = styles
        self.theme = theme

    def run(
        self,
        rpr: etree._Element | None,
        para_style_id: str | None = None,
        *,
        trace: list[Source] | None = None,
    ) -> RunFormat:
        """解析一个 run 的有效字符格式。``rpr`` 是该 run 自己的 ``w:rPr``。"""
        chain = self.styles.chain(para_style_id or self.styles.default_para)
        char_chain: list[StyleDef] = []
        if rpr is not None:
            rstyle = rpr.find(w("rStyle"))
            if rstyle is not None and rstyle.get(w("val")):
                char_chain = self.styles.chain(rstyle.get(w("val")))
        layers: list[_Layer] = [("docDefaults", self.styles.dd_rpr)]
        layers += [(self.styles.label(style), style.rpr) for style in chain]
        layers += [(f"字符样式:{style.id}", style.rpr) for style in char_chain]
        layers.append(("run", rpr))
        picked = _cascade_rpr(layers, self.theme)
        for prop in ("ea", "west", "size", "bold", "italic", "va"):
            _emit(trace, prop, picked.get(prop))
        return RunFormat(
            ea=_str(picked, "ea"),
            west=_str(picked, "west"),
            size=_float(picked, "size"),
            bold=_bool(picked, "bold"),
            italic=_bool(picked, "italic"),
            va=_str(picked, "va"),
        )

    def para(
        self,
        ppr: etree._Element | None,
        *,
        size_pt: float | None = None,
        trace: list[Source] | None = None,
    ) -> ParaFormat:
        """解析一个段落的有效段落格式。``ppr`` 是该段落的 ``w:pPr``。

        ``size_pt`` 是该段落的有效字号，仅用于把 ``@firstLine`` 之类的缇值换算成字符
        （``@firstLineChars`` 缺失时才用）。
        """
        style_id: str | None = None
        if ppr is not None:
            pstyle = ppr.find(w("pStyle"))
            if pstyle is not None and pstyle.get(w("val")):
                style_id = pstyle.get(w("val"))
        if not style_id:
            style_id = self.styles.default_para
        chain = self.styles.chain(style_id)
        layers: list[_Layer] = [("docDefaults", self.styles.dd_ppr)]
        layers += [(self.styles.label(style), style.ppr) for style in chain]
        layers.append(("run", ppr))
        picked = _cascade_ppr(layers)

        left = _chars(picked.get("left_chars"), picked.get("left_twips"), size_pt)
        right = _chars(picked.get("right_chars"), picked.get("right_twips"), size_pt)
        hang = _chars(picked.get("hanging_chars"), picked.get("hanging_twips"), size_pt)
        first = _chars(picked.get("first_line_chars"), picked.get("first_line_twips"), size_pt)
        if (first is None or not first[0]) and hang is not None:
            first = (-hang[0], hang[1])
        hanging = (-hang[0], hang[1]) if hang is not None else None

        rule_entry = picked.get("line_rule")
        line_entry = picked.get("line")
        rule_name = str(rule_entry[0]) if rule_entry is not None else None
        line_rule = LineRule(rule_name) if rule_name in _LINE_RULES else LineRule.AUTO
        if line_rule is LineRule.AUTO:
            line_multiple = float(line_entry[0]) / 240.0 if line_entry is not None else 1.0
            line_pt = None
        else:
            line_pt = float(line_entry[0]) / 20.0 if line_entry is not None else None
            line_multiple = None

        before = picked.get("space_before_twips")
        after = picked.get("space_after_twips")
        num_id = picked.get("num_id")
        numbering = None
        if num_id is not None and int(num_id[0]) != 0:
            ilvl = picked.get("num_ilvl")
            numbering = NumPr(num_id=int(num_id[0]), ilvl=int(ilvl[0]) if ilvl is not None else None)

        _emit(trace, "align", picked.get("align"))
        _emit(trace, "outline", picked.get("outline"))
        _emit(trace, "left_chars", left)
        _emit(trace, "right_chars", right)
        _emit(trace, "first_line_chars", first)
        _emit(trace, "hanging_chars", hanging)
        _emit(trace, "space_before_pt", before)
        _emit(trace, "space_after_pt", after)
        _emit(trace, "page_break_before", picked.get("page_break_before"))
        _emit(trace, "keep_with_next", picked.get("keep_with_next"))
        _emit(trace, "line_rule", rule_entry)
        _emit(trace, "line_multiple" if line_rule is LineRule.AUTO else "line_pt", line_entry)
        if numbering is not None:
            _emit(trace, "numbering", num_id)

        style = self.styles.by_id.get(style_id) if style_id is not None else None
        return ParaFormat(
            style_id=style_id,
            style_name=style.name if style is not None else None,
            align=_str(picked, "align"),
            outline=int(picked["outline"][0]) if "outline" in picked else None,
            line_rule=line_rule,
            line_multiple=line_multiple,
            line_pt=line_pt,
            first_line_chars=first[0] if first is not None else None,
            left_chars=left[0] if left is not None else None,
            right_chars=right[0] if right is not None else None,
            hanging_chars=hanging[0] if hanging is not None else None,
            space_before_pt=float(before[0]) / 20.0 if before is not None else None,
            space_after_pt=float(after[0]) / 20.0 if after is not None else None,
            numbering=numbering,
            page_break_before=_bool(picked, "page_break_before") or False,
            keep_with_next=_bool(picked, "keep_with_next"),
        )
