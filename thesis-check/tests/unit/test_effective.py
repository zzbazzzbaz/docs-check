"""有效格式：级联、归一、字体分槽、按需回溯。

全部用手写的最小 XML 片段构造，不读真实文档，测试快且与外部文件无关。
每条已知坑（§附录 C）都有一个用例。
"""

import pytest
from lxml import etree

from thesischeck.parse.effective import (
    ParaFormat,
    Resolver,
    RunFormat,
    Source,
    StyleTable,
    ThemeFonts,
    source_of,
)
from thesischeck.parse.model import LineRule, NumPr

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = f'xmlns:w="{W_NS}" xmlns:a="{A_NS}"'

DOC_DEFAULTS = """
<w:docDefaults>
  <w:rPrDefault>
    <w:rPr><w:rFonts w:ascii="Times New Roman"/><w:sz w:val="20"/></w:rPr>
  </w:rPrDefault>
  <w:pPrDefault><w:pPr/></w:pPrDefault>
</w:docDefaults>
"""

NORMAL = """
<w:style w:type="paragraph" w:default="1" w:styleId="Normal">
  <w:name w:val="Normal"/>
  <w:pPr><w:jc w:val="both"/></w:pPr>
  <w:rPr><w:sz w:val="24"/></w:rPr>
</w:style>
"""

NORMAL_BARE = """
<w:style w:type="paragraph" w:default="1" w:styleId="Normal">
  <w:name w:val="Normal"/>
</w:style>
"""

HEADING1 = """
<w:style w:type="paragraph" w:styleId="Heading1">
  <w:name w:val="heading 1"/>
  <w:basedOn w:val="Normal"/>
  <w:pPr><w:jc w:val="center"/><w:outlineLvl w:val="0"/></w:pPr>
  <w:rPr><w:b/><w:sz w:val="32"/></w:rPr>
</w:style>
"""

EMPHASIS = """
<w:style w:type="character" w:styleId="Emphasis">
  <w:name w:val="Emphasis"/>
  <w:rPr><w:i/><w:sz w:val="26"/></w:rPr>
</w:style>
"""

THEME_LATIN_ONLY = """
<a:fontScheme name="Office">
  <a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/></a:majorFont>
  <a:minorFont><a:latin typeface="等线"/><a:ea typeface=""/></a:minorFont>
</a:fontScheme>
"""


def make(styles_body: str, theme_body: str | None = None) -> Resolver:
    styles = etree.fromstring(f"<w:styles {NS}>{styles_body}</w:styles>".encode())
    theme_root = None
    if theme_body is not None:
        theme_root = etree.fromstring(
            f'<a:theme xmlns:a="{A_NS}"><a:themeElements>{theme_body}</a:themeElements></a:theme>'.encode()
        )
    return Resolver(StyleTable(styles), ThemeFonts(theme_root))


def rpr(inner: str = "") -> etree._Element:
    return etree.fromstring(f"<w:rPr {NS}>{inner}</w:rPr>".encode())


def ppr(inner: str = "") -> etree._Element:
    return etree.fromstring(f"<w:pPr {NS}>{inner}</w:pPr>".encode())


RESOLVER = make(DOC_DEFAULTS + NORMAL + HEADING1 + EMPHASIS)


# ── 级联（每个层级一个用例） ─────────────────────────────────────


def test_docdefaults_supplies_value_when_nothing_else_does() -> None:
    resolver = make(DOC_DEFAULTS + NORMAL_BARE)
    fmt = resolver.run(None)
    assert fmt.size == 10.0
    trace: list[Source] = []
    resolver.run(None, trace=trace)
    assert source_of(trace, "size") == "docDefaults"


def test_default_paragraph_style_is_used_when_pstyle_missing() -> None:
    trace: list[Source] = []
    fmt = RESOLVER.run(None, trace=trace)
    assert fmt.size == 12.0
    assert source_of(trace, "size") == "默认段落样式"


def test_paragraph_style_chain_beats_default_style() -> None:
    trace: list[Source] = []
    fmt = RESOLVER.run(None, "Heading1", trace=trace)
    assert (fmt.size, fmt.bold) == (16.0, True)
    assert source_of(trace, "size") == "样式:heading 1"
    assert source_of(trace, "bold") == "样式:heading 1"


def test_character_style_beats_paragraph_style() -> None:
    trace: list[Source] = []
    fmt = RESOLVER.run(rpr('<w:rStyle w:val="Emphasis"/>'), "Normal", trace=trace)
    assert (fmt.size, fmt.italic) == (13.0, True)
    assert source_of(trace, "size") == "字符样式:Emphasis"


def test_run_direct_beats_everything() -> None:
    trace: list[Source] = []
    fmt = RESOLVER.run(rpr('<w:sz w:val="28"/>'), "Heading1", trace=trace)
    assert fmt.size == 14.0
    assert source_of(trace, "size") == "run"


def test_basedon_chain_walk_and_cycle_protection() -> None:
    cycle = """
    <w:style w:type="paragraph" w:styleId="CycleA"><w:name w:val="Cycle A"/><w:basedOn w:val="CycleB"/></w:style>
    <w:style w:type="paragraph" w:styleId="CycleB">
      <w:name w:val="Cycle B"/><w:basedOn w:val="CycleA"/><w:rPr><w:sz w:val="30"/></w:rPr>
    </w:style>
    """
    resolver = make(DOC_DEFAULTS + NORMAL + cycle)
    trace: list[Source] = []
    fmt = resolver.run(None, "CycleA", trace=trace)
    assert fmt.size == 15.0
    assert source_of(trace, "size") == "样式:Cycle B"


# ── 字体分槽与主题字体 ───────────────────────────────────────────


def test_abstract_run_keeps_western_font_inherited_from_normal() -> None:
    """run 只写 eastAsia 时，ascii 必须继承样式链上的 Times New Roman（附录 C 第 1 条）。"""
    styles = """
    <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri"/></w:rPr></w:rPrDefault></w:docDefaults>
    <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
      <w:name w:val="Normal"/><w:rPr><w:rFonts w:ascii="Times New Roman"/></w:rPr>
    </w:style>
    """
    resolver = make(styles)
    trace: list[Source] = []
    fmt = resolver.run(rpr('<w:rFonts w:eastAsia="宋体"/>'), trace=trace)
    assert fmt.ea == "宋体"
    assert fmt.west == "Times New Roman"
    assert source_of(trace, "ea") == "run"
    assert source_of(trace, "west") == "默认段落样式"


def test_font_slots_are_independent() -> None:
    fmt = RESOLVER.run(rpr('<w:rFonts w:ascii="Arial" w:eastAsia="黑体"/>'))
    assert (fmt.west, fmt.ea) == ("Arial", "黑体")


def test_western_font_falls_back_to_hansi() -> None:
    # ascii 槽整个缺失时才退回 hAnsi；若任一远层设了 ascii，就以 ascii 为准
    fmt = make(NORMAL_BARE).run(rpr('<w:rFonts w:hAnsi="Arial"/>'))
    assert fmt.west == "Arial"


def test_nearer_theme_reference_replaces_farther_explicit_font() -> None:
    resolver = make(DOC_DEFAULTS + NORMAL, THEME_LATIN_ONLY)
    trace: list[Source] = []
    fmt = resolver.run(rpr('<w:rFonts w:asciiTheme="minorAscii"/>'), trace=trace)
    assert fmt.west == "等线"
    assert source_of(trace, "west") == "主题字体"


def test_theme_eastasia_falls_back_to_same_scheme_latin() -> None:
    resolver = make(DOC_DEFAULTS + NORMAL, THEME_LATIN_ONLY)
    fmt = resolver.run(rpr('<w:rFonts w:asciiTheme="minorAscii" w:eastAsiaTheme="minorEastAsia"/>'))
    assert (fmt.west, fmt.ea) == ("等线", "等线")


# ── 单位归一 ─────────────────────────────────────────────────────


def test_size_is_half_points() -> None:
    assert RESOLVER.run(rpr('<w:sz w:val="21"/>')).size == 10.5


def test_spacing_twips_become_points() -> None:
    fmt = RESOLVER.para(ppr('<w:spacing w:before="240" w:after="120"/>'))
    assert (fmt.space_before_pt, fmt.space_after_pt) == (12.0, 6.0)


def test_firstlinechars_is_hundredths_of_a_character() -> None:
    fmt = RESOLVER.para(ppr('<w:ind w:firstLineChars="250"/>'))
    assert fmt.first_line_chars == 2.5


def test_firstlinechars_wins_over_firstline_twips() -> None:
    """缇值只是缓存；两者冲突时以 firstLineChars 为准（附录 C 第 18 条）。"""
    fmt = RESOLVER.para(ppr('<w:ind w:firstLineChars="200" w:firstLine="640"/>'), size_pt=12.0)
    assert fmt.first_line_chars == 2.0


def test_firstline_twips_fallback_uses_font_size() -> None:
    """@firstLine 缺失 firstLineChars 时，缇值 ÷ 20 ÷ 字号（小四下 480 = 2 字符）。"""
    fmt = RESOLVER.para(ppr('<w:ind w:firstLine="480"/>'), size_pt=12.0)
    assert fmt.first_line_chars == 2.0


# ── 已知坑 ───────────────────────────────────────────────────────


def test_missing_line_spacing_defaults_to_single() -> None:
    fmt = RESOLVER.para(ppr())
    assert fmt.line_rule is LineRule.AUTO
    assert fmt.line_multiple == 1.0
    assert fmt.line_pt is None


def test_line_auto_is_a_multiple() -> None:
    fmt = RESOLVER.para(ppr('<w:spacing w:line="360" w:lineRule="auto"/>'))
    assert fmt.line_rule is LineRule.AUTO
    assert fmt.line_multiple == 1.5
    assert fmt.line_pt is None


def test_line_rule_absent_defaults_to_auto() -> None:
    fmt = RESOLVER.para(ppr('<w:spacing w:line="360"/>'))
    assert (fmt.line_rule, fmt.line_multiple) == (LineRule.AUTO, 1.5)


def test_line_exact_is_points_not_a_multiple() -> None:
    fmt = RESOLVER.para(ppr('<w:spacing w:line="360" w:lineRule="exact"/>'))
    assert fmt.line_rule is LineRule.EXACT
    assert fmt.line_pt == 18.0
    assert fmt.line_multiple is None


def test_line_at_least_is_flagged() -> None:
    fmt = RESOLVER.para(ppr('<w:spacing w:line="360" w:lineRule="atLeast"/>'))
    assert fmt.line_rule is LineRule.AT_LEAST


def test_hanging_indent_stays_negative() -> None:
    """悬挂缩进是负的首行缩进，不许归一成 0（附录 C 第 14 条）。"""
    fmt = RESOLVER.para(ppr('<w:ind w:hanging="240"/>'), size_pt=12.0)
    assert fmt.hanging_chars == -1.0
    assert fmt.first_line_chars == -1.0


def test_numid_zero_cancels_numbering() -> None:
    """numId=0 是显式取消编号，不是"没设置"（附录 C 第 15 条）。"""
    fmt = RESOLVER.para(ppr('<w:numPr><w:numId w:val="0"/><w:ilvl w:val="0"/></w:numPr>'))
    assert fmt.numbering is None


def test_numid_nonzero_is_effective_numbering() -> None:
    fmt = RESOLVER.para(ppr('<w:numPr><w:numId w:val="5"/><w:ilvl w:val="1"/></w:numPr>'))
    assert fmt.numbering == NumPr(num_id=5, ilvl=1)


def test_numbering_is_inherited_through_the_style_chain() -> None:
    styles = """
    <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
      <w:name w:val="Normal"/>
      <w:pPr><w:numPr><w:numId w:val="2"/></w:numPr></w:pPr>
    </w:style>
    """
    trace: list[Source] = []
    fmt = make(styles).para(ppr(), trace=trace)
    assert fmt.numbering == NumPr(num_id=2, ilvl=None)
    assert source_of(trace, "numbering") == "默认段落样式"


@pytest.mark.parametrize(
    ("attr", "expected"),
    [
        ("", True),
        (' w:val="1"', True),
        (' w:val="0"', False),
        (' w:val="false"', False),
        (' w:val="off"', False),
        (' w:val="no"', False),
    ],
)
def test_onoff_val_semantics(attr: str, expected: bool) -> None:
    assert RESOLVER.run(rpr(f"<w:b{attr}/>")).bold is expected


# ── 段落其它属性与回溯 ───────────────────────────────────────────


def test_align_outline_page_break_and_keep() -> None:
    fmt = RESOLVER.para(
        ppr('<w:jc w:val="right"/><w:outlineLvl w:val="2"/><w:pageBreakBefore/><w:keepNext w:val="0"/>')
    )
    assert fmt.align == "right"
    assert fmt.outline == 2
    assert fmt.page_break_before is True
    assert fmt.keep_with_next is False


def test_paragraph_style_name_and_direct_overrides_style() -> None:
    trace: list[Source] = []
    fmt = RESOLVER.para(ppr('<w:pStyle w:val="Heading1"/><w:jc w:val="right"/>'), trace=trace)
    assert (fmt.style_id, fmt.style_name) == ("Heading1", "heading 1")
    assert fmt.align == "right"
    assert source_of(trace, "align") == "run"
    assert source_of(trace, "outline") == "样式:heading 1"


def test_trace_is_opt_in_and_source_of_picks_the_winner() -> None:
    trace: list[Source] = []
    RESOLVER.run(rpr('<w:sz w:val="28"/>'), "Normal", trace=trace)
    assert source_of(trace, "size") == "run"
    assert source_of(trace, "west") == "docDefaults"
    assert source_of(trace, "absent") is None


def test_formats_are_frozen_value_objects() -> None:
    assert isinstance(RESOLVER.run(None), RunFormat)
    assert isinstance(RESOLVER.para(ppr()), ParaFormat)
