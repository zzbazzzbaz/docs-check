"""L5 批注回写：把问题以 Word 批注标进文档（需求 `FR-11`）。

只插批注标记，**绝不改动正文内容**；解析与写回操作**同一棵 XML 树**（模型里的 `xml` 引用），
打包时把原包其余部件照抄，只替换 `word/document.xml`、新增 / 追加 `word/comments.xml`
与两处注册信息（`[Content_Types].xml`、`word/_rels/document.xml.rels`）。

四道闭环（`FR-11.5`）在 `tests/unit/test_annotate.py` 里逐条验证；本模块本身保证：

1. 插标记前核对「计划批的文字 == XML 里那段文字」，不一致就**跳过**（不产坏文件）；
2. 按「段落 / 对象」聚合，同段多条问题合并成一条批注；
3. 只插标记，正文文字逐字不变；
4. 批注 `id` 全局唯一、按文档顺序，已有批注时从最大值之后追加。

页眉 / 页脚、页面设置 / 分节、以及找不到安全位置的锚点**不批注**（仍留在 `issues.json` 里）。
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from lxml import etree

from ..index import FloatRef
from ..parse import (
    PART_COMMENTS,
    PART_CONTENT_TYPES,
    PART_DOCUMENT,
    Document,
    HeaderFooter,
    Package,
    Para,
    Run,
    Section,
    Story,
    Table,
    para_text,
    rels_part_name,
)
from ..rules import Issue, Verdict, catalog
from ..semantics import Block

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
COMMENTS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

AUTHOR = "格式审核"
INITIALS = "格审"
MAX_BODY = 200
TRUNCATED = "…（详见报告）"

# 新建部件时用的最小空部件（自带正确命名空间，避免序列化出 ns0 前缀）
EMPTY_COMMENTS = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:comments xmlns:w="{W_NS}"/>'
EMPTY_CONTENT_TYPES = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="{CT_NS}"/>'
EMPTY_RELS = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PKG_REL_NS}"/>'


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


@dataclass(frozen=True, slots=True)
class PlannedComment:
    """一条待写入的批注：锚点元素 + 计划批注的文字 + 正文 + 聚合的问题数。"""

    id: int
    element: etree._Element
    text: str
    in_textbox: bool
    body: str
    problems: int
    rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Plan:
    """一次写回的计划：按锚点聚合后的批注。"""

    comments: tuple[PlannedComment, ...]


@dataclass(frozen=True, slots=True)
class _Target:
    """解析出的锚点：承载标记的段落 + 计划批注的文字。"""

    para: Para
    element: etree._Element
    text: str
    in_textbox: bool


@dataclass(frozen=True, slots=True)
class _Ctx:
    by_xml: dict[etree._Element, Para]
    by_id: dict[int, Para]


# ── 锚点解析（`FR-11.2`）────────────────────────────────────────


def _host_para(para: Para, ctx: _Ctx) -> Para | None:
    """文本框段落的宿主段落：最近的 `w:p` 祖先（且属于正文故事区）。"""
    node = para.xml.getparent()
    while node is not None:
        if node.tag == _w("p"):
            host = ctx.by_xml.get(node)
            if host is not None and host.story is Story.MAIN:
                return host
        node = node.getparent()
    return None


def _run_text(el: etree._Element) -> str:
    return "".join(str(t.text or "") for t in el.iter(_w("t")))


def _para_target(para: Para, ctx: _Ctx) -> _Target | None:
    if para.story in (Story.HEADER, Story.FOOTER):
        return None
    if para_text(para.xml) != para.text:
        return None
    if para.story is Story.TEXTBOX:
        host = _host_para(para, ctx)
        if host is None:
            return None
        if para_text(host.xml) != host.text:
            return None
        return _Target(host, host.xml, host.text, True)
    return _Target(para, para.xml, para.text, False)


def _run_target(run: Run, ctx: _Ctx) -> _Target | None:
    if _run_text(run.xml) != run.text:
        return None
    node = run.xml.getparent()
    while node is not None and node.tag != _w("p"):
        node = node.getparent()
    para = ctx.by_xml.get(node) if node is not None else None
    if para is None:
        return None
    return _para_target(para, ctx)


def _resolve(anchor: object, ctx: _Ctx) -> _Target | None:
    if isinstance(anchor, Block):
        return _para_target(anchor.para, ctx)
    if isinstance(anchor, Para):
        return _para_target(anchor, ctx)
    if isinstance(anchor, Run):
        return _run_target(anchor, ctx)
    if isinstance(anchor, FloatRef):
        para = ctx.by_id.get(anchor.para)
        return None if para is None else _para_target(para, ctx)
    if isinstance(anchor, Table):
        first = next((p for row in anchor.rows for cell in row for p in cell.paragraphs), None)
        return None if first is None else _para_target(first, ctx)
    if isinstance(anchor, (Section, HeaderFooter)):
        return None
    if isinstance(anchor, tuple):
        for item in anchor:
            found = _resolve(item, ctx)
            if found is not None:
                return found
    return None


# ── 批注正文（`FR-11.3`）────────────────────────────────────────


def _legal(ch: str) -> bool:
    return (
        ch in "\t\n\r"
        or " " <= ch <= "\ud7ff"
        or "\ue000" <= ch <= "\ufffd"
        or "\U00010000" <= ch <= "\U0010ffff"
    )


def _clean(text: str) -> str:
    """清掉 XML 1.0 非法字符（含控制符与孤立代理）。"""
    return "".join(ch for ch in text if _legal(ch))


def _fit(text: str) -> str:
    if len(text) <= MAX_BODY:
        return text
    return text[: MAX_BODY - len(TRUNCATED)].rstrip() + TRUNCATED


def _describe(issue: Issue) -> str:
    """一条批注的人话：只说「违反哪条编号、这一条要求什么」。

    规则内容统一取自 `rules.catalog` 的编号 → 内容数组，不在渲染层另起炉灶。
    未知编号（测试里自造的规则）退化成只报编号。
    """
    if issue.error is not None:
        return f"【{issue.rule}】本次未能执行，详见报告"
    content = catalog.content(issue.rule)
    head = f"【{issue.rule}】{content}" if content else f"【{issue.rule}】"
    if issue.verdict is Verdict.FAIL:
        return head
    return f"{head}（无法自动判定，请人工确认）"


def _body_for(issues: Sequence[Issue], target: _Target) -> str:
    """同段多条问题：每条一行，同一条规则只列一次。"""
    lines: list[str] = []
    for issue in issues:
        line = _describe(issue)
        if line not in lines:
            lines.append(line)
    if target.in_textbox:
        lines[0] = "（在文本框内）" + lines[0]
    return _fit(_clean("\n".join(lines)))


# ── 计划 ────────────────────────────────────────────────────────


def plan_comments(doc: Document, issues: Sequence[Issue]) -> Plan:
    """把问题按其锚点聚合成批注计划；无法锚定的**跳过**（不批注，但仍在 `issues.json` 里）。

    `id` 是**相对编号**（1 起），写入时统一加上已存在批注的最大编号（`FR-11.4.6`）。
    """
    main = doc.paragraphs
    boxes = tuple(para for box in doc.boxes for para in box.paragraphs)
    ctx = _Ctx(
        by_xml={para.xml: para for para in (*main, *boxes)},
        by_id={para.id: para for para in main},
    )
    position = {id(para.xml): index for index, para in enumerate(main)}

    groups: dict[int, list[tuple[Issue, _Target]]] = {}
    for issue in issues:
        found = _resolve(issue.where, ctx)
        if isinstance(found, _Target):
            groups.setdefault(id(found.element), []).append((issue, found))

    ordered = sorted(groups.items(), key=lambda item: position.get(item[0], len(position)))
    comments: list[PlannedComment] = []
    for number, (_, entries) in enumerate(ordered, 1):
        target = entries[0][1]
        grouped = [issue for issue, _ in entries]
        comments.append(
            PlannedComment(
                id=number,
                element=target.element,
                text=target.text,
                in_textbox=target.in_textbox,
                body=_body_for(grouped, target),
                problems=len(grouped),
                rules=tuple(issue.rule for issue in grouped),
            )
        )
    return Plan(comments=tuple(comments))


# ── 写入 ────────────────────────────────────────────────────────


def _to_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _existing_max_id(comments: etree._Element, doc: Document) -> int:
    """包内已有批注 / 标记的最大 id；没有就是 0（新批注从 1 起）。"""
    ids: list[int] = []
    ids.extend(
        value
        for value in (_to_int(c.get(_w("id"))) for c in comments.iter(_w("comment")))
        if value is not None
    )
    for tag in ("commentRangeStart", "commentRangeEnd", "commentReference"):
        for el in doc.xml.iter(_w(tag)):
            value = _to_int(el.get(_w("id")))
            if value is not None:
                ids.append(value)
    return max(ids) if ids else 0


def _contains_run(child: etree._Element) -> bool:
    return any(isinstance(el.tag, str) and el.tag == _w("r") for el in child.iter())


def _insert_markers(para: etree._Element, cid: int) -> None:
    """在**单段内**成对插入命名的批注范围标记与引用 run（`FR-11.1` / `FR-11.4.3`）。"""
    start = etree.Element(_w("commentRangeStart"))
    start.set(_w("id"), str(cid))
    end = etree.Element(_w("commentRangeEnd"))
    end.set(_w("id"), str(cid))
    reference = etree.Element(_w("r"))
    etree.SubElement(reference, _w("commentReference")).set(_w("id"), str(cid))

    children = list(para)
    content = [
        index
        for index, child in enumerate(children)
        if isinstance(child.tag, str) and child.tag != _w("pPr") and _contains_run(child)
    ]
    if content:
        first, last = content[0], content[-1]
        para.insert(first, start)
        para.insert(last + 2, end)
        para.insert(last + 3, reference)
        return
    at = 1 if children and isinstance(children[0].tag, str) and children[0].tag == _w("pPr") else 0
    para.insert(at, start)
    para.insert(at + 1, end)
    para.insert(at + 2, reference)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_element(xml: str) -> etree._Element:
    return etree.fromstring(xml.encode())


def _append_comment(root: etree._Element, cid: int, body: str) -> None:
    comment = etree.SubElement(root, _w("comment"))
    comment.set(_w("id"), str(cid))
    comment.set(_w("author"), AUTHOR)
    comment.set(_w("date"), _now())
    comment.set(_w("initials"), INITIALS)
    for line in body.split("\n"):
        paragraph = etree.SubElement(comment, _w("p"))
        run = etree.SubElement(paragraph, _w("r"))
        node = etree.SubElement(run, _w("t"))
        node.set(XML_SPACE, "preserve")
        node.text = line


def _content_types(pkg: Package) -> etree._Element:
    root = pkg.xml(PART_CONTENT_TYPES)
    proper = f"{{{CT_NS}}}Types"
    if root is None:
        return _new_element(EMPTY_CONTENT_TYPES)
    if root.tag != proper:
        # 极少数不规范的包：内容类型根不在应属命名空间里，补一个规范的根（子节点照搬）
        fixed = _new_element(EMPTY_CONTENT_TYPES)
        for child in list(root):
            fixed.append(child)
        return fixed
    return root


def _register_content_type(root: etree._Element) -> None:
    for override in root.iter(f"{{{CT_NS}}}Override"):
        if override.get("PartName") == f"/{PART_COMMENTS}":
            return
    override = etree.SubElement(root, f"{{{CT_NS}}}Override")
    override.set("PartName", f"/{PART_COMMENTS}")
    override.set("ContentType", COMMENTS_CONTENT_TYPE)


def _document_rels(pkg: Package) -> etree._Element:
    root = pkg.xml(rels_part_name(PART_DOCUMENT))
    return root if root is not None else _new_element(EMPTY_RELS)


def _ensure_relationship(root: etree._Element) -> None:
    used: set[str] = set()
    for rel in root:
        if not isinstance(rel.tag, str):
            continue
        if rel.get("Type") == COMMENTS_REL_TYPE:
            return
        rid = rel.get("Id")
        if rid is not None:
            used.add(rid)
    number = 1
    while f"rId{number}" in used:
        number += 1
    rel = etree.SubElement(root, f"{{{PKG_REL_NS}}}Relationship")
    rel.set("Id", f"rId{number}")
    rel.set("Type", COMMENTS_REL_TYPE)
    rel.set("Target", "comments.xml")


def _rezip(pkg: Package, replaced: dict[str, bytes]) -> bytes:
    """把原包部件照抄，只替换 `replaced` 里的部件（新增的追加到末尾）。"""
    pending = dict(replaced)
    names = sorted(pkg.names(), key=lambda name: (name != PART_CONTENT_TYPES, name))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            if name.endswith("/"):
                continue
            if name in pending:
                archive.writestr(name, pending.pop(name))
                continue
            raw = pkg.read(name)
            if raw is not None:
                archive.writestr(name, raw)
        for name, raw in pending.items():
            archive.writestr(name, raw)
    return buffer.getvalue()


def _serialize(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def write_marked(pkg: Package, doc: Document, plan: Plan) -> bytes:
    """把计划应用到解析时那棵树，再打包成**新的** docx 字节（原文件不动）。"""
    if not plan.comments:
        # 没有问题可批注：照抄原包，不引入 comments 部件与注册信息
        return _rezip(pkg, {})

    document = doc.xml.getroottree().getroot()
    comments = pkg.xml(PART_COMMENTS)
    if comments is None:
        comments = _new_element(EMPTY_COMMENTS)
    base = _existing_max_id(comments, doc)
    for comment in plan.comments:
        cid = base + comment.id
        _insert_markers(comment.element, cid)
        _append_comment(comments, cid, comment.body)

    content_types = _content_types(pkg)
    _register_content_type(content_types)
    rels = _document_rels(pkg)
    _ensure_relationship(rels)

    replaced = {
        PART_DOCUMENT: _serialize(document),
        PART_CONTENT_TYPES: _serialize(content_types),
        rels_part_name(PART_DOCUMENT): _serialize(rels),
        PART_COMMENTS: _serialize(comments),
    }
    return _rezip(pkg, replaced)


def annotate(pkg: Package, doc: Document, issues: Sequence[Issue]) -> bytes:
    """产出标注版 docx 字节：把问题以批注标进文档，原文件不改动（`FR-11.1`）。"""
    return write_marked(pkg, doc, plan_comments(doc, issues))
