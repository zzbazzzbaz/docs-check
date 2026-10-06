"""批注回写：四道闭环自检 + 无法批注的跳过 + 坏锚点 + 追加（需求 `FR-11`）。

四道闭环（`FR-11.5`）：
1. 文字核对：插标记前「计划批的文字」== XML 里那段文字；
2. 数量核对：批注覆盖的问题数 == 计划里的问题数（无法批注的跳过）；
3. 内容不变：写回后重新解析，正文文字逐字一致；
4. 锚点回读：重新解析标注版，每条批注锚定的文字 == 该对象文字。

另有：页眉 / 页脚、页面设置、文本框、模块缺失无法批注（跳过）；坏锚点不产坏文件；已带批注追加。
"""

from __future__ import annotations

import dataclasses
import io
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from lxml import etree
from tests.fixtures.base import BASE
from tests.fixtures.synth import alignment, combined, delete, ea, header_ea, page_margin, table_border

from thesischeck.parse.document import para_text, parse_document
from thesischeck.parse.model import Document
from thesischeck.parse.package import (
    PART_COMMENTS,
    PART_CONTENT_TYPES,
    PART_DOCUMENT,
    Package,
)
from thesischeck.report.annotate import Plan, annotate, plan_comments, write_marked
from thesischeck.rules import REGISTRY, Issue, Verdict, run_rules
from thesischeck.semantics.blocks import tag_context

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def _w(tag: str) -> str:
    return f"{{{W}}}{tag}"


# ── 夹具 ────────────────────────────────────────────────────────


@contextmanager
def _case(data: bytes) -> Iterator[tuple[Package, Document, list[Issue]]]:
    """把字节写成临时 docx，打开 -> 解析 -> 跑规则（`Package` 在整个 with 内有效）。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "case.docx"
        path.write_bytes(data)
        with Package.open(path) as pkg:
            doc = parse_document(pkg)
            issues = run_rules(tag_context(doc), REGISTRY)
            yield pkg, doc, issues


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _rewrite(data: bytes, part: str, edit: Callable[[etree._Element], None]) -> bytes:
    parts = _parts(data)
    root = etree.fromstring(parts[part])
    edit(root)
    parts[part] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _add_textbox_with_numbering(root: etree._Element) -> None:
    """在「测试表明…」段落里塞一个文本框，框内段落用自动编号（触发 GLB-28）。"""
    body = root.find(_w("body"))
    if body is None:
        return
    for para in body.iter(_w("p")):
        text = "".join(t.text or "" for t in para.iter(_w("t")))
        if not text.startswith("测试表明"):
            continue
        run = etree.SubElement(para, _w("r"))
        drawing = etree.SubElement(run, _w("drawing"))
        content = etree.SubElement(drawing, _w("txbxContent"))
        inner = etree.SubElement(content, _w("p"))
        ppr = etree.SubElement(inner, _w("pPr"))
        numpr = etree.SubElement(ppr, _w("numPr"))
        etree.SubElement(numpr, _w("ilvl")).set(_w("val"), "0")
        etree.SubElement(numpr, _w("numId")).set(_w("val"), "5")
        node = etree.SubElement(etree.SubElement(inner, _w("r")), _w("t"))
        node.text = "文本框内文字"
        return


def _comments(data: bytes) -> list[tuple[int, str]]:
    """读 `word/comments.xml`：[(id, 正文)]。"""
    parts = _parts(data)
    if PART_COMMENTS not in parts:
        return []
    root = etree.fromstring(parts[PART_COMMENTS])
    out: list[tuple[int, str]] = []
    for comment in root.iter(_w("comment")):
        cid = comment.get(_w("id"))
        body = "".join(t.text or "" for t in comment.iter(_w("t")))
        out.append((int(cid or -1), body))
    return out


def _ranges(data: bytes) -> dict[int, str]:
    """重新解析标注版：批注 id -> 夹在成对标记之间的**可见正文**文字。

    可见口径与解析器一致：跳过文本框（`w:txbxContent`）与 `mc:Fallback` 里的文字。
    """
    root = etree.fromstring(_parts(data)[PART_DOCUMENT])
    hidden = (_w("txbxContent"), f"{{{MC}}}Fallback")

    def invisible(el: etree._Element) -> bool:
        node = el.getparent()
        while node is not None:
            if node.tag in hidden:
                return True
            node = node.getparent()
        return False

    chars: list[str] = []
    starts: dict[int, int] = {}
    out: dict[int, str] = {}
    for el in root.iter():
        if not isinstance(el.tag, str) or invisible(el):
            continue
        if el.tag == _w("commentRangeStart"):
            starts[int(el.get(_w("id")) or -1)] = len(chars)
        elif el.tag == _w("commentRangeEnd"):
            cid = int(el.get(_w("id")) or -1)
            out[cid] = "".join(chars[starts.get(cid, len(chars)) :])
        elif el.tag == _w("t"):
            chars.append(el.text or "")
    return out


def _reparse(data: bytes) -> Document:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "marked.docx"
        path.write_bytes(data)
        with Package.open(path) as pkg:
            return parse_document(pkg)


# ── 四道闭环 ────────────────────────────────────────────────────


def test_closed_loop_text_identity_count_and_readback() -> None:
    """闭环 1 / 2 / 4：文字一致、数量一致、回读锚点一致。"""
    deviation = combined([alignment("中文摘要标题", "left"), ea("中文摘要标题", "仿宋")])
    with _case(deviation.apply(BASE)) as (pkg, doc, issues):
        plan = plan_comments(doc, issues)
        # 闭环 1：计划批的文字与 XML 里那段文字逐字一致
        for comment in plan.comments:
            assert para_text(comment.element) == comment.text
        marked = write_marked(pkg, doc, plan)

    # 同段两条问题聚合成一条批注
    assert len(issues) == 2
    assert len(plan.comments) == 1
    assert plan.comments[0].problems == 2
    # 闭环 2：聚合后的问题数 == 批注覆盖的问题数（无法批注的跳过）
    assert sum(comment.problems for comment in plan.comments) == len(issues)
    assert len(_comments(marked)) == len(plan.comments)
    # 闭环 4：重新解析，锚定的文字 == 该问题所在对象的文字
    ranges = _ranges(marked)
    for comment in plan.comments:
        assert ranges[comment.id] == comment.text


def test_closed_loop_body_text_unchanged() -> None:
    """闭环 3：写回后重新解析，正文文字逐字一致。"""
    with _case(ea("正文段落", "仿宋").apply(BASE)) as (pkg, doc, issues):
        before = [para.text for para in doc.paragraphs]
        marked = write_marked(pkg, doc, plan_comments(doc, issues))

    after = [para.text for para in _reparse(marked).paragraphs]
    assert after == before
    assert len(after) == len(before)


def test_no_run_paragraph_is_annotated_safely() -> None:
    """空段落（无 run）仍能成对插标记，且回读文字为空。"""
    with _case(BASE) as (pkg, doc, _):
        empty = next(para for para in doc.paragraphs if not para.text.strip() and not para.runs)
        issue = Issue("TST-EMPTY", Verdict.FAIL, empty, got="x", expect="y", src="测试")
        plan = plan_comments(doc, [issue])
        marked = write_marked(pkg, doc, plan)

    assert len(plan.comments) == 1
    assert _ranges(marked)[1] == ""


def test_comment_is_rule_id_plus_rule_content() -> None:
    """批注只讲「违反哪条编号、这一条要求什么」，内容取自 catalog 数组。"""
    with _case(BASE) as (_, doc, _):
        para = next(p for p in doc.paragraphs if p.text.strip())
        issues = [
            Issue(
                "REF-10",
                Verdict.FAIL,
                para,
                got="x",
                expect="y",
                src="规范原文：编号「[n]」后恰好 1 个半角空格",
            ),
            Issue("TST-UNKNOWN", Verdict.FAIL, para, got="a", expect="b", src="s"),
            Issue(
                "REF-14",
                Verdict.UNDETERMINED,
                para,
                got="a",
                expect="b",
                src="规范原文：所有参考文献必须都在正文中有引用",
            ),
            Issue(  # 同一条规则重复命中只列一次
                "REF-10",
                Verdict.FAIL,
                para,
                got="z",
                expect="y",
                src="规范原文：编号「[n]」后恰好 1 个半角空格",
            ),
        ]
        plan = plan_comments(doc, issues)

    body = plan.comments[0].body
    assert body.splitlines() == [
        "【REF-10】编号「[n]」后恰好 1 个半角空格",
        "【TST-UNKNOWN】",
        "【REF-14】所有参考文献必须都在正文中有引用（无法自动判定，请人工确认）",
    ]
    assert "应为" not in body  # 不再堆「实际值 / 期望值」
    assert "依据" not in body


# ── 无法批注：页眉 / 页脚、页面设置、模块缺失 ──────────────────


def test_header_footer_and_page_setup_are_not_annotated() -> None:
    cases = [
        (header_ea("仿宋").apply(BASE), "GLB-02"),
        (page_margin(1, "top", "2000").apply(BASE), "GLB-16"),
    ]
    for data, rule in cases:
        with _case(data) as (pkg, doc, issues):
            plan = plan_comments(doc, issues)
            marked = write_marked(pkg, doc, plan)
        assert rule in {issue.rule for issue in issues}, f"{rule} 没有被报出"
        # 页眉 / 页面设置无法批注：不写入批注（问题仍在 issues.json 里），文件仍可打开
        assert rule not in {name for comment in plan.comments for name in comment.rules}
        assert len(_comments(marked)) == len(plan.comments)
        _reparse(marked)


def test_missing_module_is_not_annotated() -> None:
    with _case(delete("附录标题").apply(BASE)) as (pkg, doc, issues):
        plan = plan_comments(doc, issues)
        marked = write_marked(pkg, doc, plan)
    assert "GLB-26" not in {name for comment in plan.comments for name in comment.rules}
    _reparse(marked)


def test_table_problem_anchors_first_cell_paragraph() -> None:
    """表格问题锚在该表第一个单元格的第一段（`FR-11.2`）。"""
    data = table_border("insideV", "single").apply(BASE)
    with _case(data) as (pkg, doc, issues):
        plan = plan_comments(doc, issues)
        marked = write_marked(pkg, doc, plan)

    table_comments = [comment for comment in plan.comments if "TXT-49" in comment.rules]
    assert len(table_comments) == 1
    assert table_comments[0].text.startswith("表头一")
    assert para_text(table_comments[0].element) == table_comments[0].text
    _reparse(marked)


def test_textbox_problem_anchors_host_paragraph() -> None:
    data = _rewrite(BASE, PART_DOCUMENT, _add_textbox_with_numbering)
    with _case(data) as (pkg, doc, issues):
        plan = plan_comments(doc, issues)
        marked = write_marked(pkg, doc, plan)

    textbox = [comment for comment in plan.comments if comment.in_textbox]
    assert len(textbox) == 1
    assert textbox[0].rules == ("GLB-28",)
    assert "在文本框内" in textbox[0].body
    # 锚在宿主段落（可批注），且文字与 XML 一致
    assert para_text(textbox[0].element) == textbox[0].text
    assert _ranges(marked)[textbox[0].id] == textbox[0].text


# ── 坏锚点不产坏文件 ────────────────────────────────────────────


def test_bad_anchors_are_skipped_and_file_still_opens() -> None:
    with _case(BASE) as (pkg, doc, _):
        real = doc.paragraphs[1]
        mismatch = dataclasses.replace(real, text=real.text + "XYZ")
        empty = next(para for para in doc.paragraphs if not para.text.strip() and not para.runs)
        broken = [
            Issue("TST-NONE", Verdict.FAIL, object(), got="a", expect="b", src="s"),
            Issue("TST-MISMATCH", Verdict.FAIL, mismatch, got="a", expect="b", src="s"),
            Issue("TST-OK", Verdict.FAIL, empty, got="a", expect="b", src="s"),
        ]
        plan = plan_comments(doc, broken)
        marked = write_marked(pkg, doc, plan)

    assert [comment.rules for comment in plan.comments] == [("TST-OK",)]
    assert len(plan.comments) == 1
    # 无法定位 / 锚点文字不一致的问题没有变成坏标记，文件仍能被重新解析
    assert _ranges(marked) == {1: ""}
    _reparse(marked)


# ── 已带批注：追加不覆盖 ────────────────────────────────────────


def test_append_to_document_that_already_has_comments() -> None:
    deviation = ea("中文摘要标题", "仿宋").apply(BASE)
    with _case(deviation) as (pkg, doc, issues):
        first = annotate(pkg, doc, issues)
    first_ids = {cid for cid, _ in _comments(first)}
    assert first_ids

    with _case(first) as (pkg2, doc2, issues2):
        plan2 = plan_comments(doc2, issues2)
        second = write_marked(pkg2, doc2, plan2)
    comments = _comments(second)
    ids = {cid for cid, _ in comments}
    assert len(comments) == len(first_ids) + len(plan2.comments)
    assert len(ids) == len(comments)  # id 全局唯一
    assert first_ids <= ids  # 第一次的批注一个不少
    assert max(ids) > max(first_ids)  # 新批注从已有最大值之后开始
    _reparse(second)


# ── 无问题不引入批注部件 ────────────────────────────────────────


def test_no_comments_means_no_comments_part() -> None:
    """没有问题可批注时照抄原包，不引入 comments 部件。"""
    with _case(BASE) as (pkg, doc, issues):
        plan: Plan = plan_comments(doc, issues)
        marked = write_marked(pkg, doc, plan)
    assert plan.comments == ()
    assert PART_COMMENTS not in _parts(marked)
    assert PART_CONTENT_TYPES in _parts(marked)
    _reparse(marked)
