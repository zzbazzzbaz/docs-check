"""对象存储冒烟（真实桶）：签发 → 直传 → 确认 → worker → 307 下载 → 对象布局 / 过期签名校验。

用法：
    uv run python -m scripts.cos_smoke --username <学生账号> --password <密码>
    # 也可用环境变量：COS_SMOKE_USERNAME / COS_SMOKE_PASSWORD / COS_SMOKE_BASE_URL

说明：
- 读 `.env`（COS_* 与 DATABASE_URL 均来自配置，密钥不出仓库）；
- 样本用工厂字节（`tests.factories`），不碰真实论文；
- 默认跑完清理 COS 对象与该提交记录；`--keep` 保留现场便于排查。
"""

import argparse
import asyncio
import os
import sys
import time
from typing import Any

import requests
from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosServiceError

from app.core.config import get_settings
from tests.factories import make_docx

DEFAULT_BASE_URL = "http://127.0.0.1:8001"
POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 120.0
EXPIRED_URL_SLEEP_SECONDS = 2.0
_OBJECT_NAMES = ("original.docx", "marked.docx", "issues.json")


def _step(message: str) -> None:
    print(f"▶ {message}")


def _ok(message: str) -> None:
    print(f"  ✅ {message}")


def _fail(message: str) -> None:
    print(f"  ❌ {message}")
    sys.exit(1)


def _build_cos_client(settings: Any) -> CosS3Client:
    return CosS3Client(
        CosConfig(
            Region=settings.cos_region,
            SecretId=settings.cos_secret_id,
            SecretKey=settings.cos_secret_key,
            Scheme="https",
        )
    )


def _head_size(client: CosS3Client, bucket: str, key: str) -> int | None:
    """HEAD 对象大小；不存在 → None（其余异常照抛）。"""
    try:
        return int(client.head_object(Bucket=bucket, Key=key)["Content-Length"])
    except CosServiceError as exc:
        if exc.get_status_code() == 404:
            return None
        raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对象存储冒烟（真实桶，读 .env）")
    parser.add_argument(
        "--base-url", default=os.environ.get("COS_SMOKE_BASE_URL", DEFAULT_BASE_URL)
    )
    parser.add_argument("--username", default=os.environ.get("COS_SMOKE_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("COS_SMOKE_PASSWORD", ""))
    parser.add_argument("--keep", action="store_true", help="保留冒烟记录与 COS 对象（默认清理）")
    args = parser.parse_args()
    if not args.username or not args.password:
        parser.error("需要学生账号：--username/--password 或 COS_SMOKE_USERNAME/COS_SMOKE_PASSWORD")
    return args


def _login(base_url: str, username: str, password: str) -> dict[str, str]:
    response = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    if response.status_code != 200:
        _fail(f"登录失败：HTTP {response.status_code} {response.text[:200]}")
    _ok(f"登录 {username}")
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _download(base_url: str, headers: dict[str, str], submission_id: int, kind: str) -> bytes:
    response = requests.get(
        f"{base_url}/api/v1/submissions/{submission_id}/{kind}",
        headers=headers,
        allow_redirects=False,
        timeout=30,
    )
    if response.status_code != 307:
        _fail(f"{kind} 下载应返回 307，实际 HTTP {response.status_code} {response.text[:200]}")
    location = response.headers.get("location", "")
    if "/" not in location or not location.startswith("https://"):
        _fail(f"{kind} 307 Location 异常：{location[:120]}")
    followed = requests.get(location, timeout=60)
    if followed.status_code != 200:
        _fail(f"{kind} 跟随预签名下载失败：HTTP {followed.status_code}")
    _ok(f"{kind}：307 → COS 直下 200（{len(followed.content)}B，{location[:60]}…）")
    return followed.content


async def _delete_submission_row(submission_id: int) -> None:
    from app.infrastructure.db.engine import create_engine
    from app.infrastructure.db.models.submission import Submission
    from app.infrastructure.db.session import create_session_factory

    settings = get_settings()
    engine = create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            row = await session.get(Submission, submission_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
    finally:
        await engine.dispose()


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    cos = _build_cos_client(settings)
    headers = _login(args.base_url, args.username, args.password)
    submission_id: int | None = None
    storage_dir: str | None = None
    try:
        sample = make_docx(["冒烟测试段落"])
        filename = "冒烟论文.docx"

        # ① 签发 → 直传 → 确认（202）
        _step("上传三段式：upload-url → PUT → confirm")
        response = requests.post(
            f"{args.base_url}/api/v1/submissions/upload-url",
            json={"filename": filename, "size": len(sample)},
            headers=headers,
            timeout=30,
        )
        if response.status_code != 200:
            _fail(f"upload-url 失败：HTTP {response.status_code} {response.text[:200]}")
        signed = response.json()
        object_key = signed["object_key"]
        assert object_key.startswith("tmp/") and object_key.endswith(".docx")
        put = requests.put(signed["upload_url"], data=sample, timeout=60)
        if put.status_code != 200:
            _fail(f"直传 PUT 失败：HTTP {put.status_code} {put.text[:200]}")
        response = requests.post(
            f"{args.base_url}/api/v1/submissions",
            json={"object_key": object_key, "filename": filename},
            headers=headers,
            timeout=30,
        )
        if response.status_code != 202:
            _fail(f"确认失败：HTTP {response.status_code} {response.text[:200]}")
        body = response.json()
        submission_id = int(body["id"])
        storage_dir = f"submissions/{object_key.removeprefix('tmp/').removesuffix('.docx')}"
        _ok(f"confirm 202（id={submission_id}，status={body['status']}）")

        # ② 等 worker → success
        _step("等待 worker 审核完成")
        status = ""
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            detail = requests.get(
                f"{args.base_url}/api/v1/submissions/{submission_id}",
                headers=headers,
                timeout=30,
            )
            if detail.status_code != 200:
                _fail(f"详情查询失败：HTTP {detail.status_code} {detail.text[:200]}")
            status = detail.json()["status"]
            if status in ("success", "failed"):
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        if status != "success":
            _fail(f"审核未成功：status={status}")
        _ok("worker 完成：success")

        # ③ 307 下载：原件字节一致、标注为 docx
        _step("307 预签名下载")
        original = _download(args.base_url, headers, submission_id, "original")
        if original != sample:
            _fail("原件字节与上传样本不一致")
        marked = _download(args.base_url, headers, submission_id, "marked")
        if marked[:2] != b"PK":
            _fail("标注文件不是 docx（PK 头缺失）")

        # ④ 对象布局：tmp 已删、三件产物齐
        _step("对象布局校验")
        if _head_size(cos, settings.cos_bucket, object_key) is not None:
            _fail("tmp 暂存对象未清理")
        sizes = {
            name: _head_size(cos, settings.cos_bucket, f"{storage_dir}/{name}")
            for name in _OBJECT_NAMES
        }
        if any(size is None for size in sizes.values()):
            _fail(f"产物缺失：{sizes}")
        _ok(f"tmp 已删；{storage_dir}/ 三件齐 {sizes}")

        # ⑤ 过期预签名 → 403
        _step("过期预签名校验")
        expired_url = cos.get_presigned_url(
            Method="GET",
            Bucket=settings.cos_bucket,
            Key=f"{storage_dir}/marked.docx",
            Expired=1,
        )
        time.sleep(EXPIRED_URL_SLEEP_SECONDS)
        expired = requests.get(expired_url, timeout=30)
        if expired.status_code != 403:
            _fail(f"过期预签名应 403，实际 HTTP {expired.status_code} {expired.text[:200]}")
        _ok("过期预签名请求被拒绝（403）")
    finally:
        if submission_id is not None and not args.keep:
            _step("清理冒烟数据（--keep 可保留）")
            if storage_dir is not None:
                for name in _OBJECT_NAMES:
                    cos.delete_object(Bucket=settings.cos_bucket, Key=f"{storage_dir}/{name}")
            asyncio.run(_delete_submission_row(submission_id))
            _ok("COS 对象与提交记录已清理")

    print("\n冒烟通过 ✅")


if __name__ == "__main__":
    main()
