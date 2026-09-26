"""公共夹具。

真实论文语料**不进版本库**（体积 + 个人信息），用环境变量 `THESIS_CORPUS_DIR` 指。
未设置时，需要它的测试自动跳过——CI 只跑合成样张与学校材料。
"""

import os
from pathlib import Path

import pytest

CORPUS_ENV = "THESIS_CORPUS_DIR"


def corpus_dir() -> Path | None:
    raw = os.environ.get(CORPUS_ENV)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


@pytest.fixture(scope="session")
def real_corpus() -> Path:
    path = corpus_dir()
    if path is None:
        pytest.skip(f"未设置 {CORPUS_ENV}，跳过需要真实语料的测试")
    return path
