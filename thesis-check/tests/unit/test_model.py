"""模型：只读、省内存、事实齐、且不掺语义。

这些是设计约定，破了会静默影响上层：
- 模型可变 -> 语义层就地改块，两层纠缠
- 模型里冒出 `scope` / `role` -> `parse` 反向依赖 `semantics`，分层契约失败
- `None` 被当成 0 或空串 -> "无法判定"被当成"不符合"，产生幽灵问题
"""

import dataclasses

import pytest
from lxml import etree

from thesischeck.parse import model as m

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def element() -> etree._Element:
    return etree.fromstring(f'<w:p xmlns:w="{W_NS}"/>'.encode())


def para(**over: object) -> m.Para:
    """一个只填必填项的段落，测试里按需覆写。"""
    base: dict[str, object] = {
        "id": 0,
        "story": m.Story.MAIN,
        "text": "",
        "style": None,
        "style_id": None,
        "outline": None,
        "align": None,
        "line_rule": m.LineRule.AUTO,
        "line_multiple": 1.0,
        "line_pt": None,
        "first_line_chars": None,
        "left_chars": None,
        "right_chars": None,
        "hanging_chars": None,
        "space_before_pt": None,
        "space_after_pt": None,
        "numbering": None,
        "page_break_before": False,
        "keep_with_next": None,
        "section_break": False,
        "has_page_break": False,
        "runs": (),
        "objects": m.Objects(),
        "field_codes": (),
        "in_table": False,
        "row_end": False,
        "section": None,
        "xml": element(),
    }
    base.update(over)
    return m.Para(**base)  # type: ignore[arg-type]


def test_story_and_line_rule_values_are_stable() -> None:
    """这些值是写进报告与快照的字面量，改动会静默破坏历史一致性。"""
    assert m.Story.MAIN.value == "main"
    assert m.Story.TEXTBOX.value == "textbox"
    assert m.Story.HEADER.value == "header"
    assert m.Story.FOOTER.value == "footer"
    assert m.LineRule.AUTO.value == "auto"
    assert m.LineRule.EXACT.value == "exact"
    assert m.LineRule.AT_LEAST.value == "atLeast"


def test_numpr_defaults() -> None:
    numbering = m.NumPr(num_id=1)
    assert numbering.num_id == 1
    assert numbering.ilvl is None


def test_objects_any() -> None:
    assert not m.Objects().any
    assert m.Objects(inline_images=1).any
    assert m.Objects(omath=2).any


def test_model_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        para().text = "changed"  # type: ignore


def test_model_uses_slots() -> None:
    assert not hasattr(para(), "__dict__")


def test_model_has_no_semantics_fields() -> None:
    """scope / role 属于 L2；模型里出现它们就等于 parse 依赖 semantics。"""
    names = {f.name for f in dataclasses.fields(m.Para)}
    assert "scope" not in names
    assert "role" not in names


@pytest.mark.parametrize(
    ("over", "expected"),
    [
        ({}, True),
        ({"text": "   "}, True),
        ({"text": "有字"}, False),
        ({"objects": m.Objects(inline_images=1)}, False),
        ({"text": "\t"}, True),
    ],
)
def test_is_empty_follows_the_rule_definition(over: dict[str, object], expected: bool) -> None:
    """空段落 = 无文字、无图片、无域结果。纯空白算空，有对象就不算。"""
    assert para(**over).is_empty is expected


def test_exact_line_spacing_is_not_expressed_as_none_multiple() -> None:
    """行距为 exact 时，"不是倍率"与"倍率是多少"要分开表达。

    若只留 `line_multiple=None`，规则会把它读成"无法判定"而放过一个明确的违规。
    """
    fixed = para(line_rule=m.LineRule.EXACT, line_multiple=None, line_pt=20.0)
    assert fixed.line_rule is m.LineRule.EXACT
    assert fixed.line_pt == 20.0
    assert fixed.line_multiple is None


def test_run_carries_effective_values_only() -> None:
    run = m.Run(
        text="引言",
        ea="黑体",
        west="Times New Roman",
        size=16.0,
        bold=False,
        italic=None,
        va=None,
        index=0,
        xml=element(),
    )
    assert (run.ea, run.west, run.size) == ("黑体", "Times New Roman", 16.0)
    assert run.va is None
