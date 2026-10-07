"""腾讯云 COS 存储实现（唯一产品实现）。

- 桶私有读写：一切文件访问由后端签发短时效预签名 URL；
- 转正 / 读原件 / 写产物 / 删除均走 SDK 同步调用（调用方 to_thread 包裹）；
- best-effort 删除失败只记日志：暂存残留由桶生命周期（`tmp/` 1 天）兜底。
"""

import logging
from urllib.parse import quote

from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosServiceError

from app.infrastructure.storage.base import FILE_NAMES, Storage

logger = logging.getLogger(__name__)

_NOT_FOUND = 404


class CosStorage(Storage):
    def __init__(
        self,
        *,
        region: str,
        secret_id: str,
        secret_key: str,
        bucket: str,
        presign_expire_seconds: int,
    ) -> None:
        config = CosConfig(
            Region=region, SecretId=secret_id, SecretKey=secret_key, Scheme="https"
        )
        self._client = CosS3Client(config)
        self._region = region
        self._bucket = bucket
        self._expires = presign_expire_seconds

    def staged_size(self, key: str) -> int | None:
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=key)
        except CosServiceError as exc:
            if exc.get_status_code() == _NOT_FOUND:
                return None
            raise
        return int(head["Content-Length"])

    def adopt_staged(self, key: str, storage_dir: str) -> None:
        self._client.copy_object(
            Bucket=self._bucket,
            Key=self._object_key(storage_dir, "original"),
            CopySource={"Bucket": self._bucket, "Key": key, "Region": self._region},
        )
        self.remove_staged(key)

    def remove_staged(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception:
            logger.warning("failed to delete staged object %s", key, exc_info=True)

    def presigned_upload_url(self, key: str) -> str:
        return self._client.get_presigned_url(
            Method="PUT", Bucket=self._bucket, Key=key, Expired=self._expires
        )

    def read_bytes(self, storage_dir: str, name: str) -> bytes:
        response = self._client.get_object(
            Bucket=self._bucket, Key=self._object_key(storage_dir, name)
        )
        return response["Body"].get_raw_stream().read()

    def save_review(self, storage_dir: str, *, marked: bytes, issues_json: bytes) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=self._object_key(storage_dir, "marked"), Body=marked
        )
        self._client.put_object(
            Bucket=self._bucket, Key=self._object_key(storage_dir, "issues"), Body=issues_json
        )

    def presigned_download_url(self, storage_dir: str, name: str, *, filename: str) -> str | None:
        key = self._object_key(storage_dir, name)
        if self.staged_size(key) is None:
            return None
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        return self._client.get_presigned_url(
            Method="GET",
            Bucket=self._bucket,
            Key=key,
            Expired=self._expires,
            Params={"response-content-disposition": disposition},
        )

    def remove(self, storage_dir: str) -> None:
        for name in FILE_NAMES:
            try:
                self._client.delete_object(
                    Bucket=self._bucket, Key=self._object_key(storage_dir, name)
                )
            except Exception:
                logger.warning(
                    "failed to delete %s/%s", storage_dir, FILE_NAMES[name], exc_info=True
                )

    @staticmethod
    def _object_key(storage_dir: str, name: str) -> str:
        filename = FILE_NAMES.get(name)
        if filename is None:
            raise ValueError(f"unknown storage name: {name!r}")
        return f"{storage_dir}/{filename}"
