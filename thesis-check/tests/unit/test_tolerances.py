"""容差是配置（`NFR-5.5` / 需求 §3.3）：同一份偏差，放宽容差后结论随之改变。

容差数值只出现在 `rules.base.Tolerances`，规则只引用容差键；这里证明引擎确实把配置传了进去，
而不是把 0.5pt 之类写死在规则里。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tests.fixtures.base import BASE
from tests.fixtures.synth import size

from thesischeck.parse.document import parse_document
from thesischeck.parse.package import Package
from thesischeck.rules import REGISTRY, run_rules
from thesischeck.rules.base import Tolerances
from thesischeck.semantics.blocks import tag_context


def _reported(data: bytes, tolerances: Tolerances) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "case.docx"
        path.write_bytes(data)
        with Package.open(path) as pkg:
            document = parse_document(pkg)
    return [issue.rule for issue in run_rules(tag_context(document), REGISTRY, tolerances=tolerances)]


def test_size_tolerance_is_configurable() -> None:
    """摘要标题字号 16pt 改成 17pt：默认容差 0.5pt 判不通过，放宽到 1.0pt 即通过。"""
    data = size("中文摘要标题", 17).apply(BASE)
    assert _reported(data, Tolerances()) == ["ABS-C-03"]
    assert _reported(data, Tolerances(size_pt=1.0)) == []
