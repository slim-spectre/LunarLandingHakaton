"""Deterministic tests for JPL Horizons verification parser and reference fixtures.

Tests parser correctness, longitude normalization, unit conversion, error handling,
and rejection of malformed or incomplete responses without making live network calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tools.probe_horizons import (
    HorizonsHttpError,
    HorizonsParseError,
    HorizonsProviderError,
    HorizonsTransportError,
    build_horizons_params,
    meters_to_km,
    normalize_longitude,
    parse_horizons_response,
    parse_horizons_timestamp,
    parse_observation_row,
    query_horizons,
)

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "contracts" / "reference" / "horizons"


def load_fixture(filename: str) -> dict:
    fixture_path = FIXTURES_DIR / filename
    assert fixture_path.exists(), f"Fixture file not found: {fixture_path}"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


# --- 1. Parsing of Expected Fields from Real Fixtures ---


def test_parse_expected_fields_shackleton_sun():
    fixture = load_fixture("shackleton-sun.json")
    observations = parse_horizons_response(fixture["raw_response"])

    assert len(observations) == 1
    obs = observations[0]
    assert obs["timestamp"] == "2027-07-15T12:00:00Z"
    assert obs["azimuth_deg"] == pytest.approx(177.278712, abs=1e-6)
    assert obs["elevation_deg"] == pytest.approx(-1.088272, abs=1e-6)
    assert obs["solar_presence"] is None
    assert obs["interfering_marker"] is None


def test_parse_expected_fields_shackleton_earth():
    fixture = load_fixture("shackleton-earth.json")
    observations = parse_horizons_response(fixture["raw_response"])

    assert len(observations) == 1
    obs = observations[0]
    assert obs["timestamp"] == "2027-07-15T12:00:00Z"
    assert obs["azimuth_deg"] == pytest.approx(142.714718, abs=1e-6)
    assert obs["elevation_deg"] == pytest.approx(-6.178829, abs=1e-6)


def test_parse_solar_presence_flag_faustini_sun():
    fixture = load_fixture("faustini-sun.json")
    observations = parse_horizons_response(fixture["raw_response"])

    assert len(observations) == 1
    obs = observations[0]
    assert obs["timestamp"] == "2027-07-15T12:00:00Z"
    assert obs["azimuth_deg"] == pytest.approx(322.365998, abs=1e-6)
    assert obs["elevation_deg"] == pytest.approx(1.490814, abs=1e-6)
    # Faustini Rim A has the Sun above local horizon, marked by '*' in Horizons
    assert obs["solar_presence"] == "*"


def test_parse_farside_control_point():
    fixture = load_fixture("farside-earth.json")
    observations = parse_horizons_response(fixture["raw_response"])

    assert len(observations) == 1
    obs = observations[0]
    assert obs["timestamp"] == "2027-07-15T12:00:00Z"
    assert obs["azimuth_deg"] == pytest.approx(184.908246, abs=1e-6)
    assert obs["elevation_deg"] == pytest.approx(-10.712201, abs=1e-6)


# --- 2. Format Flexibility (CSV vs Whitespace-delimited) ---


def test_parse_whitespace_delimited_table_row():
    row_no_flag = " 2027-Jul-15 12:00:00     177.278712  -1.088272"
    parsed = parse_observation_row(row_no_flag)
    assert parsed["timestamp"] == "2027-07-15T12:00:00Z"
    assert parsed["azimuth_deg"] == pytest.approx(177.278712)
    assert parsed["elevation_deg"] == pytest.approx(-1.088272)
    assert parsed["solar_presence"] is None

    row_with_flag = " 2027-Jul-15 12:00:00 *   322.365998   1.490814"
    parsed_flag = parse_observation_row(row_with_flag)
    assert parsed_flag["timestamp"] == "2027-07-15T12:00:00Z"
    assert parsed_flag["azimuth_deg"] == pytest.approx(322.365998)
    assert parsed_flag["elevation_deg"] == pytest.approx(1.490814)
    assert parsed_flag["solar_presence"] == "*"


def test_parse_csv_delimited_table_row():
    csv_row = " 2027-Jul-15 12:00:00,*,i, 322.365998,     1.490814,"
    parsed = parse_observation_row(csv_row)
    assert parsed["timestamp"] == "2027-07-15T12:00:00Z"
    assert parsed["azimuth_deg"] == pytest.approx(322.365998)
    assert parsed["elevation_deg"] == pytest.approx(1.490814)
    assert parsed["solar_presence"] == "*"
    assert parsed["interfering_marker"] == "i"


# --- 3. Longitude Normalization Tests ---


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
def test_longitude_normalization(input_lon: float, expected_lon: float):
    normalized = normalize_longitude(input_lon)
    assert normalized == pytest.approx(expected_lon, abs=1e-6)
    assert -180.0 <= normalized < 180.0


# --- 4. Altitude Unit Conversion Tests ---


@pytest.mark.parametrize(
    ("meters", "expected_km"),
    [
        (0.0, 0.0),
        (2.0, 0.002),
        (20.0, 0.02),
        (1500.0, 1.5),
        (-50.0, -0.05),
    ],
)
def test_meters_to_km(meters: float, expected_km: float):
    assert meters_to_km(meters) == pytest.approx(expected_km)


# --- 5. Timezone & Timestamp Handling Tests ---


def test_parse_horizons_timestamp():
    assert parse_horizons_timestamp("2027-Jul-15 12:00:00") == "2027-07-15T12:00:00Z"
    assert parse_horizons_timestamp("2027-Jul-15 12:00") == "2027-07-15T12:00:00Z"
    assert parse_horizons_timestamp(" 2027-Jan-01 00:00:00 ") == "2027-01-01T00:00:00Z"


def test_parse_horizons_timestamp_invalid():
    with pytest.raises(HorizonsParseError, match="Unexpected date format"):
        parse_horizons_timestamp("invalid-date")

    with pytest.raises(HorizonsParseError, match="Unsupported time digits"):
        parse_horizons_timestamp("2027-Jul-15 12:00:00:00:00")


# --- 6. Provider Error Handling Tests ---


def test_provider_error_bad_target():
    fixture = load_fixture("error-bad-target.json")
    with pytest.raises(HorizonsProviderError) as exc_info:
        parse_horizons_response(fixture["raw_response"])
    assert "no matches" in str(exc_info.value).lower()


def test_provider_error_bad_dates():
    fixture = load_fixture("error-bad-dates.json")
    with pytest.raises(HorizonsProviderError) as exc_info:
        parse_horizons_response(fixture["raw_response"])
    assert "start must be earlier than stop" in str(exc_info.value).lower()


def test_provider_error_explicit_error_key():
    payload = {"error": "Cannot find central body matching 999999"}
    with pytest.raises(HorizonsProviderError, match="Cannot find central body"):
        parse_horizons_response(payload)


# --- 7. Rejection of Malformed / Incomplete Responses ---


def test_rejection_missing_result():
    with pytest.raises(HorizonsParseError, match="Missing 'result' text block"):
        parse_horizons_response({"signature": "test"})


def test_rejection_missing_delimiters():
    payload = {"result": "Plain text with no ephemeris markers"}
    with pytest.raises(HorizonsParseError, match="Missing \\$\\$SOE / \\$\\$EOE"):
        parse_horizons_response(payload)


def test_rejection_empty_ephemeris_block():
    payload = {"result": "header\n$$SOE\n\n$$EOE\nfooter"}
    with pytest.raises(HorizonsParseError, match="No observation rows found"):
        parse_horizons_response(payload)


def test_rejection_of_missing_or_na_data():
    row_with_na = " 2027-Jul-15 12:00:00, , , n.a.,    -1.088272,"
    with pytest.raises(HorizonsParseError, match="Observation data missing \\('n.a.'\\)"):
        parse_observation_row(row_with_na)


def test_rejection_of_non_numeric_values():
    row_with_text = " 2027-Jul-15 12:00:00, , , NOT_A_FLOAT,    -1.088272,"
    with pytest.raises(HorizonsParseError, match="Failed to parse numeric azimuth/elevation"):
        parse_observation_row(row_with_text)


def test_rejection_empty_row():
    with pytest.raises(HorizonsParseError, match="Cannot parse empty observation row"):
        parse_observation_row("   ")


# --- 8. Parameter Construction & Transport Error Handling ---


def test_build_horizons_params():
    params = build_horizons_params(
        target="Sun",
        latitude=-89.44,
        longitude=222.1,
        altitude_m=2.0,
        start_time="2027-07-15T12:00:00Z",
        csv_format=True,
    )
    assert params["COMMAND"] == "'10'"
    assert params["CENTER"] == "'coord@301'"
    assert params["COORD_TYPE"] == "GEODETIC"
    assert params["SITE_COORD"] == "'222.1,-89.44,0.002000'"
    assert params["QUANTITIES"] == "'4'"
    assert params["CSV_FORMAT"] == "'YES'"


def test_transport_error_handling():
    def mock_handler(_request):
        raise httpx.ConnectError("Connection refused by provider")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    with pytest.raises(HorizonsTransportError, match="HTTP transport failed"):
        query_horizons(
            target="Sun",
            latitude=-89.44,
            longitude=222.1,
            client=client,
        )


def test_http_non_200_error_handling():
    def mock_handler(_request):
        return httpx.Response(503, text="Service Unavailable")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    with pytest.raises(HorizonsHttpError, match="HTTP status 503"):
        query_horizons(
            target="Sun",
            latitude=-89.44,
            longitude=222.1,
            client=client,
        )
