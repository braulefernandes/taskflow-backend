from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: object | None = None,
) -> JSONResponse:
    content: dict[str, object] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details is not None:
        content["error"]["details"] = details  # type: ignore[index]

    return JSONResponse(status_code=status_code, content=content)


def sanitize_validation_errors(errors: list[dict[str, object]]) -> list[dict[str, object]]:
    sanitized_errors: list[dict[str, object]] = []
    for error in errors:
        sanitized_errors.append(
            {
                key: value
                for key, value in error.items()
                if key not in {"input", "ctx"}
            }
        )
    return sanitized_errors


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(
        _request: Request,
        exc: AppException,
    ) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return error_response(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="Dados de entrada invalidos.",
            details=sanitize_validation_errors(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        _request: Request,
        _exc: Exception,
    ) -> JSONResponse:
        return error_response(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="internal_server_error",
            message="Erro interno inesperado.",
        )
