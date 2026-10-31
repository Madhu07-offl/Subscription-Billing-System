"""Error handling in the exact shape of contract/API.md section 4:

    {"error": {"code": "VALIDATION_ERROR", "message": "...", "details": [{"field": "...", "message": "..."}]}}
"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

VALIDATION_ERROR = "VALIDATION_ERROR"
UNAUTHENTICATED = "UNAUTHENTICATED"
FORBIDDEN = "FORBIDDEN"
NOT_FOUND = "NOT_FOUND"
CONFLICT = "CONFLICT"
BUSINESS_RULE = "BUSINESS_RULE"
INTERNAL = "INTERNAL"

_STATUS = {
    VALIDATION_ERROR: 400,
    UNAUTHENTICATED: 401,
    FORBIDDEN: 403,
    NOT_FOUND: 404,
    CONFLICT: 409,
    BUSINESS_RULE: 422,
    INTERNAL: 500,
}
_CODE_FOR_STATUS = {v: k for k, v in _STATUS.items()}


class AppError(Exception):
    """Raise from services/deps. Carries the contract error code; the handler builds the response."""

    def __init__(self, code: str, message: str, details: list[dict[str, str]] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.status_code = _STATUS[code]

    @classmethod
    def validation(cls, message: str, field: str | None = None) -> "AppError":
        details = [{"field": field, "message": message}] if field else None
        return cls(VALIDATION_ERROR, message, details)

    @classmethod
    def unauthenticated(cls, message: str = "Authentication required") -> "AppError":
        return cls(UNAUTHENTICATED, message)

    @classmethod
    def forbidden(cls, message: str = "You do not have access to this resource") -> "AppError":
        return cls(FORBIDDEN, message)

    @classmethod
    def not_found(cls, message: str = "Not found") -> "AppError":
        return cls(NOT_FOUND, message)

    @classmethod
    def conflict(cls, message: str) -> "AppError":
        return cls(CONFLICT, message)

    @classmethod
    def business_rule(cls, message: str, details: list[dict[str, str]] | None = None) -> "AppError":
        return cls(BUSINESS_RULE, message, details)


def error_body(code: str, message: str, details: list[dict[str, str]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return {"error": body}


def _field_name(loc: tuple[Any, ...]) -> str:
    """('body', 'newPassword') -> 'newPassword'; ('query', 'limit') -> 'limit'; nested joined with dots."""
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header", "cookie")]
    return ".".join(parts)


def _clean_message(msg: str) -> str:
    return msg.removeprefix("Value error, ")


async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(error_body(exc.code, exc.message, exc.details), exc.status_code, headers=headers)


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [{"field": _field_name(e["loc"]), "message": _clean_message(e["msg"])} for e in exc.errors()]
    return JSONResponse(error_body(VALIDATION_ERROR, "Invalid input", details), 400)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _CODE_FOR_STATUS.get(exc.status_code)
    if code is None:
        # 405 and other framework statuses have no contract code; keep the status, use the closest code.
        code = NOT_FOUND if exc.status_code == 405 else (VALIDATION_ERROR if exc.status_code < 500 else INTERNAL)
    message = "Not found" if exc.status_code == 404 else str(exc.detail)
    return JSONResponse(error_body(code, message), exc.status_code, headers=getattr(exc, "headers", None))


async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(error_body(INTERNAL, "Internal server error"), 500)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled)
