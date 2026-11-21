"""Portable ASGI foundation: liveness, actual app-role DB readiness, uniform errors."""

from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from backend.access import router as access_router
from backend.auth import router as auth_router
from backend.config import Settings, get_settings
from backend.connections import dispose_pool
from backend.cycles import router as cycles_router
from backend.database import DatabaseUnavailable, check_database
from backend.drafts import router as drafts_router
from backend.feeds import router as feeds_router
from backend.internal_feeds import router as internal_feeds_router
from backend.lifecycle import plans_router
from backend.lifecycle import router as lifecycle_router
from backend.monitoring import router as monitoring_router
from backend.public import router as public_router
from backend.recovery import router as recovery_router
from backend.registry import router as registry_router
from backend.review import router as review_router
from backend.routing import WEB, private_path, unknown_api


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeInfo(StrictModel):
    service: Literal["layer1"] = "layer1"
    stage: Literal["foundation"] = "foundation"


class Checks(StrictModel):
    api: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"


class Health(StrictModel):
    service: Literal["layer1"] = "layer1"
    status: Literal["ready"] = "ready"
    checks: Checks = Checks()
    request_id: str


class ErrorDetail(StrictModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(StrictModel):
    error: ErrorDetail


def failure(request, code, message, status):
    rid = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(
            error=ErrorDetail(code=code, message=message, request_id=rid)
        ).model_dump(),
        headers={
            "Cache-Control": "private, no-store"
            if request.url.path.startswith(
                ("/api/admin/feeds/", "/api/admin/monitoring/")
            )
            else "no-store",
            **(
                {"Vary": "Cookie"}
                if request.url.path.startswith(
                    ("/api/admin/feeds/", "/api/admin/monitoring/")
                )
                else {}
            ),
            "X-Request-ID": rid,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "frame-ancestors 'none'",
            "Referrer-Policy": "same-origin",
        },
    )


def create_app():
    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            dispose_pool()

    app = FastAPI(
        title="Serbia Annual Plan Registry", version="0.2.0", lifespan=lifespan
    )

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if private_path(request.scope["path"]) or unknown_api(request, app):
            return failure(request, "NOT_FOUND", "Resource not found.", 404)
        if (
            request.url.path.startswith(
                ("/api/access/", "/api/auth/", "/api/admin/", "/api/my-plans/")
            )
            and request.method == "POST"
        ):
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > (
                    1048576 if request.url.path.startswith("/api/my-plans/") else 8192
                ):
                    return failure(
                        request, "REQUEST_TOO_LARGE", "Request is too large.", 413
                    )
                chunks.append(chunk)
            request._body = b"".join(chunks)
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - log/output must not echo secret-bearing exception strings
            response = failure(
                request, "INTERNAL_ERROR", "Service temporarily unavailable.", 500
            )
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        if request.url.path.startswith(("/api/admin/feeds/", "/api/admin/monitoring/")):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Vary"] = "Cookie"
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        codes = {
            404: ("NOT_FOUND", "Resource not found."),
            405: ("METHOD_NOT_ALLOWED", "Method not allowed."),
        }
        access_codes = {
            "PRIVATE_EMAIL_BLOCKED",
            "INVALID_INSTITUTION",
            "REQUEST_NOT_ACCEPTED",
            "STATUS_UNAVAILABLE",
            "SERVICE_UNAVAILABLE",
            "TRY_LATER",
            "INVALID_REQUEST",
            "RECOVERY_FAILED",
            "RECOVERY_REQUIRED",
            "INVALID_RECOVERY",
            "INVALID_REFERENCE",
            "INVALID_SETTINGS",
            "PLAN_UNAVAILABLE",
            "PLAN_WINDOW_CLOSED",
            "PLAN_SUBMITTED",
            "PLAN_NOT_SUBMITTED",
            "LAST_DATASET_REQUIRED",
            "PLAN_CONFLICT",
            "INVALID_DRAFT",
            "SUBMISSION_INCOMPLETE",
            "INVALID_CYCLE",
            "INVALID_THEME",
            "SETTINGS_CONFLICT",
            "SETTINGS_LOCKED",
            "REFERENCE_UNAVAILABLE",
            "STALE_REFERENCE",
            "REFERENCE_CONFLICT",
            "INVALID_LIFECYCLE",
            "INVALID_REPLACEMENT",
            "LOGIN_FAILED",
            "AUTH_REQUIRED",
            "FORBIDDEN",
            "CSRF_INVALID",
            "ORIGIN_INVALID",
            "CONFLICT",
            "INVALID_REVIEW",
            "ACCOUNT_UNAVAILABLE",
            "DOMAIN_UNCONFIRMED",
            "INSTITUTION_HAS_APPROVED_ACCOUNT",
        }
        if isinstance(exc.detail, str) and exc.detail in access_codes:
            codes[exc.status_code] = (exc.detail, "Request could not be completed.")
        code, message = codes.get(
            exc.status_code, ("REQUEST_FAILED", "Request could not be completed.")
        )
        response = failure(request, code, message, exc.status_code)
        if exc.status_code == 405 and exc.headers and "Allow" in exc.headers:
            response.headers["Allow"] = exc.headers["Allow"]
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, _exc: RequestValidationError):
        return failure(request, "INVALID_REQUEST", "Invalid request.", 422)

    @app.get("/api/runtime", response_model=RuntimeInfo)
    def runtime_info():
        return RuntimeInfo()

    @app.get(
        "/api/health", response_model=Health, responses={503: {"model": ErrorResponse}}
    )
    def health(request: Request, settings: Annotated[Settings, Depends(get_settings)]):
        try:
            check_database(settings)
        except DatabaseUnavailable:
            return failure(
                request, "DATABASE_UNAVAILABLE", "Service temporarily unavailable.", 503
            )
        return Health(request_id=request.state.request_id)

    app.include_router(access_router)
    app.include_router(cycles_router)
    app.include_router(auth_router)
    app.include_router(review_router)
    app.include_router(recovery_router)
    app.include_router(registry_router)
    app.include_router(lifecycle_router)
    app.include_router(plans_router)
    app.include_router(drafts_router)
    app.include_router(public_router)
    app.include_router(feeds_router)
    app.include_router(internal_feeds_router)
    app.include_router(monitoring_router)
    app.frontend("/", directory=WEB, fallback="index.html", check_dir=False)
    return app


app = create_app()
