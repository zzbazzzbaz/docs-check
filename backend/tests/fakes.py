"""测试用内存存储替身（仅测试；**不是产品能力**，无切换开关）。

实现 `Storage` 协议，conftest 注入 `app.state.storage`；测试全程不访问网络。
"""

from urllib.parse import quote

from app.infrastructure.storage.base import FILE_NAMES, Storage


def _key(storage_dir: str, name: str) -> str:
    filename = FILE_NAMES.get(name)
    if filename is None:
        raise ValueError(f"unknown storage name: {name!r}")
    return f"{storage_dir}/{filename}"


class FakeStorage(Storage):
    """内存对象表：`objects[key] = bytes`。"""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.upload_keys: list[str] = []  # 已签发的预签名上传（测试断言用）

    # ── 测试辅助 ───────────────────────────────────────────────

    def write_staged(self, key: str, data: bytes) -> None:
        """模拟客户端直传完成：写入暂存对象。"""
        self.objects[key] = data

    def write_object(self, storage_dir: str, name: str, data: bytes) -> None:
        """测试断言 / 预置产物用：直接写 storage_dir 下的对象。"""
        self.objects[_key(storage_dir, name)] = data

    # ── Storage 协议 ───────────────────────────────────────────

    def staged_size(self, key: str) -> int | None:
        data = self.objects.get(key)
        return None if data is None else len(data)

    def adopt_staged(self, key: str, storage_dir: str) -> None:
        if key not in self.objects:
            raise FileNotFoundError(key)
        self.objects[_key(storage_dir, "original")] = self.objects.pop(key)

    def remove_staged(self, key: str) -> None:
        self.objects.pop(key, None)

    def presigned_upload_url(self, key: str) -> str:
        self.upload_keys.append(key)
        return f"https://fake-cos.example.com/{key}?q-sign-algorithm=sha1&q-signature=fake"

    def read_bytes(self, storage_dir: str, name: str) -> bytes:
        return self.objects[_key(storage_dir, name)]

    def save_review(self, storage_dir: str, *, marked: bytes, issues_json: bytes) -> None:
        self.write_object(storage_dir, "marked", marked)
        self.write_object(storage_dir, "issues", issues_json)

    def presigned_download_url(self, storage_dir: str, name: str, *, filename: str) -> str | None:
        key = _key(storage_dir, name)
        if key not in self.objects:
            return None
        return (
            f"https://fake-cos.example.com/{key}"
            f"?response-content-disposition=attachment%3B+filename%2A%3DUTF-8%27%27{quote(filename)}"
        )

    def remove(self, storage_dir: str) -> None:
        for name in FILE_NAMES:
            self.objects.pop(_key(storage_dir, name), None)
