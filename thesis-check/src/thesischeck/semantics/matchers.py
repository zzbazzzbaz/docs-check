"""共享匹配器：识别锚点的唯一出处。

**识别与判定正交**（`docs/规则/README.md`「通用判定口径」第 7、8 条）：这里的判据只认形状，不管对错，
一律是规则的超集。写错由属性规则报，不由识别器过滤掉——`附录a` / `附录一` / `附录Ａ`
都必须先认下来，字号 / 层级 / 大小写是否正确交给规则。

`key_text` 是识别锚点的统一预处理：去掉全部空白与零宽空格，这样「第 一 章」与「第一章」
是同一个锚点。
"""

from __future__ import annotations

import re
from typing import cast

ZW = "\u200b"  # 零宽空格：WPS 偶尔插在文本前

_WS = re.compile(r"\s+")
_TOC_STYLE = re.compile(r"^toc\s*([123])$")
_HEADING_STYLE = re.compile(r"^heading\s*(\d+)$")
_CHAPTER = re.compile(r"^第([一二三四五六七八九十]+|\d+)章")
_APPENDIX_TITLE = "附录"
_APPENDIX_SUB = re.compile(r"^附录\S")
_FIGURE = re.compile(r"^图\s*(\d+)\s*-\s*(\d+)")
_TABLE = re.compile(r"^表\s*(\d+)\s*-\s*(\d+)")
_CONT_TABLE = re.compile(r"^续表\s*(\d+)\s*-\s*(\d+)")
_FORMULA_NO = re.compile(r"[（(](\d+)\s*-\s*(\d+)[）)]")
_NUMBER_START = re.compile(r"^[\[【［(（]?\s*\d+")
_CITATION = re.compile(r"^\[\s*(\d+(?:\s*[-–,，]\s*\d+)*)\s*\]$")
_KEYWORDS_C = re.compile(r"^关键词[:：]")
_KEYWORDS_E = re.compile(r"^keywords[:：]", re.IGNORECASE)
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ASCII_ALNUM = re.compile(r"[0-9A-Za-z]")

CN_NUM: dict[str, int] = {c: i for i, c in enumerate("一二三四五六七八九十", 1)}


def key_text(s: str | None) -> str:
    """识别锚点用：去掉全部空白（含全角空格）与零宽空格。"""
    return _WS.sub("", (s or "").replace(ZW, ""))


def toc_style_level(style: str | None) -> int | None:
    """样式名形如 `toc N` 时给出层级（1 起）；否则 `None`。层级只看样式名。"""
    m = _TOC_STYLE.match((style or "").strip().lower())
    return int(m.group(1)) if m else None


def is_toc_entry_style(style: str | None) -> bool:
    """样式名形如 `toc 1` / `toc 2` / `toc 3`（目录条目）。层级只看样式名。"""
    return toc_style_level(style) is not None


def heading_style_level(style: str | None) -> int | None:
    """样式名形如 `heading N` 时给出层级（1 起）；否则 `None`。"""
    m = _HEADING_STYLE.match((style or "").strip().lower())
    return int(m.group(1)) if m else None


def _cn_number(s: str) -> int | None:
    """中文数字转整数，支持 `一`…`十` / `十一` / `二十` / `二十一` 这些常见写法。"""
    if not s:
        return None
    if s == "十":
        return 10
    if "十" in s:
        head, _, tail = s.partition("十")
        tens = CN_NUM.get(head, 1)
        units = CN_NUM.get(tail, 0)
        return tens * 10 + units
    total = 0
    for ch in s:
        if ch not in CN_NUM:
            return None
        total = total * 10 + CN_NUM[ch]
    return total


def chapter_no(text: str | None) -> int | None:
    """一级标题的章号：中文数字（`第一章`）与阿拉伯数字（`第3章`）都支持。"""
    m = _CHAPTER.match(key_text(text))
    if m is None:
        return None
    group = m.group(1)
    return int(group) if group.isdigit() else _cn_number(group)


def is_chapter(text: str | None) -> bool:
    """文本形如 `第X章`（去空白后）：超集判据，不要求大纲级别。"""
    return _CHAPTER.match(key_text(text)) is not None


def is_appendix_title(text: str | None) -> bool:
    """附录标题：去空白后恰好是 `附录`。"""
    return key_text(text) == _APPENDIX_TITLE


def is_appendix_sub(text: str | None) -> bool:
    """附录子标题：`附录` 后还有非空白字符（`附录a` / `附录一` / `附录Ａ` 都算）。"""
    return _APPENDIX_SUB.match(key_text(text)) is not None


def figure_no(text: str | None) -> tuple[str, str] | None:
    m = _FIGURE.match(key_text(text))
    return (cast(str, m.group(1)), cast(str, m.group(2))) if m else None


def table_no(text: str | None) -> tuple[str, str] | None:
    """表题编号；`续表` 不算（由 `is_continued_table_caption` 单独认）。"""
    m = _TABLE.match(key_text(text))
    return (cast(str, m.group(1)), cast(str, m.group(2))) if m else None


def formula_no(text: str | None) -> tuple[str, str] | None:
    """公式编号 `(数字-数字)`；全角 / 半角括号都认。"""
    m = _FORMULA_NO.search(key_text(text))
    return (cast(str, m.group(1)), cast(str, m.group(2))) if m else None


def is_figure_caption(text: str | None) -> bool:
    return figure_no(text) is not None


def is_table_caption(text: str | None) -> bool:
    return table_no(text) is not None


def is_continued_table_caption(text: str | None) -> bool:
    return _CONT_TABLE.match(key_text(text)) is not None


def looks_like_number(text: str | None) -> bool:
    """段落开头形如编号：`[1]` / `【1】` / `（1）` / `1.`。

    `REF-10` 与 `REF-21` **共用本判据**，互斥由此天然成立，不需要任何抑制机制。
    """
    return _NUMBER_START.match((text or "").strip()) is not None


def is_keyword_line(text: str | None, *, english: bool) -> bool:
    """关键词行：中文区以 `关键词` + 冒号开头；英文区以 `Keywords` + 冒号开头（忽略大小写）。"""
    pattern = _KEYWORDS_E if english else _KEYWORDS_C
    return pattern.match(key_text(text)) is not None


def is_citation(text: str | None) -> bool:
    """引用标注文本形如 `[数字]` / `[1,2]` / `[1-3]`。

    **只看文本形状，不看是否上标**——是否上标由 `TXT-30` 判，识别与判定正交。
    """
    return _CITATION.match(key_text(text)) is not None


def citation_numbers(text: str | None) -> tuple[int, ...]:
    """把引用标注里的编号展开成一串整数（区间展开、逗号分隔）。"""
    m = _CITATION.match(key_text(text))
    if m is None:
        return ()
    out: list[int] = []
    for part in re.split(r"[,，]", m.group(1)):
        bounds = [int(x) for x in re.split(r"[-–]", part) if x.strip().isdigit()]
        if len(bounds) == 2:
            out.extend(range(bounds[0], bounds[1] + 1))
        else:
            out.extend(bounds)
    return tuple(out)


def has_cjk(text: str | None) -> bool:
    """含中文字符（用于「只判中文字符所在的 run」）。"""
    return _CJK.search(text or "") is not None


def has_ascii_alnum(text: str | None) -> bool:
    """含 ASCII 字母或数字（用于「只判字母数字，排除标点」）。"""
    return _ASCII_ALNUM.search(text or "") is not None
