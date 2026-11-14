"""JPL Horizons provider for lunar surface observations.

Queries the JPL Horizons API for topocentric apparent airless azimuth and
elevation of the Sun and Earth from a lunar surface observing site.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import get_settings

HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
TARGET_SUN = "10"
TARGET_EARTH = "399"
MOON_BODY_ID = "301"

TARGET_COMMAND_MAP = {
    "sun": TARGET_SUN,
    "10": TARGET_SUN,
    "earth": TARGET_EARTH,
    "399": TARGET_EARTH,
}


class HorizonsError(Exception):
    """Base exception for all JPL Horizons provider operations."""


class HorizonsTransportError(HorizonsError):
    """Network connection failure, DNS resolution failure, or timeout."""


class HorizonsHttpError(HorizonsError):
    """Horizons returned a non-200 HTTP status code."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class HorizonsProviderError(HorizonsError):
    """Provider-level failure returned inside a 200 response (e.g. unknown body, date error)."""


class HorizonsParseError(HorizonsError):
    """Horizons response is malformed, missing required delimiters, or contains unparseable data."""


@dataclass(frozen=True)
class EphemerisObservation:
    """Parsed observation record for a single body from Horizons."""

    target: str
    timestamp: str
    azimuth_deg: float
    elevation_deg: float
    solar_presence: str | None
    interfering_marker: str | None
    source_url: str
    retrieval_time: str
    provider_name: str
    ephemeris_source: str | None
    request_params: dict[str, str]


def normalize_longitude(longitude: float) -> float:
    """Normalize longitude in degrees to [-180, 180) per API v1 specification."""
    if not math.isfinite(longitude):
        raise ValueError("Longitude must be finite")
    normalized = ((longitude + 180.0) % 360.0) - 180.0
    if abs(normalized) < 1e-12:
        return 0.0
    rounded = round(normalized, 6)
    return -180.0 if rounded >= 180.0 else rounded


def meters_to_km(meters: float) -> float:
    """Convert altitude from internal metres to provider kilometres."""
    if not math.isfinite(meters):
        raise ValueError("Altitude must be finite")
    return meters / 1000.0


def parse_horizons_timestamp(ts_str: str) -> str:
    """Convert Horizons ephemeris timestamp to standard ISO 8601 UTC with 'Z'."""
    cleaned = ts_str.strip()
    parts = cleaned.split()
    if len(parts) != 2:
        raise HorizonsParseError(f"Unexpected date format in ephemeris row: '{cleaned}'")
    time_subparts = parts[1].split(":")
    if len(time_subparts) == 3:
        dt = datetime.strptime(cleaned, "%Y-%b-%d %H:%M:%S").replace(tzinfo=UTC)
    elif len(time_subparts) == 2:
        dt = datetime.strptime(cleaned, "%Y-%b-%d %H:%M").replace(tzinfo=UTC)
    else:
        raise HorizonsParseError(f"Unsupported time digits in timestamp: '{cleaned}'")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_observation_row(line: str) -> dict[str, Any]:
    """Parse a single ephemeris data row into fields.

    Rejects 'n.a.' values and non-finite / out-of-range angles.
    """
    cleaned = line.strip()
    if not cleaned:
        raise HorizonsParseError("Cannot parse empty observation row")

    if "," in cleaned:
        cols = [col.strip() for col in cleaned.split(",")]
        if len(cols) < 5:
            raise HorizonsParseError(
                f"CSV row has {len(cols)} columns, expected at least 5: '{cleaned}'"
            )
        dt_str = cols[0]
        solar_presence = cols[1]
        interfering_marker = cols[2]
        azi_str = cols[3]
        elev_str = cols[4]
    else:
        tokens = cleaned.split()
        if len(tokens) < 4:
            raise HorizonsParseError(
                f"Whitespace row has {len(tokens)} tokens, expected >= 4: '{cleaned}'"
            )
        dt_str = f"{tokens[0]} {tokens[1]}"
        flags = tokens[2:-2]
        solar_presence = flags[0] if flags else ""
        interfering_marker = flags[1] if len(flags) > 1 else ""
        azi_str = tokens[-2]
        elev_str = tokens[-1]

    if azi_str.lower() == "n.a." or elev_str.lower() == "n.a.":
        raise HorizonsParseError(f"Observation data missing ('n.a.') in row: '{cleaned}'")

    try:
        azimuth_deg = float(azi_str)
        elevation_deg = float(elev_str)
    except ValueError as exc:
        raise HorizonsParseError(
            f"Failed to parse numeric azimuth/elevation from row: '{cleaned}'"
        ) from exc

    if not math.isfinite(azimuth_deg) or not 0.0 <= azimuth_deg < 360.0:
        raise HorizonsParseError(f"Azimuth must be finite and in [0, 360), got: {azimuth_deg}")
    if not math.isfinite(elevation_deg) or not -90.0 <= elevation_deg <= 90.0:
        raise HorizonsParseError(f"Elevation must be finite and in [-90, 90], got: {elevation_deg}")

    timestamp_iso = parse_horizons_timestamp(dt_str)
    return {
        "timestamp": timestamp_iso,
        "azimuth_deg": azimuth_deg,
        "elevation_deg": elevation_deg,
        "solar_presence": solar_presence or None,
        "interfering_marker": interfering_marker or None,
    }


def parse_horizons_response(
    data: dict[str, Any] | str,
) -> tuple[list[dict[str, Any]], str, str | None]:
    """Parse raw Horizons JSON or text into observation rows and provenance metadata.

    Returns:
        (observations, provider_name, ephemeris_source)
    """
    provider_name = "NASA/JPL Horizons API"
    if isinstance(data, dict):
        if data.get("error"):
            raise HorizonsProviderError(str(data["error"]))
        if "result" not in data:
            raise HorizonsParseError("Missing 'result' text block in Horizons JSON response")
        text = str(data["result"])
        sig = data.get("signature")
        if isinstance(sig, dict) and sig.get("source"):
            provider_name = str(sig["source"])
    else:
        text = str(data)

    soe_marker = "$$SOE"
    eoe_marker = "$$EOE"
    soe_idx = text.find(soe_marker)
    eoe_idx = text.find(eoe_marker)

    if soe_idx == -1 or eoe_idx == -1 or eoe_idx <= soe_idx:
        error_lines = [
            line.strip()
            for line in text.splitlines()
            if any(err_word in line.lower() for err_word in ("error", "cannot find", "no matches"))
        ]
        if error_lines:
            raise HorizonsProviderError("; ".join(error_lines[:3]))
        raise HorizonsParseError("Missing $$SOE / $$EOE ephemeris delimiters in Horizons response")

    # Extract ephemeris source e.g. DE441 from header
    ephemeris_source: str | None = None
    source_match = re.search(r"\{source:\s*([^}]+)\}", text)
    if source_match:
        ephemeris_source = source_match.group(1).strip()

    ephem_block = text[soe_idx + len(soe_marker) : eoe_idx].strip()
    lines = [line.strip() for line in ephem_block.splitlines() if line.strip()]
    if not lines:
        raise HorizonsParseError("No observation rows found between $$SOE and $$EOE")

    observations = [parse_observation_row(line) for line in lines]
    return observations, provider_name, ephemeris_source


def build_horizons_params(
    *,
    target: str,
    latitude: float,
    longitude: float,
    altitude_m: float,
    start_time: datetime,
    stop_time: datetime | None = None,
    step_size: str = "2m",
    csv_format: bool = True,
) -> dict[str, str]:
    """Construct Horizons query parameters for topocentric lunar surface observer.

    Target center is used (COMMAND 10 for Sun, 399 for Earth).
    Apparent airless azimuth and elevation (QUANTITIES=4).
    """
    target_lower = target.lower().strip()
    target_cmd = TARGET_COMMAND_MAP.get(target_lower, target)

    alt_km = meters_to_km(altitude_m)
    site_coord_str = f"{longitude},{latitude},{alt_km:.6f}"

    dt_start = start_time.astimezone(UTC)
    dt_stop = (
        stop_time.astimezone(UTC) if stop_time is not None else dt_start + timedelta(minutes=1)
    )

    start_str = dt_start.strftime("%Y-%m-%d %H:%M:%S")
    stop_str = dt_stop.strftime("%Y-%m-%d %H:%M:%S")

    return {
        "format": "json",
        "COMMAND": f"'{target_cmd}'",
        "EPHEM_TYPE": "OBSERVER",
        "CENTER": f"'coord@{MOON_BODY_ID}'",
        "COORD_TYPE": "GEODETIC",
        "SITE_COORD": f"'{site_coord_str}'",
        "START_TIME": f"'{start_str}'",
        "STOP_TIME": f"'{stop_str}'",
        "STEP_SIZE": f"'{step_size}'",
        "QUANTITIES": "'4'",
        "TIME_DIGITS": "SECONDS",
        "CSV_FORMAT": "'YES'" if csv_format else "'NO'",
    }


class HorizonsProvider:
    """Production provider client for querying JPL Horizons ephemerides."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        try:
            settings = get_settings()
            default_base_url = settings.horizons_api_url
            default_timeout = settings.horizons_timeout_seconds
        except Exception:
            default_base_url = HORIZONS_API_URL
            default_timeout = 15.0

        self.base_url = base_url if base_url is not None else default_base_url
        self.timeout = timeout if timeout is not None else default_timeout
        self.max_retries = max_retries
        self._external_client = client

    def _execute_request(self, params: dict[str, str]) -> tuple[dict[str, Any], str, str]:
        """Execute HTTP GET with bounded retries for transient transport failures.

        Returns (body_json, source_url, retrieval_time_iso).
        """

        def _call(client: httpx.Client) -> tuple[dict[str, Any], str, str]:
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.get(self.base_url, params=params)
                    retrieval_time = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                    source_url = str(response.url)

                    # Bounded retry on transient HTTP gateway errors
                    if response.status_code in (502, 503, 504) and attempt < self.max_retries:
                        time.sleep(0.5 * (attempt + 1))
                        continue

                    if response.status_code != 200:
                        raise HorizonsHttpError(
                            f"Horizons returned HTTP status {response.status_code}",
                            status_code=response.status_code,
                        )

                    try:
                        body_json = response.json()
                    except Exception as exc:
                        raise HorizonsParseError("Horizons response is not valid JSON") from exc

                    return body_json, source_url, retrieval_time

                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as exc:
                    if attempt < self.max_retries:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    raise HorizonsTransportError(
                        f"HTTP transport failed: {type(exc).__name__}: {exc}"
                    ) from exc
                except httpx.RequestError as exc:
                    raise HorizonsTransportError(
                        f"HTTP transport failed: {type(exc).__name__}: {exc}"
                    ) from exc

            # Fallback if loop ended without return or raise
            raise HorizonsTransportError("Maximum retries exhausted connecting to Horizons")

        if self._external_client is not None:
            return _call(self._external_client)
        with httpx.Client(timeout=self.timeout) as client:
            return _call(client)

    def query_body(
        self,
        *,
        target: str,
        latitude: float,
        longitude: float,
        altitude_m: float = 2.0,
        target_time: datetime | str = "2027-07-15T12:00:00Z",
    ) -> EphemerisObservation:
        """Query topocentric apparent airless azimuth and elevation for Sun or Earth.

        Normalizes longitude and converts altitude to km.
        """
        norm_lon = normalize_longitude(longitude)
        if isinstance(target_time, str):
            dt = datetime.fromisoformat(target_time)
        else:
            dt = target_time

        if dt.tzinfo is None:
            raise ValueError("Target time must include an explicit timezone")
        dt_utc = dt.astimezone(UTC)

        params = build_horizons_params(
            target=target,
            latitude=latitude,
            longitude=norm_lon,
            altitude_m=altitude_m,
            start_time=dt_utc,
        )

        body_json, source_url, retrieval_time = self._execute_request(params)
        observations, provider_name, ephem_source = parse_horizons_response(body_json)

        first_obs = observations[0]
        if target.lower() in ("sun", "10"):
            canonical_target = "Sun"
        elif target.lower() in ("earth", "399"):
            canonical_target = "Earth"
        else:
            canonical_target = target

        return EphemerisObservation(
            target=canonical_target,
            timestamp=first_obs["timestamp"],
            azimuth_deg=first_obs["azimuth_deg"],
            elevation_deg=first_obs["elevation_deg"],
            solar_presence=first_obs["solar_presence"],
            interfering_marker=first_obs["interfering_marker"],
            source_url=source_url,
            retrieval_time=retrieval_time,
            provider_name=provider_name,
            ephemeris_source=ephem_source,
            request_params=params,
        )
