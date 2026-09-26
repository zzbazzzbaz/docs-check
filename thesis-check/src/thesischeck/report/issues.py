"""L5 报告：把 `Issue` 规范化成稳定的 `issues.json`，并渲染单文件 `report.html`。

纪律：

- **只呈现，不判定**：结论完全来自 `Issue`，这里不改一个结论。
- **三态严格分区**：不通过 / 无法判定 / 该规则未执行；未识别结构另列，后三类不许当通过。
- **顺序稳定**：按（作用域, 段号, run 序号, 规则号, 摘要）排序，快照可直接 diff。
- **可复现**：不含时间戳 / 绝对路径 / 耗时。
- **面向学生**：不出现 XML 名词；定位能给到"搜什么"。

定位分两层（需求 `FR-9.1`）：机器层是段号 + run 序号 + 元素路径；人类层是
作用域 › 章 › 节（含区段内段序）+ 本段摘要 + 问题涉及的字符片段。

按需回溯（技术设计 §4.2）：只对**判不通过**的属性重走一次 `effective` 的级联拿来源，
取值与来源是同一份实现。
"""

from __future__ import annotations

import html
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from lxml import etree

from ..index import DocumentIndex, FloatRef
from ..parse.effective import DIRECT, Resolver, run_source
from ..parse.model import HeaderFooter, LineRule, Para, Run, Section, Table
from ..rules import Issue, Verdict
from ..semantics.blocks import Block, CheckContext, Role, Scope

SCHEMA_VERSION = 1
RULESET_VERSION = "batch-1+2/204"

_SCOPE_NAMES: dict[Scope, str] = {
    Scope.COVER: "封面",
    Scope.ABS_C: "中文摘要",
    Scope.ABS_E: "英文摘要",
    Scope.TOC: "目录",
    Scope.BODY: "正文",
    Scope.REFS: "参考文献",
    Scope.ACK: "致谢",
    Scope.APPENDIX: "附录",
}
_WHOLE = "全文"
_SCOPE_ORDER: tuple[str, ...] = (*_SCOPE_NAMES.values(), _WHOLE)

# 本轮未覆盖项声明（需求 §2.4）：不做 ≠ 不提，避免"没报 = 肯定没问题"
UNCOVERED: tuple[str, ...] = (
    "分页与页码的实际版面效果：本工具只检查文档结构里的分页标记，最终效果以打印或 PDF 为准。",
    "目录页码的正确性 / 连续性 / 一致性（需要渲染后的页面结果）。",
    "跨页表格的续表标注（需要知道表格实际是否跨页）。",
    "参考文献著录格式的标点校验（本期不做）。",
)

# 属性名（有效格式）-> 给学生看的说法
_PROP_LABELS: dict[str, str] = {
    "ea": "中文字体",
    "west": "西文和数字字体",
    "size": "字号",
    "bold": "加粗",
    "italic": "斜体",
    "va": "上下标",
    "align": "对齐方式",
    "outline": "大纲级别",
    "line_multiple": "行距",
    "line_pt": "行距",
    "first_line_chars": "首行缩进",
    "left_chars": "左缩进",
    "right_chars": "右缩进",
    "hanging_chars": "悬挂缩进",
    "space_before_pt": "段前间距",
    "space_after_pt": "段后间距",
    "top_pt": "上边距",
    "bottom_pt": "下边距",
    "left_pt": "左边距",
    "right_pt": "右边距",
    "page_break_before": "段前分页",
    "keep_with_next": "与下段同页",
}

_ALIGN: dict[str, str] = {
    "center": "居中",
    "left": "左对齐",
    "right": "右对齐",
    "both": "两端对齐",
    "justify": "两端对齐",
    "distribute": "分散对齐",
}
_VA: dict[str, str] = {"superscript": "上标", "subscript": "下标", "baseline": "正常"}
_SIZE_NAMES: dict[float, str] = {
    42.0: "初号",
    36.0: "小初",
    26.0: "一号",
    24.0: "小一",
    22.0: "二号",
    18.0: "小二",
    16.0: "三号",
    15.0: "小三",
    14.0: "四号",
    12.0: "小四",
    10.5: "五号",
    9.0: "小五",
}
_PT_PROPS = frozenset(
    {"top_pt", "bottom_pt", "left_pt", "right_pt", "space_before_pt", "space_after_pt", "line_pt"}
)
_CHAR_PROPS = frozenset({"first_line_chars", "left_chars", "right_chars", "hanging_chars"})


@dataclass(frozen=True, slots=True)
class Location:
    """一条问题的定位（机器层 + 人类层，见 `FR-9.1`）。"""

    block_id: int | None
    run_index: int | None
    element: str | None
    module: str
    chapter: str | None
    section: str | None
    ordinal: int | None
    excerpt: str
    span: str | None

    def text(self) -> str:
        """人类层定位，如 `正文 › 第三章  系统设计 › 3.2 系统架构（该节第 3 段）`。"""
        parts = [self.module]
        if self.chapter:
            parts.append(self.chapter)
        if self.section:
            parts.append(self.section)
        head = " › ".join(parts)
        if self.section and self.ordinal is not None:
            return f"{head}（该节第 {self.ordinal} 段）"
        if self.chapter:
            return f"{head}（章标题）"
        return head

    def find(self) -> str:
        """报告里的"怎么找"：优先搜最具体的标题，其次搜本段摘要。"""
        return self.section or self.chapter or self.excerpt or self.module

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "run_index": self.run_index,
            "element": self.element,
            "module": self.module,
            "chapter": self.chapter,
            "section": self.section,
            "ordinal": self.ordinal,
            "excerpt": self.excerpt,
            "span": self.span,
        }


@dataclass(frozen=True, slots=True)
class Downgrade:
    """一条**无法写入批注**、退回报告的问题（`FR-11.4.5` / `FR-11.6`）。

    页眉 / 页脚、页面设置 / 分节、以及找不到安全锚点的问题走这里；报告里要注明原因并计数，
    而不是悄悄消失。
    """

    rule: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class Entry:
    """一条规范化后的报告条目。"""

    rule: str | None
    severity: str  # fail / undetermined / not_run / unrecognised
    location: Location
    property: str | None
    got: str
    expect: str
    src: str
    source: str | None  # 按需回溯得到的来源，如"在 run 上直接设置"
    error: str | None

    def sort_key(self) -> tuple[object, ...]:
        rank = (
            _SCOPE_ORDER.index(self.location.module)
            if self.location.module in _SCOPE_ORDER
            else len(_SCOPE_ORDER)
        )
        block = self.location.block_id if self.location.block_id is not None else -1
        run = self.location.run_index if self.location.run_index is not None else -1
        return (rank, block, run, self.rule or "", self.location.excerpt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "location": self.location.to_dict(),
            "property": self.property,
            "got": self.got,
            "expect": self.expect,
            "basis": self.src,
            "provenance": self.source,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class Report:
    """一次审核的全部结果，可序列化为 `issues.json` 或渲染为 `report.html`。"""

    parser_version: str
    ruleset_version: str
    fail: tuple[Entry, ...]
    undetermined: tuple[Entry, ...]
    not_run: tuple[Entry, ...]
    unrecognised: tuple[Entry, ...]
    uncovered: tuple[str, ...]
    auto_numbering: int
    annotation: tuple[Downgrade, ...] = ()

    def problem_count(self) -> int:
        """需要学生处理的问题数（三态 + 未识别结构）。"""
        return len(self.fail) + len(self.undetermined) + len(self.not_run) + len(self.unrecognised)

    def all_entries(self) -> tuple[Entry, ...]:
        return self.fail + self.undetermined + self.not_run + self.unrecognised

    def by_scope(self) -> dict[str, dict[str, int]]:
        counts: dict[str, dict[str, int]] = {}
        for entry in self.all_entries():
            bucket = counts.setdefault(
                entry.location.module, {"fail": 0, "undetermined": 0, "not_run": 0, "unrecognised": 0}
            )
            bucket[entry.severity] += 1
        return {scope: counts[scope] for scope in _SCOPE_ORDER if scope in counts}

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "parser_version": self.parser_version,
            "ruleset_version": self.ruleset_version,
            "summary": {
                "fail": len(self.fail),
                "undetermined": len(self.undetermined),
                "not_run": len(self.not_run),
                "unrecognised": len(self.unrecognised),
                "by_scope": self.by_scope(),
                "auto_numbering_paragraphs": self.auto_numbering,
            },
            "fail": [entry.to_dict() for entry in self.fail],
            "undetermined": [entry.to_dict() for entry in self.undetermined],
            "not_run": [entry.to_dict() for entry in self.not_run],
            "unrecognised": [entry.to_dict() for entry in self.unrecognised],
            "uncovered": list(self.uncovered),
            "annotation": {
                "not_annotated": len(self.annotation),
                "items": [{"rule": item.rule, "reason": item.reason} for item in self.annotation],
            },
        }

    def to_html(self) -> str:
        counts = {
            name: len(getattr(self, name)) for name in ("fail", "undetermined", "not_run", "unrecognised")
        }
        sections = (
            ("不通过", self.fail, "fail"),
            ("无法判定", self.undetermined, "undetermined"),
            ("该规则未执行", self.not_run, "not_run"),
            ("未识别结构", self.unrecognised, "unrecognised"),
        )
        body: list[str] = []
        for title, entries, kind in sections:
            body.append(f'<section class="group {kind}">')
            body.append(f"<h2>{html.escape(title)}（{len(entries)} 条）</h2>")
            if not entries:
                body.append('<p class="ok">无</p>')
            for entry in entries:
                body.append(_entry_html(entry))
            body.append("</section>")
        uncovered = "".join(f"<li>{html.escape(item)}</li>" for item in self.uncovered)
        summary = _summary_html(self.by_scope(), counts)
        return _PAGE.format(
            parser=html.escape(self.parser_version),
            ruleset=html.escape(self.ruleset_version),
            summary=summary,
            groups="\n".join(body),
            annotation=_annotation_html(self.annotation),
            uncovered=uncovered,
            auto_numbering=self.auto_numbering,
            total=self.problem_count(),
        )


# ── 定位 ────────────────────────────────────────────────────────

_ANCHORS = (Block, Run, Para, Table, Section, HeaderFooter, FloatRef)
_HEADING_ROLES = (Role.H2, Role.H3)


def _anchor(where: object) -> object | None:
    """从 `Issue.where` 里找出可定位的对象；找不到就是整篇级问题。"""
    if isinstance(where, _ANCHORS):
        return where
    if isinstance(where, tuple):
        for item in where:
            found = _anchor(item)
            if found is not None:
                return found
    return None


def _primary_block(anchor: object, by_id: dict[int, Block], by_xml: dict[Any, Block]) -> Block | None:
    if isinstance(anchor, Block):
        return anchor
    if isinstance(anchor, Run):
        return by_xml.get(anchor.xml.getparent())
    if isinstance(anchor, Para):
        return by_id.get(anchor.id)
    if isinstance(anchor, FloatRef):
        return by_id.get(anchor.para)
    if isinstance(anchor, Table):
        for row in anchor.rows:
            for cell in row:
                for para in cell.paragraphs:
                    block = by_id.get(para.id)
                    if block is not None:
                        return block
    return None


def _para_of(anchor: object, block: Block | None) -> Para | None:
    if isinstance(anchor, Para):
        return anchor
    return None if block is None else block.para


def _excerpt(text: str, limit: int = 40) -> str:
    """摘要：保留原有字符（含标题里的空格），过长则截断加省略号。"""
    trimmed = text.strip()
    return trimmed if len(trimmed) <= limit else trimmed[: limit - 1] + "…"


def _element_path(el: etree._Element) -> str:
    """稳定、相对的 XML 元素路径（不起自文件系统的绝对路径）。"""
    parts: list[str] = []
    node: etree._Element | None = el
    while node is not None:
        tag = node.tag.rsplit("}", 1)[-1]
        parent = node.getparent()
        if parent is None:
            parts.append(tag)
        else:
            siblings = [child for child in parent if child.tag == node.tag]
            parts.append(f"{tag}[{siblings.index(node) + 1}]")
        node = parent
    return "/".join(reversed(parts))


def _header_footer_kind(el: etree._Element) -> str | None:
    """元素是否落在页眉 / 页脚部件里（页码类 run 定位用）。"""
    node = el.getparent()
    while node is not None:
        name = node.tag.rsplit("}", 1)[-1]
        if name == "hdr":
            return "页眉"
        if name == "ftr":
            return "页脚"
        node = node.getparent()
    return None


def _locate(
    anchor: object,
    block: Block | None,
    *,
    index: DocumentIndex,
    blocks: tuple[Block, ...],
    pos_by_id: dict[int, int],
) -> Location:
    if block is not None:
        return _block_location(anchor, block, index=index, blocks=blocks, pos_by_id=pos_by_id)
    if isinstance(anchor, Section):
        return Location(
            None, None, _element_path(anchor.xml), _WHOLE, None, None, None, f"第 {anchor.index} 节", None
        )
    if isinstance(anchor, HeaderFooter):
        kind = "页眉" if anchor.kind == "header" else "页脚"
        return Location(None, None, None, _WHOLE, None, None, None, kind, None)
    if isinstance(anchor, Run):
        hf_kind = _header_footer_kind(anchor.xml)
        if hf_kind is not None:
            return Location(
                None,
                anchor.index,
                _element_path(anchor.xml),
                _WHOLE,
                None,
                None,
                None,
                hf_kind,
                _excerpt(anchor.text),
            )
    return Location(None, None, None, _WHOLE, None, None, None, "整篇文档", None)


def _block_location(
    anchor: object,
    block: Block,
    *,
    index: DocumentIndex,
    blocks: tuple[Block, ...],
    pos_by_id: dict[int, int],
) -> Location:
    position = pos_by_id[block.para.id]
    chapter = next((item for item in index.chapters if item.start <= position <= item.end), None)
    section: str | None = None
    ordinal: int | None = None
    if chapter is not None:
        # 从本段向前找**最近**的二级 / 三级标题，作为"所属节"
        heading = next(
            (i for i in range(position, chapter.start - 1, -1) if blocks[i].role in _HEADING_ROLES),
            None,
        )
        if heading is not None:
            section = _excerpt(blocks[heading].para.text, 60)
            ordinal = position - heading + 1
        else:
            ordinal = position - chapter.start + 1
        chapter_text = _excerpt(blocks[chapter.start].para.text, 60)
    else:
        chapter_text = None
    span = _excerpt(anchor.text) if isinstance(anchor, Run) else None
    element = _element_path(anchor.xml) if isinstance(anchor, Run) else _element_path(block.para.xml)
    return Location(
        block_id=block.para.id,
        run_index=anchor.index if isinstance(anchor, Run) else None,
        element=element,
        module=_SCOPE_NAMES.get(block.scope, _WHOLE),
        chapter=chapter_text,
        section=section,
        ordinal=ordinal,
        excerpt=_excerpt(block.para.text),
        span=span,
    )


# ── 取值的人话 ──────────────────────────────────────────────────


def _size_text(pt: float) -> str:
    name = _SIZE_NAMES.get(pt)
    return f"{pt:g}pt" + (f"（{name}）" if name else "")


def _line_rule_text(para: Para | None) -> str:
    """行距哨兵值（`nan` = 非倍率行距）的人话；不显示 `nan`。"""
    if para is not None:
        point = "" if para.line_pt is None else f" {para.line_pt:g}pt"
        if para.line_rule is LineRule.EXACT:
            return "固定行距" + point
        if para.line_rule is LineRule.AT_LEAST:
            return "最小行距" + point
    return "非倍率行距"


def _tuple_text(value: tuple[object, ...]) -> str:
    if (
        len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], (int, float))
        and not isinstance(value[1], bool)
    ):
        return f"{value[0]} {_size_text(float(value[1]))}"
    return "、".join(str(item) for item in value)


def _format_value(value: object, *, prop: str | None, para: Para | None) -> str:
    if value is None:
        return "无法确定"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float) and math.isnan(value):
        return _line_rule_text(para)
    if isinstance(value, (int, float)):
        if prop == "size":
            return _size_text(float(value))
        if prop in _PT_PROPS:
            return f"{float(value):g}pt"
        if prop in _CHAR_PROPS:
            return f"{float(value):g} 字符"
        return f"{float(value):g}"
    if isinstance(value, tuple):
        return _tuple_text(value)
    if isinstance(value, str):
        if prop == "align":
            return _ALIGN.get(value, value)
        if prop == "va":
            return _VA.get(value, value)
        return value
    return str(value)


def _source_text(label: str | None, anchor: object) -> str | None:
    if label is None:
        return None
    if label == DIRECT:
        return "在 run 上直接设置" if isinstance(anchor, Run) else "在段落上直接设置"
    if label.startswith("字符样式:"):
        return f"来自字符样式「{label.split(':', 1)[1]}」"
    if label.startswith("样式:"):
        return f"来自样式「{label.split(':', 1)[1]}」"
    if label == "默认段落样式":
        return "来自默认段落样式"
    if label == "docDefaults":
        return "来自文档默认设置"
    return label


def _provenance(
    prop: str | None, anchor: object, block: Block | None, resolver: Resolver | None
) -> str | None:
    """判不通过时，对判的那个属性重走一次级联，拿来源。"""
    if resolver is None or prop is None or block is None or not isinstance(anchor, Run):
        return None
    return _source_text(run_source(resolver, anchor, block.para.style_id, prop), anchor)


# ── 组装 ────────────────────────────────────────────────────────


def build_report(
    context: CheckContext,
    index: DocumentIndex,
    issues: Sequence[Issue],
    *,
    parser_version: str,
    ruleset_version: str,
    resolver: Resolver | None = None,
    annotation: Sequence[Downgrade] = (),
) -> Report:
    """把引擎产出的 `Issue` 规范化、分区、定位，组装成 `Report`。"""
    blocks = tuple(context)
    pos_by_id = {block.para.id: i for i, block in enumerate(blocks)}
    by_id = {block.para.id: block for block in blocks}
    by_xml = {block.para.xml: block for block in blocks}

    fail: list[Entry] = []
    undetermined: list[Entry] = []
    not_run: list[Entry] = []
    for issue in issues:
        anchor = _anchor(issue.where)
        block = _primary_block(anchor, by_id, by_xml)
        location = _locate(anchor, block, index=index, blocks=blocks, pos_by_id=pos_by_id)
        prop = issue.prop
        para = _para_of(anchor, block)
        if issue.error is not None:
            entry = Entry(issue.rule, "not_run", location, None, "", "", issue.src, None, issue.error.detail)
            not_run.append(entry)
            continue
        entry = Entry(
            rule=issue.rule,
            severity="fail" if issue.verdict is Verdict.FAIL else "undetermined",
            location=location,
            property=_PROP_LABELS.get(prop, prop) if prop is not None else None,
            got=_format_value(issue.got, prop=prop, para=para),
            expect=_format_value(issue.expect, prop=prop, para=para),
            src=issue.src,
            source=_provenance(prop, anchor, block, resolver) if issue.verdict is Verdict.FAIL else None,
            error=None,
        )
        (fail if issue.verdict is Verdict.FAIL else undetermined).append(entry)

    unrecognised = [
        Entry(
            rule=None,
            severity="unrecognised",
            location=_locate(block, block, index=index, blocks=blocks, pos_by_id=pos_by_id),
            property=None,
            got="该段落未能识别结构",
            expect="应能判断它属于论文的哪个模块（封面 / 摘要 / 目录 / 正文 / 参考文献 / 致谢 / 附录）",
            src="",
            source=None,
            error=None,
        )
        for block in blocks
        if block.role is Role.UNKNOWN
    ]

    fail.sort(key=Entry.sort_key)
    undetermined.sort(key=Entry.sort_key)
    not_run.sort(key=Entry.sort_key)
    unrecognised.sort(key=Entry.sort_key)
    return Report(
        parser_version=parser_version,
        ruleset_version=ruleset_version,
        fail=tuple(fail),
        undetermined=tuple(undetermined),
        not_run=tuple(not_run),
        unrecognised=tuple(unrecognised),
        uncovered=UNCOVERED,
        auto_numbering=sum(1 for para in context.paragraphs if para.numbering is not None),
        annotation=tuple(annotation),
    )


# ── HTML ────────────────────────────────────────────────────────

_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>毕业论文格式审核报告</title>
<style>
:root {{ --fail:#b00020; --undet:#8a5300; --notrun:#5b3a86; --unknown:#555; --line:#e3e3e3; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; padding:0 1rem 3rem; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  color:#222; line-height:1.6; }}
header {{ padding:1.4rem 0 0.6rem; border-bottom:2px solid #222; }}
h1 {{ margin:0 0 .3rem; font-size:1.4rem; }}
.meta {{ color:#666; font-size:.85rem; }}
main {{ max-width:52rem; margin:0 auto; }}
section.group {{ margin-top:1.6rem; }}
section.group h2 {{ font-size:1.1rem; border-left:5px solid #999; padding-left:.5rem; }}
section.group.fail h2 {{ border-color:var(--fail); }}
section.group.undetermined h2 {{ border-color:var(--undet); }}
section.group.not_run h2 {{ border-color:var(--notrun); }}
section.group.unrecognised h2 {{ border-color:var(--unknown); }}
.entry {{ border:1px solid var(--line); border-radius:6px; padding:.7rem .9rem; margin:.6rem 0; }}
.entry .title {{ font-weight:600; }}
.entry .loc {{ color:#444; font-weight:400; }}
.entry .detail {{ margin:.4rem 0 .2rem; }}
.entry .basis, .entry .find {{ margin:.1rem 0; color:#555; font-size:.9rem; }}
.ok {{ color:#2e7d32; }}
table.summary {{ border-collapse:collapse; margin-top:.8rem; font-size:.9rem; }}
table.summary th, table.summary td {{ border:1px solid var(--line); padding:.25rem .6rem; text-align:right; }}
table.summary th:first-child, table.summary td:first-child {{ text-align:left; }}
footer {{ margin-top:2rem; padding-top:.8rem; border-top:1px solid var(--line); color:#444; }}
</style>
</head>
<body>
<header>
  <h1>毕业论文格式审核报告</h1>
  <div class="meta">解析器版本：{parser} · 规则集版本：{ruleset} · 共 {total} 条待处理</div>
</header>
<main>
{summary}
{groups}
{annotation}
<section class="group"><h2>本轮未覆盖项</h2><ul>{uncovered}</ul></section>
</main>
<footer>共 {auto_numbering} 段使用了自动编号。</footer>
</body>
</html>
"""


def _summary_html(by_scope: dict[str, dict[str, int]], counts: dict[str, int]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(scope)}</td><td>{bucket['fail']}</td><td>{bucket['undetermined']}</td>"
        f"<td>{bucket['not_run']}</td><td>{bucket['unrecognised']}</td></tr>"
        for scope, bucket in by_scope.items()
    )
    return (
        '<table class="summary"><thead><tr><th>作用域</th><th>不通过</th><th>无法判定</th>'
        f"<th>未执行</th><th>未识别</th></tr></thead><tbody>{rows}</tbody></table>"
        f"<p>合计：不通过 {counts['fail']} · 无法判定 {counts['undetermined']} · 未执行 {counts['not_run']}"
        f" · 未识别结构 {counts['unrecognised']}</p>"
    )


def _annotation_html(items: tuple[Downgrade, ...]) -> str:
    if not items:
        return ""
    rows = "".join(
        f"<li>{html.escape(item.reason)}"
        + (f"（规则 {html.escape(item.rule)}）" if item.rule else "")
        + "</li>"
        for item in items
    )
    return (
        f'<section class="group"><h2>无法写入批注的问题（{len(items)} 条）</h2>'
        "<p>下列问题位于页眉 / 页脚、页面设置等无法批注的位置，请对照上面的清单处理：</p>"
        f"<ul>{rows}</ul></section>"
    )


def _entry_html(entry: Entry) -> str:
    rule = f"【{html.escape(entry.rule)}】" if entry.rule else "【未识别结构】"
    if entry.severity == "not_run":
        detail = f"该规则本次未能执行：{html.escape(entry.error or '')}"
    elif entry.severity == "unrecognised":
        detail = f"{html.escape(entry.got)}；{html.escape(entry.expect)}"
    else:
        prop = f"{html.escape(entry.property)}：" if entry.property else ""
        source = f"（{html.escape(entry.source)}）" if entry.source else ""
        detail = f"{prop}现在「{html.escape(entry.got)}」，应为「{html.escape(entry.expect)}」{source}"
    basis = f'<p class="basis">依据：{html.escape(entry.src)}</p>' if entry.src else ""
    find = f'<p class="find">怎么找：在文档里搜「{html.escape(entry.location.find())}」</p>'
    span = f'<p class="find">片段：{html.escape(entry.location.span)}</p>' if entry.location.span else ""
    return (
        '<article class="entry">'
        f'<div class="title">{rule}<span class="loc">{html.escape(entry.location.text())}</span></div>'
        f'<p class="detail">{detail}</p>{basis}{span}{find}</article>'
    )
