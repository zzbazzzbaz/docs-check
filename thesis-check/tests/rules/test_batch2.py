"""批 2 规则的反例与纯函数单测（FR-8）。

端到端的命中 / 底稿合规在各作用域用例里；这里补两类：

- `TXT-52` 的其余反例（章号写错 / 序号重复），证明不是只认"跳号"；
- `TXT-49` 三线表判定、`REF-14` / `REF-15` 集合与顺序判定的纯函数单测，含
  "悬空引用不报"这类不便用文档构造的分支。
"""

from __future__ import annotations

from lxml import etree

from tests.fixtures.synth import combined, insert_formula_after, run_replace
from tests.rules.case import CASE
from thesischeck.index import Citation
from thesischeck.parse.model import Borders, Cell, Table
from thesischeck.rules.references import citation_coverage_verdict, citation_order_verdict
from thesischeck.rules.text import three_line_verdict

# ── TXT-52 反例：章号写错 / 序号重复 ────────────────────────────


def test_txt52_chapter_number_wrong_is_reported() -> None:
    CASE(
        "TXT-52",
        change=combined(
            [
                run_replace("公式段落", "(1-1)", "(1-1)", "(2-1)"),
                run_replace("结果引用段落", "本文", "式(1-1)", "式(2-1)"),
            ]
        ),
        expect_only=["TXT-52"],
    )


def test_txt52_sequence_duplicate_is_reported() -> None:
    CASE("TXT-52", change=insert_formula_after("公式段落", "1-1"), expect_only=["TXT-52"])


# ── TXT-49 纯函数：三线表判定 ───────────────────────────────────


def _cell(row: int, col: int, *, top: bool = False, bottom: bool = False, **sides: bool) -> Cell:
    return Cell(
        row=row,
        col=col,
        borders=Borders(
            top=top, bottom=bottom, left=sides.get("left", False), right=sides.get("right", False)
        ),
        paragraphs=(),
        xml=etree.Element("tc"),
    )


def _table(rows: tuple[tuple[Cell, ...], ...], *, conditional: bool = False) -> Table:
    return Table(
        id=1,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        rows=rows,
        style_conditional_borders=conditional,
        xml=etree.Element("tbl"),
    )


def test_three_line_verdict_accepts_header_line() -> None:
    rows = (
        (_cell(1, 1, top=True, bottom=True), _cell(1, 2, top=True, bottom=True)),
        (_cell(2, 1, bottom=True), _cell(2, 2, bottom=True)),
    )
    assert three_line_verdict(_table(rows)) == "合规"


def test_three_line_verdict_reports_vertical_line() -> None:
    rows = (
        (
            _cell(1, 1, top=True, bottom=True, right=True),
            _cell(1, 2, top=True, bottom=True, left=True),
        ),
    )
    assert three_line_verdict(_table(rows)) == "存在竖线"


def test_three_line_verdict_reports_missing_header_line() -> None:
    rows = (
        (_cell(1, 1, top=True), _cell(1, 2, top=True)),
        (_cell(2, 1, bottom=True), _cell(2, 2, bottom=True)),
    )
    assert three_line_verdict(_table(rows)) == "缺表头行下框线"


def test_three_line_verdict_is_undetermined_when_only_style_may_draw_lines() -> None:
    rows = (
        (_cell(1, 1, top=True), _cell(1, 2, top=True)),
        (_cell(2, 1, bottom=True), _cell(2, 2, bottom=True)),
    )
    assert three_line_verdict(_table(rows, conditional=True)) is None


def test_three_line_verdict_single_row_needs_no_internal_line() -> None:
    rows = ((_cell(1, 1, top=True, bottom=True), _cell(1, 2, top=True, bottom=True)),)
    assert three_line_verdict(_table(rows)) == "合规"


# ── REF-14 / REF-15 纯函数 ──────────────────────────────────────


def _citation(no: int, order: int) -> Citation:
    return Citation(no=no, para=0, order=order)


def test_ref14_reports_uncited_entry() -> None:
    assert citation_coverage_verdict(((1, 2), (_citation(1, 1),))) == "正文未引用：[2]"


def test_ref14_does_not_report_a_dangling_citation() -> None:
    payload = ((1, 2), (_citation(1, 1), _citation(2, 2), _citation(9, 3)))
    assert citation_coverage_verdict(payload) == "合规"


def test_ref14_is_undetermined_without_citations() -> None:
    assert citation_coverage_verdict(((1, 2), None)) is None


def test_ref15_reports_first_inversion() -> None:
    payload = ((1, 2), (_citation(2, 1), _citation(1, 2)))
    assert citation_order_verdict(payload) == "第 1 个引用是 [2]，与从 1 起的顺序不符"


def test_ref15_accepts_natural_order() -> None:
    payload = ((1, 2), (_citation(1, 1), _citation(2, 2)))
    assert citation_order_verdict(payload) == "合规"
