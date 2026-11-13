from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.database import check_database
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[check_database] = lambda: None
    with TestClient(app) as test_client:
        yield test_client


def test_health_success_with_controlled_database(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"status", "service", "timestamp", "database"}
    assert body["status"] == "healthy"
    assert body["service"] == "lunar-navigator-api"
    assert body["database"] == "ok"
    assert body["timestamp"].endswith("Z")
    assert datetime.fromisoformat(body["timestamp"]).utcoffset().total_seconds() == 0


def test_database_failure_returns_safe_503(client):
    def unavailable():
        raise OperationalError("SELECT 1", {}, Exception("private connection details"))

    client.app.dependency_overrides[check_database] = unavailable
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    error = assert_error(response, "DATABASE_UNAVAILABLE")
    assert error["message"] == "Database is unavailable"
    assert error["details"] == []
    assert "private connection details" not in response.text


def test_unknown_product_endpoint_uses_error_envelope(client):
    response = client.get("/api/v1/jobs")
    assert response.status_code == 404
    assert assert_error(response, "HTTP_404")["message"] == "Not Found"


def assert_error(response, code):
    assert set(response.json()) == {"error"}
    error = response.json()["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert error["code"] == code
    assert UUID(error["request_id"]).version == 4
    assert response.headers["X-Request-ID"] == error["request_id"]
    assert isinstance(error["details"], list)
    return error


@pytest.mark.parametrize(
    "content,status,code,reason",
    [
        ('{"count":"invalid"}', 422, "VALIDATION_ERROR", "int_parsing"),
        ("{", 400, "INVALID_REQUEST", "json_invalid"),
        ("{}", 400, "INVALID_REQUEST", "missing"),
        ('{"count":1,"unknown":1}', 400, "INVALID_REQUEST", "extra_forbidden"),
        ("[]", 400, "INVALID_REQUEST", "model_attributes_type"),
    ],
)
def test_validation_and_malformed_json_use_common_envelope(client, content, status, code, reason):
    class Payload(BaseModel):
        model_config = ConfigDict(extra="forbid")
        count: int

    # This route exists only in the test app to exercise the shared handlers.
    @client.app.post("/validation-probe")
    def probe(payload: Payload):
        return payload

    response = client.post(
        "/validation-probe", content=content, headers={"content-type": "application/json"}
    )
    assert response.status_code == status
    error = assert_error(response, code)
    assert error["details"][0]["reason"] == reason
    assert error["details"][0]["field"].startswith("body")


def test_health_rejects_unknown_query_fields_and_request_body(client):
    for response in (
        client.get("/api/v1/health?lat=1"),
        client.request("GET", "/api/v1/health", json={"unknown": True}),
    ):
        assert response.status_code == 400
        assert assert_error(response, "INVALID_REQUEST")["details"]


def test_request_identifiers_are_unique_and_not_taken_from_caller(client):
    supplied = "a706df04-b7c9-49c0-8eea-b53c71f86fe8"
    responses = [client.get("/missing", headers={"X-Request-ID": supplied}) for _ in range(2)]
    ids = [assert_error(response, "HTTP_404")["request_id"] for response in responses]
    assert supplied not in ids
    assert len(set(ids)) == 2


def test_unexpected_failure_has_safe_complete_error_envelope():
    app = create_app()

    @app.get("/failure-probe")
    def failure():
        raise RuntimeError("sensitive internals")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/failure-probe")
    assert response.status_code == 500
    assert assert_error(response, "INTERNAL_ERROR")["details"] == []
    assert "sensitive internals" not in response.text


def test_runtime_registers_only_health_product_route(client):
    assert set(client.get("/openapi.json").json()["paths"]) == {"/api/v1/health"}
    for method, path in (
        ("GET", "/api/v1/sites"),
        ("GET", "/api/v1/resources/csa"),
        ("POST", "/api/v1/ephemeris/now"),
        ("POST", "/api/v1/ephemeris/timeline"),
        ("POST", "/api/v1/ephemeris/compare"),
    ):
        response = client.request(method, path)
        assert response.status_code == 404
        assert_error(response, "HTTP_404")


def test_cors_only_allows_configured_origin(client):
    allowed = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    denied = client.get("/api/v1/health", headers={"Origin": "https://unlisted.example"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in allowed.headers
    assert "access-control-allow-origin" not in denied.headers


def test_wildcard_cors_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=["*"])
