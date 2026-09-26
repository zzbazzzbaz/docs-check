"""L2 的块包装：把 L1 的 `Para` 与 L2 的 `(scope, role)` 组合成一个不可变块。

`Para` 是 frozen 且属于 `parse` 层，**不能**把 scope / role 塞进去——那会让 parse 反向依赖
semantics，分层契约会红。所以用 `Block(para, scope, role)` 承载。

`Scope` / `Role` 的**定义**在 `scope.py` / `roles.py`（避免与 blocks 循环依赖），这里统一
re-export，作为 L2 的单一入口。文本框与页眉页脚里的段落不属于这 8 个文档流作用域，不在此包装。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..parse.model import Document, Para
from .roles import Role, assign_role
from .scope import Scope, scope_map

__all__ = ["Block", "Role", "Scope", "tag_blocks"]


@dataclass(frozen=True, slots=True)
class Block:
    para: Para
    scope: Scope
    role: Role


def tag_blocks(doc: Document) -> tuple[Block, ...]:
    """按文档流顺序给每个段落打上 `(scope, role)`；不丢段。"""
    scopes = scope_map(doc.paragraphs)
    return tuple(
        Block(para=para, scope=scope, role=assign_role(para, scope))
        for para, scope in zip(doc.paragraphs, scopes, strict=True)
    )
