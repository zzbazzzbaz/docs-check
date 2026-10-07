"""跨模块共享的业务异常。

HTTP 状态码映射由 api 层负责；`code` 是稳定错误标识（前端据此映射文案），
默认取类属性，具体场景可在抛出时覆盖。
"""


class DomainError(Exception):
    """业务异常基类，api 层统一捕获转 HTTP。"""

    code = "domain_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class AlreadyExistsError(DomainError):
    """资源已存在，如用户名被占用。"""

    code = "already_exists"


class InvalidCredentialsError(DomainError):
    """登录凭证无效（用户名不存在或密码错误，不区分原因防枚举）。"""

    code = "invalid_credentials"


class NotFoundError(DomainError):
    """资源不存在。"""

    code = "not_found"


class ForbiddenError(DomainError):
    """越权访问资源。"""

    code = "forbidden"


class AccountDisabledError(ForbiddenError):
    """账号已被禁用（登录或使用中）。"""

    code = "account_disabled"


class PasswordRequiredChangeError(ForbiddenError):
    """未修改初始密码，禁止访问业务接口。"""

    code = "password_required_change"


class OldPasswordIncorrectError(DomainError):
    """修改密码时旧密码校验失败。"""

    code = "old_password_incorrect"


class UnsupportedFileTypeError(DomainError):
    """上传文件类型不支持（仅 .docx）。"""

    code = "unsupported_file_type"


class EmptyFileError(DomainError):
    """上传空文件。"""

    code = "empty_file"


class FileTooLargeError(DomainError):
    """上传文件超过大小上限。"""

    code = "file_too_large"


class InvalidActionError(DomainError):
    """当前状态下不允许的操作，如修改自己的角色。"""

    code = "invalid_action"
