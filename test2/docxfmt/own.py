"""自研侧：只用 zipfile + lxml 按 OOXML 级联合成「有效格式」。

级联顺序（低 → 高）
  字符：docDefaults.rPrDefault → 段落样式链 → 字符样式链 → run 直接 rPr
  段落：docDefaults.pPrDefault → 段落样式链 → 段落直接 pPr
段落没写 pStyle 时套「默认段落样式」（w:default="1"）。

作用域：正文 + 页眉 + 页脚；表格下钻、文本框不下钻（v1 既定口径）。
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

from .common import MC, OUT, TAG, a, corpus, local_attrs, m, w, wp, write_json

ZIP_DOC = "word/document.xml"
ZIP_STYLES = "word/styles.xml"
ZIP_THEME = "word/theme/theme1.xml"


def _onoff(el) -> bool | None:
    if el is None:
        return None
    v = el.get(w("val"))
    return True if v is None else v not in ("0", "false", "off", "no")


class StyleDef:
    __slots__ = ("id", "name", "type", "default", "based_on", "rPr", "pPr")

    def __init__(self, el):
        self.id = el.get(w("styleId"))
        self.type = el.get(w("type"))
        self.default = el.get(w("default")) in ("1", "true")
        n = el.find(w("name"))
        self.name = n.get(w("val")) if n is not None and n.get(w("val")) else ""
        b = el.find(w("basedOn"))
        self.based_on = b.get(w("val")) if b is not None and b.get(w("val")) else None
        self.rPr = el.find(w("rPr"))
        self.pPr = el.find(w("pPr"))


class StyleTable:
    def __init__(self, xml: bytes | None):
        self.by_id: dict[str, StyleDef] = {}
        self.dd_rPr = None
        self.dd_pPr = None
        if xml:
            root = etree.fromstring(xml)
            for el in root.iter(w("style")):
                s = StyleDef(el)
                if s.id:
                    self.by_id[s.id] = s
            dd = root.find(w("docDefaults"))
            if dd is not None:
                rd = dd.find(w("rPrDefault"))
                if rd is not None:
                    self.dd_rPr = rd.find(w("rPr"))
                pd = dd.find(w("pPrDefault"))
                if pd is not None:
                    self.dd_pPr = pd.find(w("pPr"))
        self.default_para = next(
            (s.id for s in self.by_id.values() if s.type == "paragraph" and s.default), None
        )

    def chain(self, style_id: str | None) -> list[StyleDef]:
        """样式链，祖先 → 自身；带环保护。"""
        out: list[StyleDef] = []
        seen: set[str] = set()
        while style_id and style_id not in seen:
            seen.add(style_id)
            s = self.by_id.get(style_id)
            if s is None:
                break
            out.append(s)
            style_id = s.based_on
        return list(reversed(out))


class ThemeFonts:
    def __init__(self, xml: bytes | None):
        self.slot: dict[str, str] = {}
        if not xml:
            return
        root = etree.fromstring(xml)
        scheme = root.find(f".//{a('fontScheme')}")
        if scheme is None:
            return
        for el in scheme:
            tag = TAG(el)
            if tag not in ("majorFont", "minorFont"):
                continue
            prefix = "major" if tag == "majorFont" else "minor"
            latin = el.find(a("latin"))
            ea = el.find(a("ea"))
            cs = el.find(a("cs"))
            if latin is not None and latin.get("typeface"):
                self.slot[prefix + "HAnsi"] = latin.get("typeface")
                self.slot[prefix + "Ascii"] = latin.get("typeface")
            if ea is not None and ea.get("typeface"):
                self.slot[prefix + "EastAsia"] = ea.get("typeface")
            if cs is not None and cs.get("typeface"):
                self.slot[prefix + "Bidi"] = cs.get("typeface")

    def resolve(self, theme_name: str | None) -> str | None:
        if not theme_name:
            return None
        v = self.slot.get(theme_name)
        if v:
            return v
        # 主题里 ea 为空时，WPS 回退到同一 scheme 的 latin（实测：minorEastAsia 空 → 用 minorFont 的 latin 等线）
        if theme_name.endswith("EastAsia"):
            return self.slot.get(theme_name[: -len("EastAsia")] + "HAnsi")
        return None


# ascii/asciiTheme 是同一个槽的两种互斥写法，近层写了主题引用就顶掉远层的显式值
FONT_SLOTS = (("ascii", "asciiTheme"), ("hAnsi", "hAnsiTheme"),
              ("eastAsia", "eastAsiaTheme"), ("cs", "cstheme"))


def merge_rpr(chain: list) -> dict:
    res = {
        "slots": {}, "sz": None, "b": None, "i": None,
        "u": None, "va": None, "rstyle": None,
    }
    for pr in chain:
        if pr is None:
            continue
        rf = pr.find(w("rFonts"))
        if rf is not None:
            d = local_attrs(rf)
            for plain, themed in FONT_SLOTS:
                if plain in d:
                    res["slots"][plain] = (False, d[plain])
                elif themed in d:
                    res["slots"][plain] = (True, d[themed])
        sz = pr.find(w("sz"))
        if sz is not None and sz.get(w("val")):
            res["sz"] = int(sz.get(w("val"))) / 2.0
        for tag, key in (("b", "b"), ("i", "i")):
            el = pr.find(w(tag))
            if el is not None:
                res[key] = _onoff(el)
        u = pr.find(w("u"))
        if u is not None:
            res["u"] = u.get(w("val"), "single")
        va = pr.find(w("vertAlign"))
        if va is not None:
            res["va"] = va.get(w("val"))
        rs = pr.find(w("rStyle"))
        if rs is not None and rs.get(w("val")):
            res["rstyle"] = rs.get(w("val"))
    return res


def merge_ppr(chain: list) -> dict:
    res = {
        "style": None, "jc": None, "il": None, "ir": None, "ifl": None, "iflc": None,
        "ihang": None, "sb": None, "sa": None, "sbl": None, "sal": None,
        "line": None, "rule": None, "outline": None, "pbb": None, "keep": None,
        "num_id": None, "num_ilvl": None,
    }
    for pr in chain:
        if pr is None:
            continue
        ps = pr.find(w("pStyle"))
        if ps is not None and ps.get(w("val")):
            res["style"] = ps.get(w("val"))
        jc = pr.find(w("jc"))
        if jc is not None and jc.get(w("val")):
            res["jc"] = jc.get(w("val"))
        ind = pr.find(w("ind"))
        if ind is not None:
            d = local_attrs(ind)
            for key, name in (
                ("left", "il"), ("start", "il"), ("right", "ir"), ("end", "ir"),
                ("firstLine", "ifl"), ("firstLineChars", "iflc"),
                ("hanging", "ihang"), ("hangingChars", "ihangc"),
            ):
                if key in d:
                    res[name] = float(d[key])
        sp = pr.find(w("spacing"))
        if sp is not None:
            d = local_attrs(sp)
            for key, name in (
                ("before", "sb"), ("after", "sa"), ("beforeLines", "sbl"),
                ("afterLines", "sal"), ("line", "line"), ("lineRule", "rule"),
            ):
                if key in d:
                    res[name] = d[key]
        ol = pr.find(w("outlineLvl"))
        if ol is not None and ol.get(w("val")) is not None:
            res["outline"] = int(ol.get(w("val")))
        pbb = pr.find(w("pageBreakBefore"))
        if pbb is not None:
            res["pbb"] = _onoff(pbb)
        kn = pr.find(w("keepNext"))
        if kn is not None:
            res["keep"] = _onoff(kn)
        np = pr.find(w("numPr"))
        if np is not None:
            nid = np.find(w("numId"))
            ilvl = np.find(w("ilvl"))
            if nid is not None and nid.get(w("val")) is not None:
                # numId=0 表示「取消编号」（ECMA-376），等价于没有编号，不能当成有编号
                res["num_id"] = int(nid.get(w("val"))) or None
            if ilvl is not None and ilvl.get(w("val")) is not None:
                res["num_ilvl"] = int(ilvl.get(w("val")))
    return res


def iter_paragraphs(node, in_table: bool = False) -> list[tuple]:
    """文档顺序取段落 → [(元素, 是否在表格内, 是否表格行末)]。

    表格下钻、sdt 下钻、文本框不下钻。
    行末标出来是因为 **WPS 的 Paragraphs 会在每个表格行末多一个空段落**，
    比对时要靠这个标记把多出来的补回去（WPS 侧取不到 Range.Information）。
    """
    out: list[tuple] = []
    for child in node:
        if not isinstance(child.tag, str):
            continue
        tag = TAG(child)
        if tag == "p":
            out.append((child, in_table, False))
        elif tag == "tbl":
            for tr in child.findall(w("tr")):
                mark = len(out)
                for tc in tr.findall(w("tc")):
                    out.extend(iter_paragraphs(tc, True))
                if len(out) > mark:
                    el, _, _ = out[-1]
                    out[-1] = (el, True, True)
        elif tag == "sdt":
            content = child.find(w("sdtContent"))
            if content is not None:
                out.extend(iter_paragraphs(content, in_table))
    return out


def _inside_txbx(el, stop) -> bool:
    anc = el.getparent()
    while anc is not None and anc is not stop:
        if anc.tag == w("txbxContent"):
            return True
        anc = anc.getparent()
    return False


def _in_fallback(el, stop) -> bool:
    """在 mc:Fallback 里吗？Word 用 AlternateContent 同时写 DrawingML 与 VML 两份，是同一个对象。"""
    anc = el.getparent()
    while anc is not None and anc is not stop:
        if anc.tag == f"{{{MC}}}Fallback":
            return True
        anc = anc.getparent()
    return False


def para_text(p) -> str:
    """可见文本：正文文字 + 公式文字，制表符记 \\t、换行记 \\n；域代码与文本框不收。

    两个坑：
      * w:tab 有两处含义——w:r 里的是制表符，w:pPr/w:tabs 里的是**制表位定义**；
      * m:t（公式文字）也是可见文本（WPS 的 Range.Text 就含它），但它属于 m:r，
        所以按 m:t 定位到的字符没有对应的 w:r，字符级属性无从采样。
    """
    parts = []
    for el in p.iter():
        if not isinstance(el.tag, str) or _inside_txbx(el, p):
            continue
        if el.tag == w("t") or el.tag == m("t"):
            if el.text:
                parts.append(el.text)
        elif el.tag == w("tab") and TAG(el.getparent()) == "r":
            parts.append("\t")
        elif el.tag in (w("br"), w("cr")) and TAG(el.getparent()) == "r":
            parts.append("\n")
        elif el.tag == w("noBreakHyphen"):
            parts.append("\u2011")          # 不可断开连字符（WPS 的 Range.Text 记成 \x1e）
        elif el.tag == w("softHyphen"):
            parts.append("\u00ad")          # 可选连字符
    return "".join(parts)


def para_runs(p) -> list:
    return [r for r in p.iter(w("r")) if not _inside_txbx(r, p)]


_CTRL = re.compile(r"[\r\n\v\f\a\x07\x0c\x01\x02\x05\x0e\x13\x14\x15]")
FORMULA_NO = re.compile(r"\((\d+)\s*-\s*(\d+)\)")


def line_breaks(p) -> int:
    """段内手动换行数（`w:br` 不带 type 或 textWrapping、以及 `w:cr`）。

    `REF-21`「一条文献占且仅占 1 个段落（不手动换行）」判的就是这个。
    分页/分栏的 `w:br` 不算行内换行。
    """
    n = 0
    for el in p.iter():
        if not isinstance(el.tag, str) or _inside_txbx(el, p):
            continue
        if el.tag == w("cr"):
            n += 1
        elif el.tag == w("br") and (el.get(w("type")) or "textWrapping") == "textWrapping":
            n += 1
    return n


def _pict_floating(pict) -> bool:
    """VML 图形是浮动的吗。

    WPS 把浮动的算 `Shape`、内嵌的算 `InlineShape`（实测），判据是定位样式。
    """
    for sh in pict.iter():
        if not isinstance(sh.tag, str):
            continue
        style = sh.get("style") or ""
        if "mso-position" in style or "position:absolute" in style:
            return True
        if TAG(sh) == "wrap":
            return True
    return False


def object_counts(p) -> dict:
    """段落里的对象计数（文本框内的不算）。

    三个坑都是实测撞出来的：
      * **公式**：`m:oMathPara` 只是 `m:oMath` 的容器，同时数会重复（实测 53 vs 37），只数 `m:oMath`；
      * **`mc:AlternateContent`**：Word 会同时写 DrawingML（`mc:Choice`）与 VML（`mc:Fallback`）两份，
        是**同一个对象**，`mc:Fallback` 里的要跳过（实测 4 vs 2）；
      * **独立 VML 图形（`w:pict`）**：按定位样式分内嵌/浮动，WPS 的口径与之一致。

    分类对齐 WPS：`inline`+`pict_inline`+`ole` ↔ `InlineShapes`，`anchor`+`pict_float` ↔ `Shapes`。
    规则里「图」的定义是 `w:drawing`（不含 VML），「公式」是 `w:object` 或 `m:oMath`。
    """
    n = {"inline": 0, "anchor": 0, "pict_inline": 0, "pict_float": 0, "ole": 0, "omath": 0}
    for el in p.iter():
        if not isinstance(el.tag, str) or _inside_txbx(el, p) or _in_fallback(el, p):
            continue
        if el.tag == wp("inline"):
            n["inline"] += 1
        elif el.tag == wp("anchor"):
            n["anchor"] += 1
        elif el.tag == w("pict"):
            n["pict_float" if _pict_floating(el) else "pict_inline"] += 1
        elif el.tag == w("object"):
            n["ole"] += 1
        elif el.tag == m("oMath"):
            n["omath"] += 1
    return n


class OwnDoc:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.z = zipfile.ZipFile(self.path)
        self.styles = StyleTable(self._read(ZIP_STYLES))
        self.theme = ThemeFonts(self._read(ZIP_THEME))

    def _read(self, name: str) -> bytes | None:
        try:
            return self.z.read(name)
        except KeyError:
            return None

    def _font_slots(self, slots: dict) -> tuple[str | None, str | None]:
        def resolve(slot: str) -> str | None:
            entry = slots.get(slot)
            if not entry:
                return None
            is_theme, value = entry
            return self.theme.resolve(value) if is_theme else value

        return resolve("ascii") or resolve("hAnsi"), resolve("eastAsia")

    def para_record(self, p, story: str, ordinal: int,
                    in_table: bool = False, row_end: bool = False) -> dict:
        full_text = para_text(p)
        oc = object_counts(p)
        direct_ppr = p.find(w("pPr"))
        pstyle = None
        if direct_ppr is not None:
            ps = direct_ppr.find(w("pStyle"))
            if ps is not None and ps.get(w("val")):
                pstyle = ps.get(w("val"))
        style_id = pstyle or self.styles.default_para
        chain = self.styles.chain(style_id)

        ppr = merge_ppr([self.styles.dd_pPr] + [s.pPr for s in chain] + [direct_ppr])
        style_name = self.styles.by_id[style_id].name if style_id in self.styles.by_id else None

        pexplicit: dict[str, object] = {}
        if direct_ppr is not None:
            _jc = direct_ppr.find(w("jc"))
            if _jc is not None and _jc.get(w("val")):
                pexplicit["align"] = _jc.get(w("val"))
            _ind = direct_ppr.find(w("ind"))
            if _ind is not None:
                ia = local_attrs(_ind)
                if "firstLine" in ia:
                    pexplicit["ind_first"] = float(ia["firstLine"]) / 20.0
                elif "firstLineChars" in ia:
                    pexplicit["ind_first_chars"] = float(ia["firstLineChars"]) / 100.0
            _sp = direct_ppr.find(w("spacing"))
            if _sp is not None:
                sa = local_attrs(_sp)
                if "line" in sa:
                    pexplicit["line"] = float(sa["line"]) / 20.0
            _ol = direct_ppr.find(w("outlineLvl"))
            if _ol is not None and _ol.get(w("val")) is not None:
                pexplicit["outline"] = int(_ol.get(w("val")))

        runs = []
        for r in para_runs(p):
            direct_rpr = r.find(w("rPr"))
            rstyle = None
            if direct_rpr is not None:
                rs = direct_rpr.find(w("rStyle"))
                if rs is not None and rs.get(w("val")):
                    rstyle = rs.get(w("val"))
            char_chain = self.styles.chain(rstyle) if rstyle else []
            rpr = merge_rpr(
                [self.styles.dd_rPr]
                + [s.rPr for s in chain]
                + [s.rPr for s in char_chain]
                + [direct_rpr]
            )
            ascii_, ea = self._font_slots(rpr["slots"])
            text = "".join(t.text or "" for t in r.iter(w("t")) if not _inside_txbx(t, p))
            explicit: dict[str, object] = {}
            if direct_rpr is not None:
                rf = direct_rpr.find(w("rFonts"))
                if rf is not None:
                    if rf.get(w("ascii")):
                        explicit["ascii"] = rf.get(w("ascii"))
                    if rf.get(w("eastAsia")):
                        explicit["ea"] = rf.get(w("eastAsia"))
                _sz = direct_rpr.find(w("sz"))
                if _sz is not None and _sz.get(w("val")):
                    explicit["size"] = int(_sz.get(w("val"))) / 2.0
                if direct_rpr.find(w("b")) is not None:
                    explicit["bold"] = _onoff(direct_rpr.find(w("b")))
            runs.append(
                {
                    "text": text,
                    "size": rpr["sz"],
                    "bold": rpr["b"],
                    "italic": rpr["i"],
                    "underline": rpr["u"],
                    "va": rpr["va"],
                    "ascii": ascii_,
                    "ea": ea,
                    "rstyle": rpr["rstyle"],
                    "explicit": explicit,
                }
            )

        def pt(v):
            return None if v is None else float(v) / 20.0

        # 公式编号 `(章号-序号)` 在哪里，以及它所在 run 的字体/字号
        # （公式段落里公式本体在前，第一个 ASCII run 往往不是编号，所以要按位置采样）
        fno = None
        m = FORMULA_NO.search(full_text)
        if m is not None:
            idx = m.start() + 1
            pos = 0
            for i, r in enumerate(para_runs(p)):
                n = len(para_text(r))
                if pos <= idx < pos + n and i < len(runs):
                    fno = {"no": f"{m.group(1)}-{m.group(2)}", "ascii": runs[i]["ascii"],
                           "ea": runs[i]["ea"], "size": runs[i]["size"]}
                    break
                pos += n

        # 行距：文档从没写过 spacing 时，Word/WPS 的有效值是单倍（w:line=240 lineRule=auto）
        line_pt = pt(ppr["line"])
        line_rule = ppr["rule"]
        if line_pt is None:
            line_pt, line_rule = 12.0, "auto"

        # 首行缩进的有效值，口径按 WPS 实测：
        #   firstLineChars > 0 → 字符数 × 段落第一个 run 的字号（第一个 run 即便是空的也算）
        #   否则用 firstLine 缇值（heading 1 里 firstLineChars=0、firstLine=640 → 32pt）
        # 悬挂缩进在 Word 对象模型里就是**负的**首行缩进（WPS 的 FirstLineIndent 也报负值）
        size = next((r["size"] for r in runs if r["size"]), None)
        if size is None and direct_ppr is not None:
            _mark = direct_ppr.find(w("rPr"))
            _sz = _mark.find(w("sz")) if _mark is not None else None
            if _sz is not None and _sz.get(w("val")):
                size = int(_sz.get(w("val"))) / 2.0

        def chars_pt(hundredths):  # firstLineChars / hangingChars 的单位是 1/100 字符
            if hundredths and size:
                return round(hundredths / 100.0 * size, 2)
            return None

        first_twips_pt = pt(ppr["ifl"])
        first_chars = None if not ppr["iflc"] else ppr["iflc"] / 100.0
        first_pt = first_twips_pt
        if first_chars is not None:
            first_pt = chars_pt(ppr["iflc"]) or first_pt
        if not first_pt:
            hang = chars_pt(ppr.get("ihangc")) or pt(ppr["ihang"])
            if hang:
                first_pt = -hang

        has_page_break = bool(ppr["pbb"]) or any(
            br.get(w("type")) == "page"
            for br in p.iter(w("br"))
            if not _inside_txbx(br, p)
        )

        return {
            "story": story,
            "ordinal": ordinal,
            "text": full_text,
            "in_table": in_table,
            "row_end": row_end,
            # 文本口径（与 WPS 可比）：无可见文字、无内嵌图形
            "text_empty": not _CTRL.sub("", full_text) and oc["inline"] == 0,
            # 规则口径：无文字、无图片（含浮动）、无公式（比前者严，WPS 表达不了"无浮动图"）
            "is_empty": not _CTRL.sub("", full_text) and not any(oc.values()),
            # 对象计数与派生标记（图 = w:drawing；公式 = w:object 或 m:oMath）
            "objects": oc,
            "has_figure": (oc["inline"] + oc["anchor"]) > 0,
            "has_formula": (oc["ole"] + oc["omath"]) > 0,
            # 本段起始的域代码（dump 时填）
            "field_codes": [],
            "line_breaks": line_breaks(p),
            "formula_no": fno,
            "style_id": style_id,
            "style_name": style_name,
            "align": ppr["jc"] or "left",
            "outline": ppr["outline"],
            "page_break_before": bool(ppr["pbb"]),
            "has_page_break": has_page_break,
            "sect_break": direct_ppr is not None and direct_ppr.find(w("sectPr")) is not None,
            "keep_with_next": bool(ppr["keep"]),
            "ind_left": pt(ppr["il"]),
            "ind_right": pt(ppr["ir"]),
            "ind_first": first_pt,
            "ind_first_chars": first_chars,
            "ind_first_twips_pt": first_twips_pt,
            "ind_hanging": pt(ppr["ihang"]),
            "sp_before": pt(ppr["sb"]),
            "sp_after": pt(ppr["sa"]),
            "sp_before_lines": None if ppr["sbl"] is None else float(ppr["sbl"]) / 100.0,
            "sp_after_lines": None if ppr["sal"] is None else float(ppr["sal"]) / 100.0,
            "line": line_pt,
            "line_rule": line_rule,
            "num_id": ppr["num_id"],
            "explicit": pexplicit,
            "runs": runs,
        }

    def fields(self, body) -> list[dict]:
        """文档正文里的域。

        两类：
          * **真实域**：`w:fldChar` begin/end 配成对（`w:fldSimple` 记成单段），代码取 `w:instrText` 的第一个词；
          * **合成域**（`synthetic: True`）：WPS 的 `doc.Fields` 还会把 `w:object`→`EMBED`、
            正文 `w:hyperlink`→`HYPERLINK`、内联 VML 文本框→`SHAPE` 也算成域。
            为了能逐项对账，这里也记一份；**规则判定应该只用真实域**。

        `para`/`end_para` 是段落号（0 起），TOC 域的那对就是「目录区」范围。
        """
        out: list[dict] = []
        stack: list[dict] = []
        paras = list(iter_paragraphs(body))
        for pi, (p, _, _) in enumerate(paras):
            for el in p.iter():
                if not isinstance(el.tag, str) or _inside_txbx(el, p) or _in_fallback(el, p):
                    continue
                if el.tag == w("fldChar"):
                    t = el.get(w("fldCharType"))
                    if t == "begin":
                        stack.append({"code": None, "para": pi, "end_para": pi,
                                      "depth": len(stack), "synthetic": False})
                    elif t == "end" and stack:
                        f = stack.pop()
                        f["end_para"] = pi
                        out.append(f)
                elif el.tag == w("instrText") and stack and stack[-1]["code"] is None:
                    text = (el.text or "").strip()
                    if text:
                        stack[-1]["code"] = text.split()[0].upper()
                elif el.tag == w("fldSimple"):
                    instr = (el.get(w("instr")) or "").strip()
                    if instr:
                        out.append({"code": instr.split()[0].upper(), "para": pi,
                                    "end_para": pi, "depth": len(stack), "synthetic": False})

        for pi, (p, _, _) in enumerate(paras):
            content_here = bool(para_text(p)) or any(object_counts(p).values())
            for el in p.iter():
                if not isinstance(el.tag, str) or _inside_txbx(el, p) or _in_fallback(el, p):
                    continue
                code = None
                if el.tag == w("object"):
                    code = "EMBED"
                elif el.tag == w("hyperlink"):
                    code = "HYPERLINK"
                elif el.tag == w("pict"):
                    code = "SHAPE"          # 浮动与否都会被 WPS 合成为 SHAPE 域，实测 15/15
                if code:
                    out.append({"code": code, "para": pi, "end_para": pi,
                                "depth": None, "synthetic": True})

        # 域的「内容结束段」：结束标记所在段若只有标记、没有别的内容，内容其实结束在上一段
        # （WPS 的 Field.Result.End 就是这么给的，TOC 域恒定差 1 的来源）
        for f in out:
            p = paras[f["end_para"]][0]
            has = bool(para_text(p)) or any(object_counts(p).values())
            f["end_para_content"] = f["end_para"] if has else max(f["para"], f["end_para"] - 1)
        return sorted(out, key=lambda f: (f["para"], f["code"]))

    def dump(self) -> dict:
        out = {"path": str(self.path), "tool": "own", "paragraphs": [], "meta": {}}

        doc = etree.fromstring(self.z.read(ZIP_DOC))
        # WPS 的 Tables.Count 只数顶层表格（嵌套表格不单独计，实测 6 vs 5）
        out["meta"]["n_tables"] = sum(
            1 for el in doc.iter(w("tbl"))
            if not _inside_txbx(el, doc) and not _in_fallback(el, doc)
            and not any(a.tag == w("tbl") for a in el.iterancestors())
        )
        body = doc.find(w("body"))
        for i, (p, in_tbl, row_end) in enumerate(iter_paragraphs(body)):
            out["paragraphs"].append(self.para_record(p, "main", i, in_tbl, row_end))

        fields = self.fields(body)
        out["fields"] = fields
        for f in fields:
            # 每段只挂**真实域**的代码（合成域是 WPS 的口径，供对账用，别污染规则）
            if not f["synthetic"] and 0 <= f["para"] < len(out["paragraphs"]):
                out["paragraphs"][f["para"]]["field_codes"].append(f["code"])

        for story, pattern in (("header", "word/header"), ("footer", "word/footer")):
            parts = sorted(
                n for n in self.z.namelist() if n.startswith(pattern) and n.endswith(".xml")
            )
            k = 0
            for part in parts:
                root = etree.fromstring(self.z.read(part))
                for p, in_tbl, row_end in iter_paragraphs(root):
                    rec = self.para_record(p, story, k, in_tbl, row_end)
                    rec["part"] = part
                    out["paragraphs"].append(rec)
                    k += 1

        out["meta"]["n_paragraphs"] = len(out["paragraphs"])
        return out


def dump(path) -> dict:
    return OwnDoc(path).dump()


def main() -> None:
    args = sys.argv[1:] or [str(p) for p in corpus()]
    for arg in args:
        p = Path(arg)
        write_json(OUT / f"{p.stem}.own.json", dump(p))
        print("own:", p.name)


if __name__ == "__main__":
    main()
