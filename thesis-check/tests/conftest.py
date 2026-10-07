"""公共夹具。

测试语料随测试提交在仓内 `tests/docx`；`THESIS_CORPUS_DIR` 可覆盖指向更大的语料
（例如完整的调研语料），不设置时用仓内语料。
"""

import os
from pathlib import Path

import pytest

CORPUS_ENV = "THESIS_CORPUS_DIR"
INTERNAL_CORPUS = Path(__file__).resolve().parent / "docx"


def corpus_dir() -> Path | None:
    raw = os.environ.get(CORPUS_ENV)
    if raw:
        path = Path(raw)
        if path.is_dir():
            return path
    return INTERNAL_CORPUS if INTERNAL_CORPUS.is_dir() else None


@pytest.fixture(scope="session")
def real_corpus() -> Path:
    path = corpus_dir()
    if path is None:
        pytest.skip(f"仓内缺 tests/docx，且未设置 {CORPUS_ENV}，跳过需要真实语料的测试")
    return path
