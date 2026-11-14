from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class APIProblem(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []

    def error(self, request_id: str) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "request_id": request_id,
        }
