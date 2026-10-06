"""L2 的块包装：把 L1 的 `Para` 与 L2 的 `(scope, role)` 组合成一个不可变块。

`Para` 是 frozen 且属于 `parse` 层，**不能**把 scope / role 塞进去——那会让 parse 反向依赖
semantics，分层契约会红。所以用 `Block(para, scope, role)` 承载。

`Scope` / `Role` 的**定义**在 `scope.py` / `roles.py`（避免与 blocks 循环依赖），这里只借用、
不再转手 re-export；对层外的统一入口是 `thesischeck.semantics` 门面。文本框与页眉页脚里的段落
不属于这 8 个文档流作用域，不在此包装。

`CheckContext` 是给规则引擎的**只读上下文**：它本身就是块序列（所以既有的
`Callable[[Sequence[Block]], ...]` 选择器原样可用），另外挂上整篇级事实——分节、全部段落
（含文本框）与"包里有没有 numbering.xml"。「分页 / 页面设置 / 页眉页脚 / 自动编号」类规则
需要这些整篇事实，而它们不属于任何单个段落。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from ..parse import Document, Para, Section, Table
from .roles import Role, assign_role
from .scope import Scope, scope_map

__all__ = ["Block", "CheckContext", "tag_blocks", "tag_context"]


@dataclass(frozen=True, slots=True)
class Block:
    para: Para
    scope: Scope
    role: Role


class CheckContext(tuple[Block, ...]):
    """块序列 + 整篇只读事实。迭代 / 下标 / `len` 都按块序列语义，既有选择器无需改动。"""

    sections: tuple[Section, ...]
    paragraphs: tuple[Para, ...]
    tables: tuple[Table, ...]
    has_numbering_part: bool

    def __new__(
        cls,
        blocks: Sequence[Block],
        *,
        sections: tuple[Section, ...] = (),
        paragraphs: tuple[Para, ...] = (),
        tables: tuple[Table, ...] = (),
        has_numbering_part: bool = False,
    ) -> CheckContext:
        self = super().__new__(cls, blocks)
        self.sections = sections
        self.paragraphs = paragraphs
        self.tables = tables
        self.has_numbering_part = has_numbering_part
        return cast(CheckContext, self)


def tag_blocks(doc: Document) -> tuple[Block, ...]:
    """按文档流顺序给每个段落打上 `(scope, role)`；不丢段。"""
    scopes = scope_map(doc.paragraphs)
    return tuple(
        Block(para=para, scope=scope, role=assign_role(para, scope))
        for para, scope in zip(doc.paragraphs, scopes, strict=True)
    )


def tag_context(doc: Document) -> CheckContext:
    """构建规则引擎的上下文：块序列 + 分节 + 全部段落（含文本框）+ 表格 + numbering 信号。"""
    box_paragraphs = tuple(para for box in doc.boxes for para in box.paragraphs)
    return CheckContext(
        tag_blocks(doc),
        sections=doc.sections,
        paragraphs=(*doc.paragraphs, *box_paragraphs),
        tables=doc.tables,
        has_numbering_part=doc.has_numbering_part,
    )
