"""存储抽象：唯一产品实现 `CosStorage`（cos.py）；测试替身见 tests/fakes.py。

- 无本地磁盘后端、无后端切换（对象存储是唯一文件层，见对象存储 Spec §0.2）；
- 所有方法同步阻塞（COS SDK 同步），调用方用 `asyncio.to_thread` 包裹；
- key 布局：`tmp/{uuid}.docx` → `submissions/{uuid}/{original,marked}.docx + issues.json`。
"""

from typing import Protocol

# name → 对象名（storage_dir 下的固定布局）
FILE_NAMES: dict[str, str] = {
    "original": "original.docx",
    "marked": "marked.docx",
    "issues": "issues.json",
}


class Storage(Protocol):
    """文件层契约（8 方法）。`name ∈ {original, marked, issues}`。"""

    def staged_size(self, key: str) -> int | None:
        """HEAD 对象返回字节数；不存在 → None。"""
        ...

    def adopt_staged(self, key: str, storage_dir: str) -> None:
        """转正：copy 暂存对象 → `{storage_dir}/original.docx`，并 best-effort 清理暂存。"""
        ...

    def remove_staged(self, key: str) -> None:
        """best-effort 删除暂存对象（失败不抛，残留由桶生命周期兜底）。"""
        ...

    def presigned_upload_url(self, key: str) -> str:
        """签发预签名 PUT（绝对地址；有效期由配置决定）。"""
        ...

    def read_bytes(self, storage_dir: str, name: str) -> bytes:
        """读取对象字节；对象不存在 / 名称非法时抛异常。"""
        ...

    def save_review(self, storage_dir: str, *, marked: bytes, issues_json: bytes) -> None:
        """写入 marked.docx / issues.json（worker 成功后调用）。"""
        ...

    def presigned_download_url(self, storage_dir: str, name: str, *, filename: str) -> str | None:
        """HEAD 存在性 + 签发预签名 GET（附件名走 `filename*`）；不存在 → None。"""
        ...

    def remove(self, storage_dir: str) -> None:
        """best-effort 删除 storage_dir 下全部对象（失败不抛）。"""
        ...
