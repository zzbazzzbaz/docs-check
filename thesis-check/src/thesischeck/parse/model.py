"""L1 文档模型：**只装事实**，不含任何判定，也不含作用域 / 角色。

两个刻意的设计：

1. **不含 `Scope` / `Role`**：那两个概念属于 L2 语义层。`parse` 是最底层，不能反向依赖
   `semantics`（`.importlinter` 会拦）。语义层用 `Block(para, scope, role)` 这样的包装承载它们。
2. **取不到值一律 `None`**，含义是"无法判定"，**不是**"不符合"。
   例如行距：`line_rule=exact` 时 `line_multiple` 就是 `None`，但这不是"不知道"，
   规则看 `line_rule` 就能判它不合规——所以"是不是倍率"与"倍率是多少"要分开表达。

所有节点都带 `xml`（lxml 元素引用）：批注回写靠它，调试也靠它。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lxml import etree


class Story(StrEnum):
    """段落所属的故事区。正文默认**不下钻**文本框，文本框走单独一路。"""

    MAIN = "main"
    TEXTBOX = "textbox"
    HEADER = "header"
    FOOTER = "footer"


class LineRule(StrEnum):
    AUTO = "auto"
    EXACT = "exact"
    AT_LEAST = "atLeast"


@dataclass(frozen=True, slots=True)
class NumPr:
    """**有效**自动编号（段落直接写的，或经样式链继承的）。

    `num_id == 0` 是"显式取消编号"，不是"没设置"——构造前要先判掉。
    """

    num_id: int
    ilvl: int | None = None


@dataclass(frozen=True, slots=True)
class Objects:
    """段落里内嵌的对象计数。`mc:Fallback` 里的重复写法不算。"""

    inline_images: int = 0
    floating_images: int = 0
    ole: int = 0
    omath: int = 0

    @property
    def any(self) -> bool:
        return bool(self.inline_images or self.floating_images or self.ole or self.omath)


@dataclass(frozen=True, slots=True)
class Run:
    """一个 run 的文本与**有效格式**（已走完级联，不是 run 自身的属性）。"""

    text: str
    ea: str | None
    west: str | None
    size: float | None
    bold: bool | None
    italic: bool | None
    va: str | None
    index: int
    xml: etree._Element


@dataclass(frozen=True, slots=True)
class Para:
    """一个段落的事实。字段名与规则文档用到的概念一一对应。

    `field_codes` 是**起始于本段**的真实域代码（嵌套域也算）；`section` 是本段所属分节的
    序号（1 起），页眉页脚与文本框段落为 `None`。
    """

    id: int
    story: Story
    text: str
    style: str | None
    style_id: str | None
    outline: int | None
    align: str | None
    line_rule: LineRule
    line_multiple: float | None
    line_pt: float | None
    first_line_chars: float | None
    left_chars: float | None
    right_chars: float | None
    hanging_chars: float | None
    space_before_pt: float | None
    space_after_pt: float | None
    numbering: NumPr | None
    page_break_before: bool
    keep_with_next: bool | None
    section_break: bool
    has_page_break: bool
    runs: tuple[Run, ...]
    objects: Objects
    field_codes: tuple[str, ...]
    in_table: bool
    row_end: bool
    section: int | None
    xml: etree._Element

    @property
    def is_empty(self) -> bool:
        """规则口径的空段落：无文字、无图片、无域结果（书签与批注锚点不算内容）。"""
        return not self.text.strip() and not self.objects.any


@dataclass(frozen=True, slots=True)
class Borders:
    """一个单元格四边**有没有线**（已是有效值，合成见 `document.py`）。

    OOXML 里四边都没写就是"无线"，这是确定值，不是"无法判定"。
    """

    top: bool
    bottom: bool
    left: bool
    right: bool


@dataclass(frozen=True, slots=True)
class Cell:
    """表格里的一格。`row` / `col` 从 1 起，`col` 是该格在行里的位置（合并格算作一格）。"""

    row: int
    col: int
    borders: Borders
    paragraphs: tuple[Para, ...]
    xml: etree._Element


@dataclass(frozen=True, slots=True)
class Table:
    """一个**顶层**表格。嵌套表格不单独成 Table，其段落仍留在宿主单元格里。"""

    id: int
    n_rows: int
    n_cols: int
    rows: tuple[tuple[Cell, ...], ...]
    xml: etree._Element


@dataclass(frozen=True, slots=True)
class Box:
    """一个文本框（`w:txbxContent`）。**不走正文块序列**，单独一路采集。

    `host` 是宿主段落号（最近的 `w:p` 祖先的 `Para.id`）；文本框套文本框时为 `None`。
    """

    id: int
    host: int | None
    paragraphs: tuple[Para, ...]
    xml: etree._Element


@dataclass(frozen=True, slots=True)
class Field:
    """一个**真实域**（`w:fldChar` begin/end 配成对，或 `w:fldSimple`）。

    `code` 是域代码首个词的大写（`PAGE` / `TOC` / `PAGEREF`…）；`start` / `end` 是段号
    （正文故事区的 `Para.id`）；`end_content` 是域结果**内容**的最后一段——结束标记若落在
    只有标记、没有内容的段落上，内容其实结束在上一段（TOC 的跨度用这个界定目录区）。
    """

    code: str
    start: int
    end: int
    end_content: int
    xml: etree._Element


@dataclass(frozen=True, slots=True)
class HeaderFooter:
    """一个分节某一种页眉/页脚**生效后**的引用。

    `owned` = 本节自己写了 `w:headerReference` / `w:footerReference`；否则 `part` 是从
    上一节继承来的生效部件。`page_fields` 是该部件里的 PAGE 域个数。`ref_type` 取
    `default` / `first` / `even`。
    """

    kind: str
    ref_type: str
    owned: bool
    part: str | None
    text: str
    page_fields: int
    paragraphs: tuple[Para, ...]


@dataclass(frozen=True, slots=True)
class Section:
    """一个分节。

    段落级 `w:sectPr` 结束它所在的那一节，body 级 `w:sectPr` 是最后一节；
    `headers` / `footers` 固定是 default、first、even 三个（可能没有引用、没有部件）。
    """

    index: int
    type: str
    orientation: str
    width_pt: float | None
    height_pt: float | None
    top_pt: float | None
    bottom_pt: float | None
    left_pt: float | None
    right_pt: float | None
    header_pt: float | None
    footer_pt: float | None
    page_number_format: str | None
    different_first_page: bool
    odd_and_even_pages: bool
    headers: tuple[HeaderFooter, ...]
    footers: tuple[HeaderFooter, ...]
    xml: etree._Element


@dataclass(frozen=True, slots=True)
class Document:
    """一篇文档的 L1 事实。

    `blocks` 是文件顺序的块序列，`w:p` 与 `w:tbl` 交错（内容控件透传、不下钻文本框）；
    `paragraphs` 是正文故事区的全部段落，含表格单元格内的段落，`id` 连续；
    `fields` 是正文故事区的**真实域**（页眉页脚里的域不算，在 `Section` 里）。
    """

    blocks: tuple[Para | Table, ...]
    paragraphs: tuple[Para, ...]
    tables: tuple[Table, ...]
    boxes: tuple[Box, ...]
    fields: tuple[Field, ...]
    sections: tuple[Section, ...]
    xml: etree._Element
