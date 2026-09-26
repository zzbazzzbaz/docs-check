"""Phase 5 等价性关卡：新解析器逐字段对齐 `test2` 快照。

比对口径是**逐字段严格相等**：字段缺失、类型不同（`None` 与 `0`、`bool` 与 `int`）、
浮点精度、列表长度都算差异。只有快照里的 `path` / `tool` 两个位置性元数据不参与比对
（快照的 `path` 相对 `test2/`，与本地绝对路径无可比性）。

`test2/corpus` 或 `test2/snapshots` 不在本地时整组跳过（标 `real_corpus` + `slow`）。

无法对齐的字段必须进 `ACCEPTED` 允许清单（字段名 + 篇名 + 条数 + 原因），清单为空是
最好的结果；**不允许静默忽略**。
"""

from __future__ import annotations

import gzip
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from thesischeck.parse import compat
from thesischeck.parse.document import parse_document
from thesischeck.parse.package import Package

# ── 语料与快照位置 ──────────────────────────────────────────────
_REPO = Path(__file__).resolve().parents[2]
_TEST2 = _REPO.parent / "test2"
CORPUS = _TEST2 / "corpus"
SNAPSHOTS = _TEST2 / "snapshots"
SUITES = ("own", "ownpages", "ownborders", "owntextbox")

# 快照里相对 test2/ 的路径与工具标记，不参与解析事实比对
IGNORED_KEYS = frozenset({"path", "tool"})


@dataclass(frozen=True)
class Diff:
    """一条字段级差异。`field` 把列表下标折叠成 `[]`，便于按字段归类。"""

    path: str
    message: str

    @property
    def field(self) -> str:
        return re.sub(r"\[\d+\]", "[]", self.path)


@dataclass(frozen=True)
class AcceptedDiff:
    """一条**已接受**的差异：哪套房、哪篇、几条、为什么。"""

    suite: str
    field: str
    doc: str
    count: int
    reason: str


# 允许清单：目前为空——40 篇 x 4 套逐字段零差异。
ACCEPTED: tuple[AcceptedDiff, ...] = ()


def diff_records(
    expected: object,
    actual: object,
    path: str = "$",
    ignore: frozenset[str] = IGNORED_KEYS,
) -> list[Diff]:
    """纯函数：喂两个 JSON 值，返回差异列表。递归处理 dict / list，标量严格比对类型。"""
    out: list[Diff] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        exp_keys = set(expected) - ignore
        act_keys = set(actual) - ignore
        for key in sorted(exp_keys - act_keys):
            out.append(Diff(f"{path}.{key}", "快照里有、新解析器没有"))
        for key in sorted(act_keys - exp_keys):
            out.append(Diff(f"{path}.{key}", "新解析器有、快照里没有"))
        for key in sorted(exp_keys & act_keys):
            out.extend(diff_records(expected[key], actual[key], f"{path}.{key}", ignore))
        return out
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            out.append(Diff(f"{path}[]", f"长度 {len(expected)} != {len(actual)}"))
        for index, (exp_item, act_item) in enumerate(zip(expected, actual, strict=False)):
            out.extend(diff_records(exp_item, act_item, f"{path}[{index}]", ignore))
        return out
    if type(expected) is not type(actual):
        out.append(Diff(path, f"类型不同：{type(expected).__name__} != {type(actual).__name__}"))
    elif expected != actual:
        out.append(Diff(path, f"{expected!r} != {actual!r}"))
    return out


def _available() -> bool:
    return CORPUS.is_dir() and SNAPSHOTS.is_dir() and any(CORPUS.glob("*.docx"))


def _corpus_docs() -> list[Path]:
    return sorted(CORPUS.glob("*.docx")) if _available() else []


def _snapshot(docx: Path, suite: str) -> Path:
    return SNAPSHOTS / f"{docx.stem}.{suite}.json.gz"


# ── 纯函数自测（不需要语料）────────────────────────────────────


def test_diff_reports_no_difference_for_equal_values() -> None:
    value = {"a": [1, 2.5, None, True], "b": {"c": "x"}}
    assert diff_records(value, json.loads(json.dumps(value))) == []


def test_diff_reports_missing_and_extra_keys() -> None:
    paths = {d.path for d in diff_records({"a": 1}, {"b": 1})}
    assert paths == {"$.a", "$.b"}


def test_diff_distinguishes_none_from_zero_and_bool_from_int() -> None:
    assert diff_records({"v": None}, {"v": 0})[0].path == "$.v"
    assert diff_records({"v": True}, {"v": 1})[0].path == "$.v"


def test_diff_detects_float_precision_and_list_length() -> None:
    assert diff_records({"v": 12.0}, {"v": 12.1})[0].path == "$.v"
    assert diff_records([1, 2], [1])[0].path == "$[]"


def test_diff_folds_list_index_in_field_name() -> None:
    (difference,) = diff_records([{"v": 1}], [{"v": 2}])
    assert difference.field == "$[].v"


def test_diff_ignores_positional_metadata() -> None:
    assert diff_records({"path": "a", "tool": "own", "v": 1}, {"path": "b", "v": 1}) == []


# ── 语料关卡 ────────────────────────────────────────────────────


@pytest.mark.real_corpus
@pytest.mark.slow
@pytest.mark.skipif(not _available(), reason="需要 test2/corpus 与 test2/snapshots")
@pytest.mark.parametrize("docx", _corpus_docs(), ids=lambda p: p.stem)
def test_compat_dump_matches_snapshots(docx: Path) -> None:
    with Package.open(docx) as pkg:
        document = parse_document(pkg)
        per_suite: dict[str, list[tuple[str, Diff]]] = {}
        for suite in SUITES:
            snapshot = _snapshot(docx, suite)
            if not snapshot.exists():
                pytest.skip(f"缺少快照：{snapshot.name}")
            expected = json.loads(gzip.decompress(snapshot.read_bytes()))
            actual = compat.dump_suite(suite, pkg, document)
            per_suite[suite] = [(suite, diff) for diff in diff_records(expected, actual)]

    hits: Counter[AcceptedDiff] = Counter()
    unexpected: list[tuple[str, Diff]] = []
    for differences in per_suite.values():
        for suite, difference in differences:
            entry = next(
                (item for item in ACCEPTED if item.suite == suite and item.field == difference.field),
                None,
            )
            if entry is None:
                unexpected.append((suite, difference))
            else:
                hits[entry] += 1

    for entry in ACCEPTED:
        if hits[entry] != entry.count:
            pytest.fail(
                f"允许清单过期：{entry.suite} {entry.doc} {entry.field} "
                f"声明 {entry.count} 条，实际 {hits[entry]} 条"
            )

    if unexpected:
        lines = [f"{len(unexpected)} 条未接受的差异："]
        lines += [
            f"  {suite} {difference.path}: {difference.message}" for suite, difference in unexpected[:40]
        ]
        pytest.fail("\n".join(lines))
