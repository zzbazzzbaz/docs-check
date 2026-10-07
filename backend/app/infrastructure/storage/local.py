"""本地文件存储：原子写 + 防路径穿越。纯文件系统，不含业务规则。"""

import os
import shutil
from pathlib import Path

_FILE_NAMES: dict[str, str] = {
    "original": "original.docx",
    "marked": "marked.docx",
    "issues": "issues.json",
}


class LocalStorage:
    """目录布局：`{base}/submissions/{id}/{original,marked}.docx + issues.json`。"""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir.resolve()

    def submission_dir(self, submission_id: int) -> Path:
        return self._base / "submissions" / str(submission_id)

    def save_original(self, submission_id: int, original: bytes) -> str:
        """原子写 original.docx；返回相对目录 `submissions/{id}`（上传时调用）。"""
        self._atomic_write(self.submission_dir(submission_id) / _FILE_NAMES["original"], original)
        return f"submissions/{submission_id}"

    def save_review(self, submission_id: int, *, marked: bytes, issues_json: bytes) -> None:
        """原子写 marked.docx / issues.json（worker 成功后调用）。"""
        target = self.submission_dir(submission_id)
        self._atomic_write(target / _FILE_NAMES["marked"], marked)
        self._atomic_write(target / _FILE_NAMES["issues"], issues_json)

    def resolve(self, storage_dir: str, name: str) -> Path:
        """拼接路径并校验仍在存储根内（防穿越）；`name ∈ {original, marked, issues}`。"""
        filename = _FILE_NAMES.get(name)
        if filename is None:
            raise ValueError(f"unknown storage name: {name!r}")
        path = (self._base / storage_dir / filename).resolve()
        if not path.is_relative_to(self._base):
            raise ValueError(f"resolved path escapes storage root: {path}")
        return path

    def read_bytes(self, storage_dir: str, name: str) -> bytes:
        return self.resolve(storage_dir, name).read_bytes()

    def remove(self, submission_id: int) -> None:
        """best-effort 删除该提交目录（失败不抛）。"""
        shutil.rmtree(self.submission_dir(submission_id), ignore_errors=True)

    def _atomic_write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
