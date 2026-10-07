"""multipart 上传读取工具：边读边计数，超限立即拒绝。"""

from fastapi import UploadFile

from app.services.errors import FileTooLargeError

_CHUNK_BYTES = 1024 * 1024


async def read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """读取上传内容；超过 `max_bytes` 抛 `FileTooLargeError`（413）。

    流式读取，不会把超限文件整体读进内存。
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK_BYTES):
        total += len(chunk)
        if total > max_bytes:
            raise FileTooLargeError(f"文件超过 {max_bytes // (1024 * 1024)}MB 限制")
        chunks.append(chunk)
    return b"".join(chunks)
