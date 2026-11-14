"""Deterministic unit tests for JPL Horizons production provider.

Verifies parser correctness against Stage 0 reference fixtures, detection of
errors in HTTP 200, bounded network retry behavior, timeouts, coordinate/altitude
conversion, and provenance metadata preservation.
"""

from __future__ import annotations

import json
import os
from datetime import UTC
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.astronomy.horizons import (
    EphemerisObservation,
    HorizonsHttpError,
    HorizonsParseError,
    HorizonsProvider,
    HorizonsProviderError,
    HorizonsTransportError,
    build_horizons_params,
    meters_to_km,
    normalize_longitude,
    parse_horizons_response,
    parse_observation_row,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "reference" / "horizons"


def load_fixture(filename: str) -> dict:
    fixture_path = FIXTURES_DIR / filename
    assert fixture_path.exists(), f"Fixture file not found: {fixture_path}"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


# --- 1. Real Fixture Parsing ---


def test_parse_real_shackleton_sun_fixture():
    fixture = load_fixture("shackleton-sun.json")
    observations, provider_name, ephem_source = parse_horizons_response(fixture["raw_response"])

    assert len(observations) == 1
    obs = observations[0]
    assert obs["timestamp"] == "2027-07-15T12:00:00Z"
    assert obs["azimuth_deg"] == pytest.approx(177.278712, abs=1e-6)
    assert obs["elevation_deg"] == pytest.approx(-1.088272, abs=1e-6)
    assert obs["solar_presence"] is None
    assert obs["interfering_marker"] is None
    assert provider_name == "NASA/JPL Horizons API"
    assert ephem_source == "DE441"


def test_parse_real_shackleton_earth_fixture():
    fixture = load_fixture("shackleton-earth.json")
    observations, provider_name, ephem_source = parse_horizons_response(fixture["raw_response"])

    assert len(observations) == 1
    obs = observations[0]
    assert obs["timestamp"] == "2027-07-15T12:00:00Z"
    assert obs["azimuth_deg"] == pytest.approx(142.714718, abs=1e-6)
    assert obs["elevation_deg"] == pytest.approx(-6.178829, abs=1e-6)
    assert provider_name == "NASA/JPL Horizons API"
    assert ephem_source == "DE441"


def test_parse_real_faustini_sun_with_solar_presence_marker():
    fixture = load_fixture("faustini-sun.json")
    observations, _, _ = parse_horizons_response(fixture["raw_response"])

    assert len(observations) == 1
    obs = observations[0]
    assert obs["timestamp"] == "2027-07-15T12:00:00Z"
    assert obs["azimuth_deg"] == pytest.approx(322.365998, abs=1e-6)
    assert obs["elevation_deg"] == pytest.approx(1.490814, abs=1e-6)
    assert obs["solar_presence"] == "*"


def test_parse_real_faustini_earth_fixture():
    fixture = load_fixture("faustini-earth.json")
    observations, _, _ = parse_horizons_response(fixture["raw_response"])

    assert len(observations) == 1
    obs = observations[0]
    assert obs["timestamp"] == "2027-07-15T12:00:00Z"
    assert obs["azimuth_deg"] == pytest.approx(288.064862, abs=1e-6)
    assert obs["elevation_deg"] == pytest.approx(-4.947411, abs=1e-6)


def test_parse_real_farside_control_point_fixtures():
    sun_fixture = load_fixture("farside-sun.json")
    sun_obs, _, _ = parse_horizons_response(sun_fixture["raw_response"])
    assert sun_obs[0]["azimuth_deg"] == pytest.approx(219.515614, abs=1e-6)
    assert sun_obs[0]["elevation_deg"] == pytest.approx(-4.390937, abs=1e-6)

    earth_fixture = load_fixture("farside-earth.json")
    earth_obs, _, _ = parse_horizons_response(earth_fixture["raw_response"])
    assert earth_obs[0]["azimuth_deg"] == pytest.approx(184.908246, abs=1e-6)
    assert earth_obs[0]["elevation_deg"] == pytest.approx(-10.712201, abs=1e-6)


# --- 2. Errors Embedded in HTTP 200 ---


def test_detect_provider_error_bad_target():
    fixture = load_fixture("error-bad-target.json")
    with pytest.raises(HorizonsProviderError) as exc_info:
        parse_horizons_response(fixture["raw_response"])
    assert "no matches" in str(exc_info.value).lower()


def test_detect_provider_error_bad_dates():
    fixture = load_fixture("error-bad-dates.json")
    with pytest.raises(HorizonsProviderError) as exc_info:
        parse_horizons_response(fixture["raw_response"])
    assert "start must be earlier than stop" in str(exc_info.value).lower()


def test_detect_explicit_error_key_in_json():
    payload = {"error": "Cannot find central body matching 999999"}
    with pytest.raises(HorizonsProviderError, match="Cannot find central body"):
        parse_horizons_response(payload)


def test_detect_missing_soe_eoe_delimiters():
    payload = {"result": "Plain text with no ephemeris markers"}
    with pytest.raises(HorizonsParseError, match="Missing \\$\\$SOE / \\$\\$EOE"):
        parse_horizons_response(payload)


def test_detect_empty_ephemeris_block():
    payload = {"result": "header\n$$SOE\n\n$$EOE\nfooter"}
    with pytest.raises(HorizonsParseError, match="No observation rows found"):
        parse_horizons_response(payload)


# --- 3. Missing or Malformed Observation Data ---


def test_rejection_of_missing_na_data():
    row_with_na = " 2027-Jul-15 12:00:00, , , n.a.,    -1.088272,"
    with pytest.raises(HorizonsParseError, match="Observation data missing \\('n.a.'\\)"):
        parse_observation_row(row_with_na)


def test_rejection_of_non_numeric_azimuth_elevation():
    row = " 2027-Jul-15 12:00:00, , , INVALID_AZI,    -1.088272,"
    with pytest.raises(HorizonsParseError, match="Failed to parse numeric azimuth/elevation"):
        parse_observation_row(row)


def test_rejection_of_empty_observation_row():
    with pytest.raises(HorizonsParseError, match="Cannot parse empty observation row"):
        parse_observation_row("   ")


@pytest.mark.parametrize(
    "azimuth,elevation",
    [
        ("NaN", "0"),
        ("inf", "0"),
        ("-1", "0"),
        ("360", "0"),
        ("0", "NaN"),
        ("0", "inf"),
        ("0", "999"),
        ("0", "-91"),
    ],
)
def test_observation_parser_rejects_out_of_range_or_nonfinite_angles(azimuth, elevation):
    with pytest.raises(HorizonsParseError, match="(finite|in \\[)"):
        parse_observation_row(f"2027-Jul-15 12:00:00, , , {azimuth}, {elevation},")


# --- 4. Coordinate and Altitude Conversion ---


@pytest.mark.parametrize(
    ("input_lon", "expected_lon"),
    [
        (222.1, -137.9),
        (-137.9, -137.9),
        (77.0, 77.0),
        (180.0, -180.0),
        (-180.0, -180.0),
        (0.0, 0.0),
        (-0.0, 0.0),
        (360.0, 0.0),
        (-360.0, 0.0),
        (540.0, -180.0),
    ],
)
def test_normalize_longitude(input_lon: float, expected_lon: float):
    norm = normalize_longitude(input_lon)
    assert norm == pytest.approx(expected_lon, abs=1e-6)
    assert -180.0 <= norm < 180.0


def test_normalize_longitude_rejects_nonfinite():
    with pytest.raises(ValueError, match="finite"):
        normalize_longitude(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        normalize_longitude(float("inf"))


@pytest.mark.parametrize(
    ("meters", "expected_km"),
    [
        (0.0, 0.0),
        (2.0, 0.002),
        (20.0, 0.020),
        (1500.0, 1.5),
        (-50.0, -0.05),
    ],
)
def test_meters_to_km(meters: float, expected_km: float):
    assert meters_to_km(meters) == pytest.approx(expected_km, abs=1e-9)


def test_meters_to_km_rejects_nonfinite():
    with pytest.raises(ValueError, match="finite"):
        meters_to_km(float("nan"))


# --- 5. Parameter Construction ---


def test_build_horizons_params_sun():
    from datetime import datetime

    dt = datetime(2027, 7, 15, 12, 0, 0, tzinfo=UTC)
    params = build_horizons_params(
        target="Sun",
        latitude=-89.44,
        longitude=222.1,
        altitude_m=2.0,
        start_time=dt,
    )
    assert params["COMMAND"] == "'10'"
    assert params["CENTER"] == "'coord@301'"
    assert params["COORD_TYPE"] == "GEODETIC"
    assert params["SITE_COORD"] == "'222.1,-89.44,0.002000'"
    assert params["QUANTITIES"] == "'4'"
    assert params["CSV_FORMAT"] == "'YES'"
    assert params["TIME_DIGITS"] == "SECONDS"
    assert params["START_TIME"] == "'2027-07-15 12:00:00'"
    assert params["STOP_TIME"] == "'2027-07-15 12:01:00'"


def test_build_horizons_params_earth():
    from datetime import datetime

    dt = datetime(2027, 7, 15, 12, 0, 0, tzinfo=UTC)
    params = build_horizons_params(
        target="Earth",
        latitude=-89.44,
        longitude=-137.9,
        altitude_m=2.0,
        start_time=dt,
    )
    assert params["COMMAND"] == "'399'"
    assert params["CENTER"] == "'coord@301'"


# --- 6. Timeouts, Transport Failures and Bounded Retries ---


def test_provider_transport_error_on_connection_failure():
    def mock_handler(_request):
        raise httpx.ConnectError("Network unreachable")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    provider = HorizonsProvider(client=client, max_retries=1)

    with pytest.raises(HorizonsTransportError, match="HTTP transport failed"):
        provider.query_body(
            target="Sun",
            latitude=-89.44,
            longitude=222.1,
            target_time="2027-07-15T12:00:00Z",
        )


def test_provider_transport_error_on_timeout():
    def mock_handler(_request):
        raise httpx.ConnectTimeout("Connection timed out")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    provider = HorizonsProvider(client=client, max_retries=1)

    with pytest.raises(HorizonsTransportError, match="ConnectTimeout"):
        provider.query_body(
            target="Sun",
            latitude=-89.44,
            longitude=222.1,
            target_time="2027-07-15T12:00:00Z",
        )


def test_provider_http_non_200_error():
    def mock_handler(_request):
        return httpx.Response(500, text="Internal Server Error")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    provider = HorizonsProvider(client=client, max_retries=0)

    with pytest.raises(HorizonsHttpError) as exc_info:
        provider.query_body(
            target="Sun",
            latitude=-89.44,
            longitude=222.1,
            target_time="2027-07-15T12:00:00Z",
        )
    assert exc_info.value.status_code == 500


def test_provider_bounded_retries_on_503():
    attempts = 0

    def mock_handler(_request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, text="Service Unavailable")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    provider = HorizonsProvider(client=client, max_retries=2)

    with patch("time.sleep"):  # do not wait in test
        with pytest.raises(HorizonsHttpError) as exc_info:
            provider.query_body(
                target="Sun",
                latitude=-89.44,
                longitude=222.1,
                target_time="2027-07-15T12:00:00Z",
            )
    assert exc_info.value.status_code == 503
    # Initial attempt + 2 retries = 3 attempts total
    assert attempts == 3


def test_provider_successful_query_with_mock_fixture():
    fixture = load_fixture("shackleton-sun.json")

    def mock_handler(_request):
        return httpx.Response(200, json=fixture["raw_response"])

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    provider = HorizonsProvider(client=client)

    result = provider.query_body(
        target="Sun",
        latitude=-89.44,
        longitude=222.1,
        altitude_m=2.0,
        target_time="2027-07-15T12:00:00Z",
    )

    assert isinstance(result, EphemerisObservation)
    assert result.target == "Sun"
    assert result.timestamp == "2027-07-15T12:00:00Z"
    assert result.azimuth_deg == pytest.approx(177.278712, abs=1e-6)
    assert result.elevation_deg == pytest.approx(-1.088272, abs=1e-6)
    assert result.provider_name == "NASA/JPL Horizons API"
    assert result.ephemeris_source == "DE441"
    assert "COMMAND" in result.request_params


# --- 7. Live Control Scenario (Opt-In) ---


@pytest.mark.skipif(
    not os.getenv("TEST_LIVE_HORIZONS"),
    reason="Set TEST_LIVE_HORIZONS to run the explicit live network probe",
)
def test_live_control_scenario_shackleton_sun():
    provider = HorizonsProvider()
    result = provider.query_body(
        target="Sun",
        latitude=-89.44,
        longitude=222.1,
        altitude_m=2.0,
        target_time="2027-07-15T12:00:00Z",
    )

    assert result.target == "Sun"
    assert result.timestamp == "2027-07-15T12:00:00Z"
    # Live Horizons query must agree with Stage 0 verified fixture
    assert result.azimuth_deg == pytest.approx(177.278712, abs=1e-5)
    assert result.elevation_deg == pytest.approx(-1.088272, abs=1e-5)


def test_provider_preserves_unknown_ephemeris_version_as_null():
    body = {"result": "Synthetic parser fixture\n$$SOE\n2027-Jul-15 12:00:00, , , 0, 0,\n$$EOE"}
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    ) as client:
        observation = HorizonsProvider(client=client).query_body(
            target="Sun",
            latitude=0,
            longitude=0,
            target_time="2027-07-15T12:00:00Z",
        )
    assert observation.ephemeris_source is None
