from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse


class MapServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details=None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        super().__init__(message)


def error_response(request: Request, error: MapServiceError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=error.status_code,
        headers={"X-Request-ID": request_id},
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
                "request_id": request_id,
            }
        },
    )
