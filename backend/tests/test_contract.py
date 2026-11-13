import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from openapi_spec_validator import validate
from sqlalchemy.exc import OperationalError

from app.core.database import check_database
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "openapi.v1.yaml"
DOCUMENT = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def validator(schema):
    return Draft202012Validator(
        {**schema, "components": DOCUMENT["components"]}, format_checker=FormatChecker()
    )


def fixture(name):
    return json.loads((ROOT / "contracts" / "examples" / name).read_text(encoding="utf-8"))


def test_openapi_validity_and_references():
    validate(DOCUMENT)

    def walk(value):
        if isinstance(value, dict):
            if "$ref" in value:
                assert value["$ref"].startswith("#/")
                target = DOCUMENT
                for part in value["$ref"][2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(DOCUMENT)


def test_runtime_health_and_errors_match_the_canonical_contract():
    app = create_app()
    app.dependency_overrides[check_database] = lambda: None
    with TestClient(app) as client:
        validator({"$ref": "#/components/schemas/Health"}).validate(
            client.get("/api/v1/health").json()
        )
        for response in (client.get("/missing"), client.get("/api/v1/health?unknown=1")):
            validator({"$ref": "#/components/schemas/ErrorEnvelope"}).validate(response.json())

        def unavailable():
            raise OperationalError("SELECT 1", {}, Exception("private details"))

        app.dependency_overrides[check_database] = unavailable
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        validator({"$ref": "#/components/schemas/ErrorEnvelope"}).validate(response.json())


def test_all_contract_examples_match_request_or_response_schemas():
    checked = set()

    def walk(value):
        if isinstance(value, dict):
            if "schema" in value and "examples" in value:
                for example in value["examples"].values():
                    path = (CONTRACT.parent / example["externalValue"]).resolve()
                    assert path.is_relative_to(ROOT / "contracts" / "examples")
                    validator(value["schema"]).validate(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                    checked.add(path)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(DOCUMENT["paths"])
    assert checked == set((ROOT / "contracts" / "examples").glob("*.json"))


def test_all_agreed_routes_are_documented_and_runtime_status_is_explicit():
    expected = {
        "/health",
        "/sites",
        "/sites/{site_id}",
        "/map/layers",
        "/map/layers/{layer_id}",
        "/map/layers/{layer_id}/tiles/{matrix}/{row}/{col}",
        "/map/layers/{layer_id}/image",
        "/terrain/coverage",
        "/terrain/regions/{region_id}/heightmap",
        "/resources/csa",
        "/ephemeris/now",
        "/ephemeris/timeline",
        "/ephemeris/compare",
        "/jobs/{job_id}",
        "/jobs/{job_id}/result",
    }
    assert set(DOCUMENT["paths"]) == {"/api/v1" + path for path in expected}
    for path, operations in DOCUMENT["paths"].items():
        for operation in operations.values():
            assert operation["x-implementation-status"] == (
                "implemented" if path.endswith("/health") else "planned"
            )
            assert operation["x-reject-unknown-query-parameters"] is True
            assert operation["responses"]["429"]["headers"]["Retry-After"]["required"] is True


@pytest.mark.parametrize(
    "changes",
    [
        {"duration_days": 0},
        {"duration_days": 31},
        {"duration_days": 1.5},
        {"step_minutes": 90},
        {"observer_height_m": -1},
        {"observer_height_m": 21},
        {"visibility_margin_deg": -1},
        {"visibility_margin_deg": 6},
        {"horizon_mode": "automatic"},
        {"step_hours": 2},
        {"start_time": "2027-07-15T00:00:00"},
        {"site": {"lat": -89, "lon": 12}},
        {"site": {"latitude": 91, "longitude": 0}},
        {"site": {"latitude": 0, "longitude": -181}},
        {"site": {"latitude": 0, "longitude": 360}},
        {"site": {"site_id": "site", "latitude": 0, "longitude": 0}},
    ],
)
def test_timeline_schema_rejects_invalid_values_and_unknown_fields(changes):
    request = {
        "site": {"latitude": -89.44, "longitude": 222.1},
        "start_time": "2027-07-15T00:00:00Z",
        "duration_days": 1,
        "step_minutes": 360,
        "horizon_mode": "geometric",
        **changes,
    }
    with pytest.raises(ValidationError):
        validator({"$ref": "#/components/schemas/TimelineRequest"}).validate(request)


@pytest.mark.parametrize("longitude", [-180, 180, 222.1, 359.999])
def test_input_longitude_range_and_timezone_offsets_are_accepted(longitude):
    validator({"$ref": "#/components/schemas/NowRequest"}).validate(
        {
            "site": {"latitude": -90, "longitude": longitude},
            "target_time": "2027-07-15T02:00:00+02:00",
            "horizon_mode": "geometric",
        }
    )


def test_job_acceptance_fixture_kind_matches_submission_route():
    for endpoint, kind in (("now", "now"), ("timeline", "timeline"), ("compare", "comparison")):
        media = DOCUMENT["paths"]["/api/v1/ephemeris/" + endpoint]["post"]["responses"]["202"]
        path = media["content"]["application/json"]["examples"]["accepted"]["externalValue"]
        assert fixture(Path(path).name)["kind"] == kind


def test_illustrative_observations_have_consistent_angles_vectors_and_visibility():
    points = [fixture("observation-result.json")["point"]]
    points.extend(fixture("timeline-two-golden-windows.json")["points"])
    for point in points:
        for name in ("sun", "earth"):
            body = point[name]
            vector = body["direction_enu"]
            assert math.isclose(sum(value**2 for value in vector.values()), 1, abs_tol=1e-6)
            assert math.isclose(vector["up"], math.sin(math.radians(body["elevation_deg"])))
            azimuth = math.degrees(math.atan2(vector["east"], vector["north"])) % 360
            assert math.isclose(azimuth, body["azimuth_deg"])
            assert body["visible"] == (body["elevation_deg"] > body["horizon_elevation_deg"])
        assert point["is_golden_window"] == (point["sun"]["visible"] and point["earth"]["visible"])


def test_timeline_fixture_windows_and_duration_weighted_summary_are_consistent():
    result = fixture("timeline-two-golden-windows.json")
    start, end = (datetime.fromisoformat(result[key]) for key in ("start_time", "end_time"))
    step = timedelta(minutes=result["step_minutes"])
    points = result["points"]
    assert result["total_samples"] == len(points) == (end - start) / step
    assert [datetime.fromisoformat(point["timestamp"]) for point in points] == [
        start + index * step for index in range(len(points))
    ]
    assert len(result["golden_windows"]) == 2
    period_hours = (end - start).total_seconds() / 3600
    for key, metric, visible in (
        ("sunlight_windows", "sunlit", lambda p: p["sun"]["visible"]),
        ("earth_visibility_windows", "earth_visible", lambda p: p["earth"]["visible"]),
        ("golden_windows", "golden", lambda p: p["is_golden_window"]),
    ):
        intervals = []
        for index, point in enumerate(points):
            if visible(point):
                a, b = start + index * step, min(start + (index + 1) * step, end)
                if intervals and intervals[-1][1] == a:
                    intervals[-1] = (intervals[-1][0], b)
                else:
                    intervals.append((a, b))
        windows = result[key]
        assert [
            (datetime.fromisoformat(w["start_time"]), datetime.fromisoformat(w["end_time"]))
            for w in windows
        ] == intervals
        durations = [(b - a).total_seconds() / 3600 for a, b in intervals]
        assert [w["duration_hours"] for w in windows] == durations
        assert result["summary"][metric + "_hours"] == sum(durations)
        assert result["summary"][metric + "_pct"] == 100 * sum(durations) / period_hours
    summary = result["summary"]
    assert summary["longest_golden_window_hours"] == max(
        w["duration_hours"] for w in result["golden_windows"]
    )
    assert summary["average_sun_elevation_deg"] == sum(
        point["sun"]["elevation_deg"] for point in points
    ) / len(points)
    for body, field in (("sun", "next_sunset_at"), ("earth", "next_earthset_at")):
        transitions = [
            current["timestamp"]
            for previous, current in zip(points, points[1:], strict=False)
            if previous[body]["visible"] and not current[body]["visible"]
        ]
        assert summary[field] == (transitions[0] if transitions else None)
    assert result["meta"]["time_resolution_minutes"] == result["step_minutes"]


def test_comparison_fixtures_follow_scoring_order_normalization_and_supported_dates():
    request, result = fixture("comparison-request.json"), fixture("comparison-result.json")
    labels = [scenario["label"] for scenario in request["scenarios"]]
    assert len(labels) == len(set(labels))
    ranked = result["ranked_scenarios"]
    assert {item["label"] for item in ranked} == set(labels)
    assert result["recommended_label"] == ranked[0]["label"]
    assert [item["rank"] for item in ranked] == list(range(1, len(ranked) + 1))
    assert ranked == sorted(
        ranked,
        key=lambda item: (
            -item["score"],
            -item["summary"]["longest_golden_window_hours"],
            labels.index(item["label"]),
        ),
    )
    lower, upper = map(datetime.fromisoformat, ("2000-01-01T00:00:00Z", "2050-01-01T00:00:00Z"))
    for item in ranked:
        original = request["scenarios"][labels.index(item["label"])]
        assert item["site"]["longitude"] == pytest.approx(
            ((original["site"]["longitude"] + 180) % 360) - 180
        )
        start, end = map(datetime.fromisoformat, (item["start_time"], item["end_time"]))
        assert lower <= start < upper and end <= upper
        assert end - start == timedelta(days=request["duration_days"])
        summary = item["summary"]
        assert item["score"] == pytest.approx(
            0.4 * summary["sunlit_pct"]
            + 0.3 * summary["earth_visible_pct"]
            + 0.3 * summary["golden_pct"]
        )
        for metric in ("sunlit", "earth_visible", "golden"):
            assert summary[metric + "_pct"] == pytest.approx(
                100 * summary[metric + "_hours"] / (24 * request["duration_days"])
            )
