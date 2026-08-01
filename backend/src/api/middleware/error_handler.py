"""Global exception handlers producing RFC 7807 Problem Details (Phase 10 §4)."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("erp.api")


def _problem(status_code: int, title: str, detail: str, instance: str, errors: list | None = None) -> JSONResponse:
    body = {
        "type": f"urn:erp:error:{title.lower().replace(' ', '-')}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(status_code=status_code, content=body)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return _problem(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Validation Failed",
            "One or more fields failed validation",
            str(request.url.path),
            errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return _problem(exc.status_code, exc.__class__.__name__, str(exc.detail), str(request.url.path))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # NFR-OBS-002: every unhandled exception is captured with its stack
        # trace and request context before the generic 500 is returned to
        # the client — the client never sees internals, but this is not lost.
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return _problem(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal Server Error",
            "An unexpected error occurred",
            str(request.url.path),
        )
