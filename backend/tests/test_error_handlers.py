from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.error_handlers import register_error_handlers
from app.services.errors import (
    AccountDisabledError,
    DomainError,
    EmptyFileError,
    FileTooLargeError,
    ForbiddenError,
    InvalidActionError,
    NotFoundError,
    OldPasswordIncorrectError,
    PasswordRequiredChangeError,
    UnsupportedFileTypeError,
)

PASSWORD = "secret123"


async def test_route_errors_use_unified_body(client):
    """真实路由：业务异常统一转为 {"detail": str, "code": str}，route 内不再 try/except。"""
    # 未知用户登录 → 401（由 InvalidCredentialsError 映射）
    r = await client.post("/api/v1/auth/login", json={"username": "nobody", "password": PASSWORD})
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "invalid_credentials"
    assert isinstance(r.json()["detail"], str)


async def test_unmapped_domain_error_is_generic_500():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/mapped")
    async def _mapped() -> None:
        raise NotFoundError("user 999 not found")

    @app.get("/unmapped")
    async def _unmapped() -> None:
        raise DomainError("db exploded: secret dsn")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/mapped")
        assert r.status_code == 404, r.text
        assert r.json() == {"detail": "user 999 not found", "code": "not_found"}

        # 未登记的子类 → 500 且不泄露异常信息
        r = await c.get("/unmapped")
        assert r.status_code == 500, r.text
        assert r.json() == {"detail": "internal server error", "code": "internal_error"}


async def test_new_domain_errors_map_to_status_and_code():
    """M3 新增异常：状态码 + 稳定 code（继承类走 MRO，只登记基类）。"""
    cases: list[tuple[str, DomainError, int, str]] = [
        ("forbidden", ForbiddenError("无权访问该资源"), 403, "forbidden"),
        ("disabled", AccountDisabledError("账号已被禁用，请联系管理员"), 403, "account_disabled"),
        (
            "password-required",
            PasswordRequiredChangeError("请先修改初始密码"),
            403,
            "password_required_change",
        ),
        ("old-password", OldPasswordIncorrectError("旧密码错误"), 400, "old_password_incorrect"),
        (
            "file-type",
            UnsupportedFileTypeError("仅支持 .docx 文件"),
            400,
            "unsupported_file_type",
        ),
        ("empty-file", EmptyFileError("请选择文件"), 400, "empty_file"),
        ("too-large", FileTooLargeError("文件超过 50MB 限制"), 413, "file_too_large"),
    ]

    app = FastAPI()
    register_error_handlers(app)
    for path, exc, *_ in cases:

        def make_handler(error: DomainError = exc):
            async def handler() -> None:
                raise error

            return handler

        app.get(f"/{path}")(make_handler())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for path, _exc, expected_status, expected_code in cases:
            r = await c.get(f"/{path}")
            assert r.status_code == expected_status, (path, r.text)
            assert r.json()["code"] == expected_code, (path, r.text)
            assert isinstance(r.json()["detail"], str)


async def test_invalid_action_with_custom_code():
    """实例级 code 覆盖：InvalidActionError + 场景 code（如 password_unchanged）。"""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/password-unchanged")
    async def _unchanged() -> None:
        raise InvalidActionError("新密码不能与旧密码相同", code="password_unchanged")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/password-unchanged")
        assert r.status_code == 400, r.text
        assert r.json()["code"] == "password_unchanged"
        assert r.json()["detail"] == "新密码不能与旧密码相同"
