from __future__ import annotations

import logging
from typing import Any, Sequence
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    alerts,
    facilities,
    health,
    journeys,
    locations,
    saved_journeys,
    trip_intent,
    weather,
)
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("wayfinder.main")

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.log_provider_status()
    app.state.http_client = httpx.AsyncClient(
        timeout=settings.REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": settings.HTTP_USER_AGENT},
    )
    logger.info("Wayfinder API starting (env=%s)", settings.APP_ENV)
    yield
    await app.state.http_client.aclose()
    logger.info("Wayfinder API shut down")


app = FastAPI(
    title="Wayfinder API",
    description="Travel-aware location intelligence backend: routing, nearby facilities, weather, "
    "alerts, and an explainable, rule-based journey risk assessment.",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(journeys.router, prefix=API_PREFIX)
app.include_router(locations.router, prefix=API_PREFIX)
app.include_router(facilities.router, prefix=API_PREFIX)
app.include_router(weather.router, prefix=API_PREFIX)
app.include_router(alerts.router, prefix=API_PREFIX)
app.include_router(saved_journeys.router, prefix=API_PREFIX)
app.include_router(trip_intent.router, prefix=API_PREFIX)


def _json_safe_errors(errors: Sequence[Any]) -> list[Any]:
    """Pydantic v2 validation errors can carry a raw exception object inside
    ctx.error (e.g. our own @field_validator ValueError), which json.dumps
    cannot serialize. Stringify it rather than letting the response fail."""
    safe = []
    for err in errors:
        err = dict(err)
        ctx = err.get("ctx")
        if isinstance(ctx, dict) and "error" in ctx:
            ctx = dict(ctx)
            ctx["error"] = str(ctx["error"])
            err["ctx"] = ctx
        safe.append(err)
    return safe


# One consistent error envelope for every client-facing error response:
#   { "error": { "code": "SOME_CODE", "message": "human readable", "details": [...] } }
# `details` is only present for validation errors (the Pydantic error list).
# This never fires for upstream provider failures in journey/facilities/
# weather/alerts, which are always reported via `data_status` in a 200
# response instead (see docs/API_CONTRACT.md "Why always 200?").
_STATUS_CODE_NAMES = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
    500: "INTERNAL_ERROR",
}


def _error_body(code: str, message: str, details: list[Any] | None = None) -> dict[str, Any]:
    error_content: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error_content["details"] = details
    return {"error": error_content}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Consistent 422 shape for client input errors (distinct from upstream provider failures)."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body(
            "VALIDATION_ERROR",
            "Request validation failed.",
            details=_json_safe_errors(exc.errors()),
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Normalizes any HTTPException into the same error envelope as every
    other error response, instead of FastAPI's default bare {"detail": "..."}.
    Registered against Starlette's base HTTPException (not just FastAPI's
    subclass) so this also covers exceptions raised by the framework itself
    - e.g. 404 "no matching route" - not only ones a route handler raises
    manually (like facilities.py rejecting an out-of-range radius_km)."""
    code = _STATUS_CODE_NAMES.get(exc.status_code, "HTTP_ERROR")
    message = (
        exc.detail if isinstance(exc.detail, str) else "Request could not be processed."
    )
    return JSONResponse(status_code=exc.status_code, content=_error_body(code, message))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception while processing %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body("INTERNAL_ERROR", "An unexpected error occurred."),
    )