"""CosStorage 离线单测：不访问网络。

预签名 URL 走真实签名逻辑（本地计算），网络调用（head / copy / delete / get / put）
走桩代理记录并返回预设值；另覆盖 key 映射、404 → None、best-effort 语义。
"""

import io
from typing import Any
from urllib.parse import quote as urlquote

import pytest
from qcloud_cos import CosS3Client
from qcloud_cos.cos_exception import CosServiceError

from app.infrastructure.storage.cos import CosStorage

REGION = "ap-beijing"
BUCKET = "docx-check-1327210567"
KEY = f"tmp/{'a' * 32}.docx"
SUBMISSIONS_DIR = f"submissions/{'b' * 32}"


def _service_error(status_code: int) -> CosServiceError:
    return CosServiceError("HEAD", {"code": "NoSuchKey", "message": "not found"}, status_code)


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def get_raw_stream(self) -> io.BytesIO:
        return io.BytesIO(self._data)


class _StubClient:
    """代理真实 client：签名方法直通（离线可用），网络方法记录 + 返回预设值。"""

    def __init__(self, real: CosS3Client) -> None:
        self._real = real
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.head_response: dict[str, str] | None = None
        self.head_error: CosServiceError | None = None
        self.fail_delete_keys: set[str] = set()
        self.object_body = b""

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def _record(self, name: str, kwargs: dict[str, Any]) -> None:
        self.calls.append((name, kwargs))

    def head_object(self, **kwargs: Any) -> dict[str, str]:
        self._record("head_object", kwargs)
        if self.head_error is not None:
            raise self.head_error
        if self.head_response is None:
            raise _service_error(404)
        return self.head_response

    def copy_object(self, **kwargs: Any) -> None:
        self._record("copy_object", kwargs)

    def delete_object(self, **kwargs: Any) -> None:
        self._record("delete_object", kwargs)
        if kwargs["Key"] in self.fail_delete_keys:
            raise _service_error(500)

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self._record("get_object", kwargs)
        return {"Body": _Body(self.object_body)}

    def put_object(self, **kwargs: Any) -> None:
        self._record("put_object", kwargs)

    def call_keys(self, method: str) -> list[str]:
        return [str(kwargs["Key"]) for name, kwargs in self.calls if name == method]


@pytest.fixture
def cos(monkeypatch: pytest.MonkeyPatch) -> tuple[CosStorage, _StubClient]:
    storage = CosStorage(
        region=REGION,
        secret_id="AKIDfake",
        secret_key="fake",
        bucket=BUCKET,
        presign_expire_seconds=600,
    )
    stub = _StubClient(storage._client)
    monkeypatch.setattr(storage, "_client", stub)
    return storage, stub


def test_presigned_upload_url_bucket_domain_and_key(cos):
    storage, _ = cos
    url = storage.presigned_upload_url(KEY)

    assert url.startswith(f"https://{BUCKET}.cos.{REGION}.myqcloud.com/{KEY}?")
    assert "q-sign-algorithm=sha1" in url
    assert "q-signature=" in url


def test_presigned_download_url_utf8_disposition(cos):
    storage, stub = cos
    stub.head_response = {"Content-Length": "1234"}

    url = storage.presigned_download_url(SUBMISSIONS_DIR, "original", filename="论文初稿.docx")

    assert url is not None
    assert url.startswith(
        f"https://{BUCKET}.cos.{REGION}.myqcloud.com/{SUBMISSIONS_DIR}/original.docx?"
    )
    assert "attachment%3B+filename%2A%3DUTF-8%27%27" in url
    assert urlquote(urlquote("论文初稿.docx")) in url
    assert stub.calls[0] == (
        "head_object",
        {"Bucket": BUCKET, "Key": f"{SUBMISSIONS_DIR}/original.docx"},
    )


def test_presigned_download_url_returns_none_when_missing(cos):
    storage, _ = cos

    assert (
        storage.presigned_download_url(SUBMISSIONS_DIR, "marked", filename="x.marked.docx") is None
    )


def test_staged_size_returns_none_on_404_and_reraises_others(cos):
    storage, stub = cos
    stub.head_response = {"Content-Length": "47"}
    assert storage.staged_size(KEY) == 47

    stub.head_response = None
    assert storage.staged_size(KEY) is None

    stub.head_error = _service_error(500)
    with pytest.raises(CosServiceError):
        storage.staged_size(KEY)


def test_adopt_staged_copies_then_cleans_tmp(cos):
    storage, stub = cos

    storage.adopt_staged(KEY, SUBMISSIONS_DIR)

    assert stub.calls == [
        (
            "copy_object",
            {
                "Bucket": BUCKET,
                "Key": f"{SUBMISSIONS_DIR}/original.docx",
                "CopySource": {"Bucket": BUCKET, "Key": KEY, "Region": REGION},
            },
        ),
        ("delete_object", {"Bucket": BUCKET, "Key": KEY}),
    ]


def test_adopt_staged_tolerates_cleanup_failure(cos):
    storage, stub = cos
    stub.fail_delete_keys = {KEY}

    storage.adopt_staged(KEY, SUBMISSIONS_DIR)  # 不抛：copy 成功即可，残留由生命周期兜底

    assert [name for name, _ in stub.calls] == ["copy_object", "delete_object"]


def test_remove_is_best_effort_over_three_objects(cos):
    storage, stub = cos
    stub.fail_delete_keys = {f"{SUBMISSIONS_DIR}/marked.docx"}

    storage.remove(SUBMISSIONS_DIR)  # marked 删除失败不影响其余，也不抛

    assert stub.call_keys("delete_object") == [
        f"{SUBMISSIONS_DIR}/original.docx",
        f"{SUBMISSIONS_DIR}/marked.docx",
        f"{SUBMISSIONS_DIR}/issues.json",
    ]


def test_read_bytes_and_rejects_unknown_name(cos):
    storage, stub = cos
    stub.object_body = b"PK\x03\x04content"

    assert storage.read_bytes(SUBMISSIONS_DIR, "original") == b"PK\x03\x04content"
    assert stub.call_keys("get_object") == [f"{SUBMISSIONS_DIR}/original.docx"]

    with pytest.raises(ValueError):
        storage.read_bytes(SUBMISSIONS_DIR, "password")


def test_save_review_writes_marked_and_issues(cos):
    storage, stub = cos

    storage.save_review(SUBMISSIONS_DIR, marked=b"m", issues_json=b"{}")

    puts = [(kwargs["Key"], kwargs["Body"]) for name, kwargs in stub.calls if name == "put_object"]
    assert puts == [
        (f"{SUBMISSIONS_DIR}/marked.docx", b"m"),
        (f"{SUBMISSIONS_DIR}/issues.json", b"{}"),
    ]
