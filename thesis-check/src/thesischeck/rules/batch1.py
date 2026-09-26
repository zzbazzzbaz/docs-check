"""批 1 规则的汇合点：各作用域的实现拆到独立模块，本文件不再自带规则。

示范规则 `ABS-C-02` 已并入 `abstract_c.py`；封面 / 中文摘要 / 英文摘要分别见
`cover.py` / `abstract_c.py` / `abstract_e.py`。`rules/__init__.py` 汇总所有作用域注册表，
本文件保留为空注册表，后续作用域模块挂在同一处。
"""

from __future__ import annotations

from typing import Any

from .base import Rule

REGISTRY: tuple[Rule[Any, Any], ...] = ()
