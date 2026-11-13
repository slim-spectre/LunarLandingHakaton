from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.core.config import get_settings
from app.core.database import check_database


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["healthy"] = "healthy"
    service: Literal["lunar-navigator-api"] = "lunar-navigator-api"
    timestamp: str = Field(pattern="Z$", json_schema_extra={"format": "date-time"})
    database: Literal["ok"] = "ok"


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    reason: str = Field(min_length=1)


class APIError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern="^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1)
    details: list[ErrorDetail]
    request_id: UUID


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: APIError


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=status,
        headers={"X-Request-ID": request_id},
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
                "request_id": request_id,
            }
        },
    )


async def reject_health_query(request: Request) -> None:
    if request.query_params:
        raise RequestValidationError(
            [{"type": "extra_forbidden", "loc": ("query", name)} for name in request.query_params]
        )
    async for chunk in request.stream():
        if chunk:
            raise RequestValidationError([{"type": "unexpected_body", "loc": ("body",)}])


def create_app() -> FastAPI:
    app = FastAPI(title="Lunar Navigator API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def request_identifier(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        structural = {
            "json_invalid",
            "missing",
            "extra_forbidden",
            "unexpected_body",
            "model_attributes_type",
            "model_type",
            "list_type",
            "dict_type",
        }
        errors = exc.errors()
        malformed = any(error["type"] in structural for error in errors)
        details = [
            {"field": ".".join(str(part) for part in error["loc"]), "reason": error["type"]}
            for error in errors
        ]
        return error_response(
            request,
            400 if malformed else 422,
            "INVALID_REQUEST" if malformed else "VALIDATION_ERROR",
            "Invalid request structure" if malformed else "Request validation failed",
            details,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        response = error_response(
            request, exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail)
        )
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        return error_response(request, 500, "INTERNAL_ERROR", "Internal server error")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return error_response(request, 503, "DATABASE_UNAVAILABLE", "Database is unavailable")

    @app.get(
        "/api/v1/health",
        response_model=Health,
        dependencies=[Depends(reject_health_query)],
        responses={status: {"model": ErrorEnvelope} for status in (400, 500, 503)},
    )
    def health(database: Annotated[None, Depends(check_database)]) -> Health:
        return Health(timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"))

    return app


app = create_app()
