"""LocalStorage：原子写、读取、防穿越、清理。"""

from pathlib import Path

import pytest

from app.infrastructure.storage.local import LocalStorage


def _storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


def test_save_original_and_read(tmp_path: Path):
    storage = _storage(tmp_path)
    rel = storage.save_original(7, b"original-bytes")

    assert rel == "submissions/7"
    assert storage.read_bytes(rel, "original") == b"original-bytes"


def test_save_review_and_read(tmp_path: Path):
    storage = _storage(tmp_path)
    storage.save_original(7, b"o")
    storage.save_review(7, marked=b"m", issues_json=b'{"summary": {}}')

    assert storage.read_bytes("submissions/7", "marked") == b"m"
    assert storage.read_bytes("submissions/7", "issues") == b'{"summary": {}}'


def test_atomic_write_leaves_no_tmp_file(tmp_path: Path):
    storage = _storage(tmp_path)
    storage.save_review(9, marked=b"m", issues_json=b"{}")

    names = sorted(p.name for p in storage.submission_dir(9).iterdir())
    assert names == ["issues.json", "marked.docx"]


def test_resolve_rejects_traversal(tmp_path: Path):
    storage = _storage(tmp_path)

    with pytest.raises(ValueError):
        storage.resolve("../outside", "original")
    with pytest.raises(ValueError):
        storage.resolve("submissions/../../etc", "original")


def test_resolve_rejects_unknown_name(tmp_path: Path):
    storage = _storage(tmp_path)

    with pytest.raises(ValueError):
        storage.resolve("submissions/1", "password")


def test_remove_is_best_effort(tmp_path: Path):
    storage = _storage(tmp_path)
    storage.save_original(3, b"x")
    assert storage.submission_dir(3).exists()

    storage.remove(3)
    assert not storage.submission_dir(3).exists()

    storage.remove(3)  # 重复删除不抛
