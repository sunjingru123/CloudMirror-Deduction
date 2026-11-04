"""业务层异常。

服务层抛出这些异常，由 `app/main.py` 中的异常处理器统一转换为 HTTP 响应，
使服务层保持与 Web 框架解耦。
"""


class ServiceError(Exception):
    """服务层异常基类。"""

    status_code: int = 400

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(ServiceError):
    """资源不存在。"""

    status_code = 404


class ConflictError(ServiceError):
    """资源冲突（如名称重复、重复依赖）。"""

    status_code = 409


class InvalidOperationError(ServiceError):
    """非法操作（如自依赖）。"""

    status_code = 400
