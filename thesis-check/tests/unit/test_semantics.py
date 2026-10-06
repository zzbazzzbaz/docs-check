"""L2 语义层：共享匹配器、作用域分区、全量角色、具名选择器。

两条本阶段最贵的纪律：
- **识别器是超集**：`附录a` / `附录一` / `第 一 章` / `第1章` 都要先认下来，写错由规则报。
- **反恒真**：把 `附录A` 的级别改成 3、把大写字母改成小写，**仍然被识别**。

样张在内存里拼最小 docx；真实语料统计标 `real_corpus`，无语料时跳过。
"""

from __future__ import annotations

import io
import os
import zipfile
from collections import Counter
from itertools import pairwise
from pathlib import Path

import pytest

from thesischeck.parse import package as pkg
from thesischeck.parse.document import parse_document
from thesischeck.parse.model import Document
from thesischeck.semantics import matchers, select
from thesischeck.semantics.blocks import Block, Role, Scope, tag_blocks
from thesischeck.semantics.scope import partition

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

STYLES = f"""<?xml version="1.0"?>
<w:styles xmlns:w="{W}">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="正文"/></w:style>
  <w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="H1">
    <w:name w:val="heading 1"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="H2">
    <w:name w:val="heading 2"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="H3">
    <w:name w:val="heading 3"/><w:pPr><w:outlineLvl w:val="2"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="H4">
    <w:name w:val="heading 4"/><w:pPr><w:outlineLvl w:val="3"/></w:pPr>
  </w:style>
</w:styles>"""


def para(text: str = "", *, style: str | None = None, numbering: int | None = None) -> str:
    ppr = ""
    if style is not None:
        ppr += f'<w:pStyle w:val="{style}"/>'
    if numbering is not None:
        ppr += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{numbering}"/></w:numPr>'
    prefix = f"<w:pPr>{ppr}</w:pPr>" if ppr else ""
    run = f"<w:r><w:t>{text}</w:t></w:r>" if text else ""
    return f"<w:p>{prefix}{run}</w:p>"


def load(tmp_path: Path, body: str) -> Document:
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(pkg.PART_CONTENT_TYPES, b'<?xml version="1.0"?><Types/>')
        zf.writestr(pkg.PART_DOCUMENT, document.encode())
        zf.writestr(pkg.PART_STYLES, STYLES.encode())
    path = tmp_path / "d.docx"
    path.write_bytes(archive.getvalue())
    with pkg.Package.open(path) as opened:
        return parse_document(opened)


def full_document() -> str:
    """覆盖全部 8 个作用域、且目录里混入「第一章」「参考文献」条目。"""
    return (
        para("本科毕业设计（论文）")
        + para("摘    要")
        + para("中文摘要正文。")
        + para("关键词：格式；审核")
        + para("ABSTRACT")
        + para("English abstract body.")
        + para("Keywords: format, review")
        + para("目    录")
        + para("第一章 引言", style="TOC1")
        + para("参考文献", style="TOC1")
        + para("第一章 引言")
        + para("1.1 系统概述")
        + para("正文内容。")
        + para("")
        + para("参考文献")
        + para("[1] 作者. 题名[M]. 出版社.")
        + para("致    谢")
        + para("感谢所有帮助过我的人。")
        + para("附    录")
        + para("附录A 名词术语", style="H2")
        + para("这里是附录的正文内容。")
    )


def texts(blocks: tuple[Block, ...]) -> list[str]:
    return [b.para.text for b in blocks]


# ── 共享匹配器：识别器是超集 ────────────────────────────────────


def test_key_text_removes_whitespace_and_zero_width() -> None:
    assert matchers.key_text("第 一 章\n引言") == "第一章引言"
    assert matchers.key_text("\u200b摘要") == "摘要"
    assert matchers.key_text(None) == ""


@pytest.mark.parametrize(
    "text",
    ["第一章 引言", "第 一 章", "第1章", "第 11 章", "第11章", "第十一章"],
)
def test_chapter_recognition_is_a_superset(text: str) -> None:
    assert matchers.is_chapter(text)


@pytest.mark.parametrize("text", ["第一", "章", "绪论", ""])
def test_non_chapter_text_is_not_recognised(text: str) -> None:
    assert not matchers.is_chapter(text)


def test_chapter_no_reads_chinese_and_arabic() -> None:
    assert matchers.chapter_no("第一章") == 1
    assert matchers.chapter_no("第十章") == 10
    assert matchers.chapter_no("第十一章") == 11
    assert matchers.chapter_no("第 二十三 章") == 23
    assert matchers.chapter_no("第3章") == 3
    assert matchers.chapter_no("绪论") is None


@pytest.mark.parametrize("text", ["附录a", "附录一", "附录Ａ", "附录A名词术语", "附 录 b"])
def test_appendix_sub_is_recognised_without_case_or_level(text: str) -> None:
    assert matchers.is_appendix_sub(text)


def test_appendix_title_and_sub_are_distinct() -> None:
    assert matchers.is_appendix_title("附    录")
    assert not matchers.is_appendix_title("附录A")
    assert not matchers.is_appendix_sub("附    录")


def test_caption_and_formula_matchers() -> None:
    assert matchers.is_figure_caption("图3-1 系统架构")
    assert not matchers.is_figure_caption("如图3-1所示")
    assert matchers.is_table_caption("表 3-2 字段说明")
    assert matchers.is_continued_table_caption("续表3-2")
    assert not matchers.is_table_caption("续表3-2")
    assert matchers.formula_no("公式（3-1）") == ("3", "1")


def test_looks_like_number_accepts_various_brackets() -> None:
    for text in ("[1] 作者", "【2】作者", "（3）作者", "1. 作者", " [4] 作者"):
        assert matchers.looks_like_number(text)
    assert not matchers.looks_like_number("作者. 题名[M]")


def test_citation_text_and_numbers() -> None:
    assert matchers.is_citation("[1]")
    assert matchers.is_citation("[1,2]")
    assert matchers.is_citation("[1-3]")
    assert not matchers.is_citation("1")
    assert matchers.citation_numbers("[1,3-5]") == (1, 3, 4, 5)


def test_character_classes() -> None:
    assert matchers.has_cjk("中文")
    assert not matchers.has_cjk("abc123")
    assert matchers.has_ascii_alnum("a1")
    assert not matchers.has_ascii_alnum("中文，。")


# ── 作用域分区 ──────────────────────────────────────────────────


def test_scope_ranges_are_contiguous_and_cover_the_document(tmp_path: Path) -> None:
    document = load(tmp_path, full_document())
    ranges = partition(document.paragraphs)
    assert [r.scope for r in ranges] == [
        Scope.COVER,
        Scope.ABS_C,
        Scope.ABS_E,
        Scope.TOC,
        Scope.BODY,
        Scope.REFS,
        Scope.ACK,
        Scope.APPENDIX,
    ]
    assert ranges[0].start == 0
    assert ranges[-1].end == len(document.paragraphs) - 1
    for left, right in pairwise(ranges):
        assert right.start == left.end + 1


def test_toc_entries_do_not_start_the_body_scope(tmp_path: Path) -> None:
    document = load(tmp_path, full_document())
    body = next(r for r in partition(document.paragraphs) if r.scope is Scope.BODY)
    # 目录里的「第一章 引言」在前，正文的那一段在后
    assert body.start == 10


@pytest.mark.parametrize("heading", ["第一章 引言", "第 一 章 引言", "第1章 引言"])
def test_body_scope_starts_at_a_chapter_heading(tmp_path: Path, heading: str) -> None:
    body = para("封面标题") + para("摘 要") + para("摘要正文") + para(heading)
    document = load(tmp_path, body)
    ranges = partition(document.paragraphs)
    assert [r.scope for r in ranges] == [Scope.COVER, Scope.ABS_C, Scope.BODY]


def test_missing_module_is_treated_as_missing_not_guessed(tmp_path: Path) -> None:
    document = load(tmp_path, para("封面标题") + para("摘 要") + para("第一章 引言"))
    scopes = [r.scope for r in partition(document.paragraphs)]
    assert scopes == [Scope.COVER, Scope.ABS_C, Scope.BODY]


# ── 角色是全函数 ────────────────────────────────────────────────


def test_tag_blocks_covers_every_paragraph(tmp_path: Path) -> None:
    document = load(tmp_path, full_document())
    blocks = tag_blocks(document)
    assert len(blocks) == len(document.paragraphs)
    assert [b.para for b in blocks] == list(document.paragraphs)


def test_roles_of_a_full_document(tmp_path: Path) -> None:
    blocks = tag_blocks(load(tmp_path, full_document()))

    def role_at(index: int) -> Role:
        return blocks[index].role

    assert role_at(0) is Role.BODY  # 封面行
    assert role_at(1) is Role.TITLE  # 摘    要
    assert role_at(3) is Role.KEYWORDS
    assert role_at(4) is Role.TITLE  # ABSTRACT
    assert role_at(6) is Role.KEYWORDS
    assert role_at(7) is Role.TITLE  # 目    录
    assert role_at(8) is Role.BODY  # 目录条目
    assert role_at(10) is Role.BODY  # 无标题样式的「第一章 引言」
    assert role_at(13) is Role.EMPTY
    assert role_at(14) is Role.TITLE  # 参考文献
    assert role_at(15) is Role.REF_ITEM
    assert role_at(16) is Role.TITLE  # 致    谢
    assert role_at(18) is Role.TITLE  # 附    录
    assert role_at(19) is Role.H2  # 附录子标题按大纲级别
    assert all(b.role is not None for b in blocks)


def test_unknown_is_only_used_when_a_block_cannot_be_placed(tmp_path: Path) -> None:
    body = para("摘 要") + para("摘要正文") + para("目录") + para("这是一段手打的目录说明")
    blocks = tag_blocks(load(tmp_path, body))
    assert blocks[-1].scope is Scope.TOC
    assert blocks[-1].role is Role.UNKNOWN


def test_heading_level_uses_outline_then_style_never_size(tmp_path: Path) -> None:
    document = load(tmp_path, para("摘 要") + para("第一章 引言", style="H1"))
    blocks = tag_blocks(document)
    assert blocks[-1].role is Role.H1


# ── 选择器 ──────────────────────────────────────────────────────


def test_selectors_pick_the_expected_objects(tmp_path: Path) -> None:
    blocks = tag_blocks(load(tmp_path, full_document()))
    assert texts(select.module_titles(blocks)) == [
        "摘    要",
        "ABSTRACT",
        "目    录",
        "参考文献",
        "致    谢",
        "附    录",
    ]
    assert texts(select.keywords_c(blocks)) == ["关键词：格式；审核"]
    assert texts(select.keywords_e(blocks)) == ["Keywords: format, review"]
    assert texts(select.toc_entries(blocks)) == ["第一章 引言", "参考文献"]
    assert texts(select.chapters(blocks)) == ["第一章 引言"]
    assert texts(select.h2(blocks)) == ["附录A 名词术语"]
    assert texts(select.h1(blocks)) == []
    assert texts(select.body_paragraphs(blocks)) == ["第一章 引言", "1.1 系统概述", "正文内容。"]
    assert texts(select.ref_items(blocks)) == ["[1] 作者. 题名[M]. 出版社."]
    assert texts(select.appendix_subs(blocks)) == ["附录A 名词术语"]
    assert texts(select.empty_blocks(blocks)) == [""]
    assert select.unknown_blocks(blocks) == ()


def test_continued_table_caption_is_not_an_ordinary_table_caption(tmp_path: Path) -> None:
    body = (
        para("第一章 引言", style="H1")
        + para("表1-1 器件清单")
        + "<w:tbl><w:tr><w:tc>"
        + para("数据")
        + "</w:tc></w:tr></w:tbl>"
        + para("续表1-1")
    )
    blocks = tag_blocks(load(tmp_path, body))
    assert texts(select.captions_tab(blocks)) == ["表1-1 器件清单"]
    assert texts(select.continued_table_captions(blocks)) == ["续表1-1"]


def test_appendix_recognition_is_independent_of_level_and_case(tmp_path: Path) -> None:
    body = para("附 录") + para("附录a名词术语", style="H3") + para("正文说明内容。")
    blocks = tag_blocks(load(tmp_path, body))
    sub = blocks[1]
    assert sub.role is Role.H3  # 级别写错仍按级别给角色
    assert texts(select.appendix_subs(blocks)) == ["附录a名词术语"]  # 文本识别不受影响


def test_body_selector_excludes_table_and_object_paragraphs(tmp_path: Path) -> None:
    body = (
        para("第一章 引言", style="H1")
        + para("正文文字")
        + "<w:tbl><w:tr><w:tc>"
        + para("表格里的话")
        + "</w:tc></w:tr></w:tbl>"
        + "<w:p><w:r><w:drawing/></w:r></w:p>"
    )
    blocks = tag_blocks(load(tmp_path, body))
    assert texts(select.body_paragraphs(blocks)) == ["正文文字"]


def test_numbering_aware_selectors_let_auto_numbered_blocks_go(tmp_path: Path) -> None:
    body = (
        para("第一章 引言")
        + para("（1）资料收集", style="H4", numbering=5)
        + para("（2）需求分析", style="H4")
    )
    blocks = tag_blocks(load(tmp_path, body))
    assert texts(select.h4(blocks)) == ["（1）资料收集", "（2）需求分析"]
    assert texts(select.h4_no_auto(blocks)) == ["（2）需求分析"]


def test_reference_numbering_rules_are_mutually_exclusive_by_shared_matcher(tmp_path: Path) -> None:
    body = para("参考文献") + para("[1] 作者. 题名[M].") + para("这条文献没有编号")
    blocks = tag_blocks(load(tmp_path, body))
    items = select.ref_items(blocks)
    numbered = [b for b in items if matchers.looks_like_number(b.para.text)]
    unnumbered = [b for b in items if not matchers.looks_like_number(b.para.text)]
    assert len(numbered) + len(unnumbered) == len(items)
    assert not set(texts(tuple(numbered))) & set(texts(tuple(unnumbered)))
    assert texts(tuple(unnumbered)) == ["这条文献没有编号"]


def test_citation_runs_are_found_by_text_not_by_superscript(tmp_path: Path) -> None:
    body = (
        para("第一章 引言")
        + '<w:p><w:r><w:t>[1]</w:t></w:r><w:r><w:rPr><w:vertAlign w:val="superscript"/>'
        + "</w:rPr><w:t>[2]</w:t></w:r></w:p>"
    )
    blocks = tag_blocks(load(tmp_path, body))
    assert [r.text for r in select.citation_runs(blocks)] == ["[1]", "[2]"]
    assert [r.text for r in select.superscript_runs(blocks)] == ["[2]"]


# ── 真实语料统计（无语料时跳过）────────────────────────────────


def _corpus_docs() -> list[Path]:
    env = os.environ.get("THESIS_CORPUS_DIR")
    if env and Path(env).is_dir():
        return sorted(Path(env).glob("*.docx"))
    repo = Path(__file__).resolve().parents[2]
    fallback = repo.parent / "test2" / "corpus"
    return sorted(fallback.glob("*.docx")) if fallback.is_dir() else []


@pytest.mark.skipif(not _corpus_docs(), reason="需要真实语料（THESIS_CORPUS_DIR 或 test2/corpus）")
def test_real_corpus_scopes_and_roles() -> None:
    per_scope: Counter[Scope] = Counter()
    unknowns: Counter[Scope] = Counter()
    total = 0
    for docx in _corpus_docs():
        with pkg.Package.open(docx) as opened:
            document = parse_document(opened)
        blocks = tag_blocks(document)
        assert len(blocks) == len(document.paragraphs)
        ranges = partition(document.paragraphs)
        assert ranges and ranges[0].start == 0 and ranges[-1].end == len(document.paragraphs) - 1
        for left, right in pairwise(ranges):
            assert right.start == left.end + 1
        for block in blocks:
            per_scope[block.scope] += 1
            total += 1
            if block.role is Role.UNKNOWN:
                unknowns[block.scope] += 1

    print(f"\nreal corpus: {len(_corpus_docs())} docs, {total} paragraphs")
    print(f"  {'scope':<10}{'paras':>8}{'unknown':>9}{'ratio':>9}")
    for scope in Scope:
        count = per_scope.get(scope, 0)
        unknown = unknowns.get(scope, 0)
        ratio = f"{unknown / count:.2%}" if count else "-"
        print(f"  {scope.value:<10}{count:>8}{unknown:>9}{ratio:>9}")
    unknown_total = sum(unknowns.values())
    print(f"  {'total':<10}{total:>8}{unknown_total:>9}{unknown_total / total:.2%}")
