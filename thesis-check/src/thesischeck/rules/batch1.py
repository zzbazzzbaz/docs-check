"""批 1 规则数据表：`id + 对象选择器 + 属性提取器 + 期望值 + 依据`，一行一条。

本阶段只放**一条示范规则**，用来跑通"数据一行 + 用例两行"的形态；197 条在批 1
阶段（Phase 8）填进来，本文件的 `REGISTRY` 就是唯一注册入口，双向一致性检查读它。

对象识别一律复用 `semantics.select`（`NFR-4.3`：对象口径只定义一次），本层不新造判据。
"""

from __future__ import annotations

from collections.abc import Sequence
from operator import attrgetter
from typing import Any

from ..parse.model import Run
from ..semantics import select
from ..semantics.blocks import Block, Scope
from .base import Rule


def abstract_c_title_cjk_runs(blocks: Sequence[Block]) -> tuple[Run, ...]:
    """中文摘要标题里含中文字符的 run：模块标题段落 -> 限定中文摘要区 -> 只取中文字符 run。"""
    titles = select.module_titles(blocks)
    return select.cjk_runs(select.by_scope(titles, Scope.ABS_C))


ABS_C_02 = Rule(
    id="ABS-C-02",
    of=abstract_c_title_cjk_runs,
    prop=attrgetter("ea"),
    expect="黑体",
    src="规范原文：中文摘要标题用三号黑体",
)


REGISTRY: tuple[Rule[Any, Any], ...] = (ABS_C_02,)
