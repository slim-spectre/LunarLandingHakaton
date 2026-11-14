import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi import APIRouter
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from app.astronomy import HorizonsTransportError
from app.core.config import Settings
from app.core.problems import APIProblem
from app.main import create_app
from app.requests import NowRequest
from app.storage import MODEL_VERSION, Repository, request_key
from app.worker import run_once

ROOT = Path(__file__).resolve().parents[2]
REQUEST = {
    "site": {"latitude": -89.44, "longitude": 222.1},
    "target_time": "2027-07-15T00:00:00Z",
    "horizon_mode": "geometric",
}


def check_schema(name, body):
    document = yaml.safe_load((ROOT / "contracts/openapi.v1.yaml").read_text())
    Draft202012Validator(
        {"$ref": "#/components/schemas/" + name, "components": document["components"]},
        format_checker=FormatChecker(),
    ).validate(body)


def controlled(normalized):
    result = json.loads((ROOT / "contracts/examples/observation-result.json").read_text())
    result["site"] = normalized["site"]
    result["point"]["timestamp"] = normalized["target_time"]
    result["meta"]["model_version"] = MODEL_VERSION
    return result


def submit(repository, request=None):
    return repository.submit(NowRequest.model_validate(request or REQUEST), str(uuid4()))["job_id"]


def test_catalog_filters_and_paginates_without_scientific_properties(stage_client):
    result = stage_client.get("/api/v1/sites?category=artemis&limit=1&offset=0").json()
    check_schema("SiteList", result)
    assert result["total"] == 1 and len(result["items"]) == 1
    assert result["items"][0]["id"] == "test-artemis"
    assert stage_client.get("/api/v1/sites?offset=2").json()["items"] == []
    assert stage_client.get("/api/v1/sites?category=clps").json()["total"] == 0
    site = stage_client.get("/api/v1/sites/test-apollo").json()
    check_schema("Site", site)
    assert set(site).isdisjoint({"sunlit_pct", "golden_pct", "earth_visible_pct"})
    missing = stage_client.get("/api/v1/sites/unknown")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "SITE_NOT_FOUND"


@pytest.mark.parametrize(
    "query,status",
    [
        ("limit=0", 422),
        ("offset=-1", 422),
        ("category=other", 422),
        ("limit=no", 422),
        ("lat=1", 400),
        ("limit=1&limit=2", 400),
    ],
)
def test_catalog_query_validation(stage_client, query, status):
    response = stage_client.get("/api/v1/sites?" + query)
    assert response.status_code == status
    check_schema("ErrorEnvelope", response.json())


@pytest.mark.parametrize(
    "change,status",
    [
        ({"site": {"site_id": "test-artemis", "latitude": 0, "longitude": 0}}, 400),
        ({"site": {"lat": 0, "lon": 0}}, 400),
        ({"unknown": 1}, 400),
        ({"observer_height_m": -1}, 422),
        ({"observer_height_m": 21}, 422),
        ({"visibility_margin_deg": 6}, 422),
        ({"target_time": "2027-01-01T00:00:00"}, 422),
        ({"target_time": "1999-12-31T23:59:59Z"}, 422),
        ({"target_time": "2050-01-01T00:00:00Z"}, 422),
        ({"target_time": 10000000}, 422),
        ({"target_time": "1700000000"}, 422),
        ({"site": {"latitude": 91, "longitude": 0}}, 422),
        ({"site": {"latitude": 0, "longitude": 360}}, 422),
        ({"site": {"latitude": "1", "longitude": 0}}, 422),
        ({"site": {"site_id": "missing"}}, 404),
        ({"horizon_mode": "terrain"}, 422),
    ],
)
def test_submission_validation_has_common_errors(stage_client, change, status):
    response = stage_client.post("/api/v1/ephemeris/now", json={**REQUEST, **change})
    assert response.status_code == status
    check_schema("ErrorEnvelope", response.json())
    if change.get("horizon_mode") == "terrain":
        assert response.json()["error"]["code"] == "TERRAIN_UNAVAILABLE"


def test_post_cors_unknown_query_and_get_body(stage_client):
    preflight = stage_client.options(
        "/api/v1/ephemeris/now",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert "POST" in preflight.headers["access-control-allow-methods"]
    assert stage_client.post("/api/v1/ephemeris/now?debug=true", json=REQUEST).status_code == 400
    assert stage_client.request("GET", "/api/v1/sites", json={"unknown": 1}).status_code == 400


def test_queued_running_success_and_result_storage(stage_client, stage_repo):
    submitted = {**REQUEST, "target_time": "2027-07-15T02:00:00+02:00"}
    response = stage_client.post("/api/v1/ephemeris/now", json=submitted)
    assert response.status_code == 202
    check_schema("JobAccepted", response.json())
    job_id = response.json()["job_id"]
    assert stage_repo.job(job_id)["submitted"] == submitted
    assert stage_repo.job(job_id)["normalized"]["target_time"] == "2027-07-15T00:00:00Z"
    assert stage_repo.job(job_id)["normalized"]["site"]["longitude"] == -137.9
    assert stage_client.get(response.json()["result_url"]).status_code == 409
    check_schema("Job", stage_client.get(response.json()["status_url"]).json())
    calls = []

    def execute(normalized):
        calls.append(normalized)
        status = stage_repo.status(job_id)
        assert status["status"] == "running" and status["started_at"]
        check_schema("Job", status)
        return controlled(normalized)

    assert run_once(stage_repo, executor=execute)
    assert len(calls) == 1
    status = stage_client.get(response.json()["status_url"]).json()
    assert status["status"] == "succeeded" and status["finished_at"]
    check_schema("Job", status)
    result = stage_client.get(response.json()["result_url"]).json()
    check_schema("NowResult", result)
    assert result["site"]["surface_elevation_m"] == 0
    assert result["site"]["observer_height_m"] == 2
    assert Repository(stage_repo.engine, stage_repo.clock).result(job_id) == result


def test_catalog_and_custom_sites_resolve_to_the_same_scientific_key(stage_repo):
    a = stage_repo.resolve(
        NowRequest.model_validate({**REQUEST, "site": {"site_id": "test-artemis"}})
    )
    b = stage_repo.resolve(NowRequest.model_validate(REQUEST))
    assert a["site"]["site_id"] == "test-artemis" and b["site"]["site_id"] is None
    assert request_key(a) == request_key(b)


def test_cache_hits_are_accepted_as_queued_and_preserve_provenance(stage_client, stage_repo):
    first = submit(stage_repo)
    run_once(stage_repo, executor=controlled)
    original = stage_repo.result(first)
    response = stage_client.post(
        "/api/v1/ephemeris/now",
        json={
            **REQUEST,
            "site": {"name": "Another label", "latitude": -89.44, "longitude": -137.9},
        },
    )
    assert response.status_code == 202 and response.json()["status"] == "queued"
    calls = []
    run_once(stage_repo, executor=lambda value: calls.append(value))
    assert calls == []
    cached = stage_repo.result(response.json()["job_id"])
    assert cached["site"]["name"] == "Another label"
    assert cached["meta"]["data_status"] == "cached"
    assert cached["meta"]["sources"] == original["meta"]["sources"]
    assert cached["meta"]["generated_at"] == original["meta"]["generated_at"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_time", "2027-07-15T00:00:00.001Z"),
        ("observer_height_m", 3.0),
        ("visibility_margin_deg", 1.0),
        ("horizon_mode", "terrain"),
        ("model_version", "new-model"),
    ],
)
def test_cache_keys_include_all_calculation_parameters(stage_repo, field, value):
    normalized = stage_repo.resolve(NowRequest.model_validate(REQUEST))
    assert request_key(normalized) != request_key({**normalized, field: value})


def test_cache_keys_include_coordinates(stage_repo):
    normalized = stage_repo.resolve(NowRequest.model_validate(REQUEST))
    changed = deepcopy(normalized)
    changed["site"]["latitude"] += 0.01
    assert request_key(normalized) != request_key(changed)


def test_failure_is_structured_and_result_is_not_available(stage_client, stage_repo):
    job_id = submit(stage_repo)

    def fail(normalized):
        raise HorizonsTransportError("private upstream diagnostic")

    run_once(stage_repo, executor=fail)
    status = stage_repo.status(job_id)
    assert status["status"] == "failed"
    assert status["error"]["code"] == "ASTRONOMY_UNAVAILABLE"
    assert "private upstream" not in json.dumps(status)
    check_schema("Job", status)
    response = stage_client.get(f"/api/v1/jobs/{job_id}/result")
    assert response.status_code == 409 and response.json()["error"]["code"] == "JOB_FAILED"
    assert stage_client.get(f"/api/v1/jobs/{uuid4()}").status_code == 404


def test_expired_lease_recovers_and_fences_old_executor(stage_repo, stage_clock):
    job_id = submit(stage_repo)
    old = stage_repo.claim(10)
    assert old and stage_repo.claim(10) is None
    stage_clock[0] += timedelta(seconds=11)
    recovered = Repository(stage_repo.engine, stage_repo.clock).claim(10)
    assert recovered["id"] == job_id and recovered["lease_token"] != old["lease_token"]
    assert stage_repo.finish(recovered, result=controlled(recovered["normalized"]))
    assert not stage_repo.finish(old, error={"code": "OLD"})
    assert stage_repo.status(job_id)["status"] == "succeeded"
    assert stage_repo.job(job_id)["attempts"] == 2


def test_result_retention_at_least_seven_days(stage_repo, stage_clock):
    job_id = submit(stage_repo)
    run_once(stage_repo, executor=controlled)
    stage_clock[0] += timedelta(days=7) - timedelta(seconds=1)
    assert stage_repo.result(job_id)
    stage_clock[0] += timedelta(seconds=1)
    with pytest.raises(APIProblem) as error:
        stage_repo.result(job_id)
    assert error.value.code == "JOB_EXPIRED"
    with pytest.raises(ValueError):
        Settings(_env_file=None, result_retention_days=6)


def test_cache_expiration_requires_execution(stage_repo, stage_clock):
    submit(stage_repo)
    run_once(stage_repo, executor=controlled)
    stage_clock[0] += timedelta(hours=2)
    submit(stage_repo)
    calls = []

    def execute(value):
        calls.append(value)
        return controlled(value)

    run_once(stage_repo, executor=execute)
    assert len(calls) == 1


def test_map_router_registration_and_stage2_exclusion():
    router = APIRouter(prefix="/map")

    @router.get("/layers")
    def layers():
        return {"items": []}

    with TestClient(create_app(map_router=router)) as client:
        assert client.get("/api/v1/map/layers").json() == {"items": []}
        for path in ("timeline", "compare"):
            assert client.post("/api/v1/ephemeris/" + path, json={}).status_code == 404


def test_explicit_defaults_share_a_cache_key(stage_repo):
    implicit = stage_repo.resolve(NowRequest.model_validate(REQUEST))
    explicit = stage_repo.resolve(
        NowRequest.model_validate(
            {
                **REQUEST,
                "observer_height_m": 2.0,
                "visibility_margin_deg": 0.0,
            }
        )
    )
    assert request_key(implicit) == request_key(explicit)


def test_invalid_executor_result_fails_instead_of_succeeding(stage_repo):
    job_id = submit(stage_repo)
    run_once(stage_repo, executor=lambda value: None)
    assert stage_repo.status(job_id)["status"] == "failed"
    assert stage_repo.status(job_id)["error"]["code"] == "PROVIDER_ERROR"


def test_adapter_calls_only_the_agreed_astronomy_service(monkeypatch, stage_repo):
    from app import worker
    from app.astronomy import ObservationPoint, SourceMetadata

    calls = []
    normalized = stage_repo.resolve(NowRequest.model_validate(REQUEST))
    result = controlled(normalized)
    point = ObservationPoint.model_validate(result["point"])
    point.sources = [SourceMetadata(**source) for source in result["meta"]["sources"]]

    def calculate(**kwargs):
        calls.append(kwargs)
        return point

    monkeypatch.setattr(worker, "calculate_geometric_observation", calculate)
    output = worker.execute_observation(normalized)
    assert calls[0]["observer_height_m"] == normalized["site"]["observer_height_m"]
    assert calls[0]["longitude"] == -137.9
    assert output["point"] == result["point"]
    assert calls[0]["provider"].max_retries == 1
    normalized["target_time"] = "2027-07-15T00:00:00.001Z"
    with pytest.raises(APIProblem) as error:
        worker.execute_observation(normalized)
    assert error.value.code == "PROVIDER_TIME_MISMATCH"


def test_isolated_executor_enforces_deadline_and_terminates_child(monkeypatch):
    from app import worker

    class Receiver:
        def poll(self, timeout):
            return False

        def close(self):
            pass

    class Sender:
        def close(self):
            pass

    class Process:
        terminated = False

        def start(self):
            pass

        def is_alive(self):
            return not self.terminated

        def terminate(self):
            self.terminated = True

        def join(self, timeout):
            pass

    process = Process()

    class Context:
        def Pipe(self, duplex):
            assert not duplex
            return Receiver(), Sender()

        def Process(self, **kwargs):
            assert kwargs["daemon"] is True
            return process

    monkeypatch.setattr(worker.multiprocessing, "get_context", lambda mode: Context())
    with pytest.raises(APIProblem) as error:
        worker.isolated_execution({})
    assert error.value.code == "ASTRONOMY_TIMEOUT"
    assert process.terminated


def test_expired_payload_is_cleared_without_deleting_job_metadata(stage_repo, stage_clock):
    job_id = submit(stage_repo)
    run_once(stage_repo, executor=controlled)
    stage_clock[0] += timedelta(days=8)
    assert not run_once(stage_repo, executor=controlled)
    job = stage_repo.job(job_id)
    assert job["result"] is None
    assert job["status"] == "succeeded" and job["finished_at"] is not None
    with pytest.raises(APIProblem) as problem:
        stage_repo.result(job_id)
    assert problem.value.code == "JOB_EXPIRED"


def test_submicrosecond_request_time_is_preserved_in_the_key(stage_client, stage_repo):
    request = {**REQUEST, "target_time": "2027-07-15T02:00:00.0000001+02:00"}
    response = stage_client.post("/api/v1/ephemeris/now", json=request)
    assert response.status_code == 202
    job = stage_repo.job(response.json()["job_id"])
    assert job["normalized"]["target_time"] == "2027-07-15T00:00:00.0000001Z"
    assert job["submitted"]["target_time"] == request["target_time"]
    whole = stage_repo.resolve(NowRequest.model_validate(REQUEST))
    assert job["cache_key"] != request_key(whole)
