"""L5 报告：把 `Issue` 规范化成稳定的 `issues.json`（`summary` / `rules` / `problems`）。

纪律：

- **只呈现，不判定**：结论完全来自 `Issue`，这里不改一个结论。
- **三态严格分区**：不通过 / 无法判定 / 该规则未执行；未识别结构另列，后三类不许当通过。
- **静态信息只写一次**：规则文案集中在 `rules`（一条规则一份），问题只在 `problems` 里带
  自己的定位与实际值——不逐条重复「这条要求什么」。
- **顺序稳定**：按（作用域, 段号, 规则号, 摘要）排序，快照可直接 diff。
- **可复现**：不含时间戳 / 绝对路径 / 耗时。
- **面向学生**：不出现 XML 名词。

定位分两层（需求 `FR-9.1`）：机器层是段号；人类层是 作用域 › 章 › 节（含区段内段序）+ 本段摘要。
"""

from __future__ import annotations

import math
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..index import DocumentIndex, FloatRef
from ..parse import HeaderFooter, LineRule, Para, Run, Section, Table
from ..rules import Issue, Verdict, catalog
from ..semantics import Block, CheckContext, Role, Scope

# 规则集版本的**回退值**：优先环境变量与 git 描述（见下）
RULESET_VERSION = "batch-1+2/207"

# 部署态注入：安装后的包没有 .git，`git describe` 取不到真实版本
RULESET_VERSION_ENV = "THESISCHECK_RULESET_VERSION"


@lru_cache(maxsize=1)
def ruleset_version() -> str:
    """规则集版本，按优先级：环境变量 `THESISCHECK_RULESET_VERSION` → git describe → 常量。

    环境变量用于部署态（安装后的包没有 .git）；`git describe --tags --dirty` 用于开发态，
    给出 tag + 距 tag 的提交数 + 脏标记；都取不到才回退到常量。结果缓存，一次进程只取
    一次，`lru_cache` 线程安全。
    """
    override = os.environ.get(RULESET_VERSION_ENV, "").strip()
    if override:
        return override
    try:
        described = subprocess.run(
            ["git", "describe", "--tags", "--dirty"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except OSError, subprocess.SubprocessError:
        described = ""
    return described or RULESET_VERSION


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
    """一条问题的定位：机器层段号 + 人类层 作用域 › 章 › 节（含区段内段序）+ 本段摘要。"""

    block_id: int | None
    module: str
    chapter: str | None
    section: str | None
    ordinal: int | None
    excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "module": self.module,
            "chapter": self.chapter,
            "section": self.section,
            "ordinal": self.ordinal,
            "excerpt": self.excerpt,
        }


@dataclass(frozen=True, slots=True)
class Entry:
    """`problems` 里的一条问题。"""

    rule: str | None
    severity: str  # fail / undetermined / not_run / unrecognised
    location: Location
    got: str
    expect: str
    error: str | None = None

    def sort_key(self) -> tuple[object, ...]:
        rank = (
            _SCOPE_ORDER.index(self.location.module)
            if self.location.module in _SCOPE_ORDER
            else len(_SCOPE_ORDER)
        )
        block = self.location.block_id if self.location.block_id is not None else -1
        return (rank, block, self.rule or "", self.location.excerpt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "where": self.location.to_dict(),
            "got": self.got,
            "expect": self.expect,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class Report:
    """一次审核的全部结果：静态规则表 + 动态问题清单（+ 摘要）。"""

    ruleset_version: str
    problems: tuple[Entry, ...]

    def counts(self) -> dict[str, int]:
        """四态计数。"""
        counts = {"fail": 0, "undetermined": 0, "not_run": 0, "unrecognised": 0}
        for entry in self.problems:
            counts[entry.severity] += 1
        return counts

    def by_scope(self) -> dict[str, dict[str, int]]:
        """按作用域分组的四态计数，顺序固定（`_SCOPE_ORDER`）。"""
        scopes: dict[str, dict[str, int]] = {}
        for entry in self.problems:
            bucket = scopes.setdefault(
                entry.location.module, {"fail": 0, "undetermined": 0, "not_run": 0, "unrecognised": 0}
            )
            bucket[entry.severity] += 1
        return {scope: scopes[scope] for scope in _SCOPE_ORDER if scope in scopes}

    def rules(self) -> dict[str, dict[str, str]]:
        """问题里出现的规则号 → 规则文案（一条规则只写一次，与批注同源 `catalog`）。"""
        table: dict[str, dict[str, str]] = {}
        for entry in self.problems:
            if entry.rule is not None and entry.rule not in table:
                table[entry.rule] = {"text": catalog.content(entry.rule)}
        return table

    def to_json(self) -> dict[str, Any]:
        counts = self.counts()
        return {
            "summary": {
                "ruleset_version": self.ruleset_version,
                **counts,
                "by_scope": self.by_scope(),
            },
            "rules": self.rules(),
            "problems": [entry.to_dict() for entry in self.problems],
        }


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


def _header_footer_kind(el: Any) -> str | None:
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
        return _block_location(block, index=index, blocks=blocks, pos_by_id=pos_by_id)
    if isinstance(anchor, Section):
        return Location(None, _WHOLE, None, None, None, f"第 {anchor.index} 节")
    if isinstance(anchor, HeaderFooter):
        return Location(None, _WHOLE, None, None, None, "页眉" if anchor.kind == "header" else "页脚")
    if isinstance(anchor, Run):
        kind = _header_footer_kind(anchor.xml)
        if kind is not None:
            return Location(None, _WHOLE, None, None, None, _excerpt(anchor.text) or kind)
    return Location(None, _WHOLE, None, None, None, "整篇文档")


def _block_location(
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
    return Location(
        block_id=block.para.id,
        module=_SCOPE_NAMES.get(block.scope, _WHOLE),
        chapter=chapter_text,
        section=section,
        ordinal=ordinal,
        excerpt=_excerpt(block.para.text),
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


# ── 组装 ────────────────────────────────────────────────────────


def build_report(
    context: CheckContext,
    index: DocumentIndex,
    issues: Sequence[Issue],
    *,
    ruleset_version: str,
) -> Report:
    """把引擎产出的 `Issue` 规范化、定位，组装成 `Report`。"""
    blocks = tuple(context)
    pos_by_id = {block.para.id: i for i, block in enumerate(blocks)}
    by_id = {block.para.id: block for block in blocks}
    by_xml = {block.para.xml: block for block in blocks}

    problems: list[Entry] = []
    for issue in issues:
        anchor = _anchor(issue.where)
        block = _primary_block(anchor, by_id, by_xml)
        location = _locate(anchor, block, index=index, blocks=blocks, pos_by_id=pos_by_id)
        if issue.error is not None:
            problems.append(Entry(issue.rule, "not_run", location, "", "", issue.error.detail))
            continue
        prop = issue.prop
        para = _para_of(anchor, block)
        problems.append(
            Entry(
                rule=issue.rule,
                severity="fail" if issue.verdict is Verdict.FAIL else "undetermined",
                location=location,
                got=_format_value(issue.got, prop=prop, para=para),
                expect=_format_value(issue.expect, prop=prop, para=para),
            )
        )
    problems.extend(
        Entry(
            rule=None,
            severity="unrecognised",
            location=_block_location(block, index=index, blocks=blocks, pos_by_id=pos_by_id),
            got="该段落未能识别结构",
            expect="应能判断它属于论文的哪个模块（封面 / 摘要 / 目录 / 正文 / 参考文献 / 致谢 / 附录）",
        )
        for block in blocks
        if block.role is Role.UNKNOWN
    )

    problems.sort(key=Entry.sort_key)
    return Report(ruleset_version=ruleset_version, problems=tuple(problems))
