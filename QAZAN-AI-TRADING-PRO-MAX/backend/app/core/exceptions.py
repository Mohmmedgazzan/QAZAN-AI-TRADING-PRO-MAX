from datetime import datetime, timezone
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger("qazan.exceptions")


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class ExternalMarketDataError(AppError):
    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(
            code="EXTERNAL_MARKET_DATA_ERROR",
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details,
        )


class DatabaseError(AppError):
    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(
            code="DATABASE_ERROR",
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


def _error_payload(
    request: Request,
    code: str,
    message: str,
    details: str | None = None,
) -> dict:
    request_id = getattr(request.state, "request_id", None)
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
            "path": str(request.url.path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "[%s] %s (%s)",
            exc.code,
            exc.message,
            exc.details or "no details",
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(request, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        details = "; ".join(
            f"{'.'.join(str(loc) for loc in err.get('loc', []))}: {err.get('msg', '')}"
            for err in exc.errors()
        )
        logger.warning(
            "Validation error on %s: %s",
            request.url.path,
            details,
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload(
                request,
                "VALIDATION_ERROR",
                "Invalid request parameters.",
                details,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "Unhandled server exception on %s: %s",
            request.url.path,
            str(exc),
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(
                request,
                "INTERNAL_SERVER_ERROR",
                "An unexpected internal error occurred.",
                str(exc),
            ),
        )
