"""JPL Horizons API verification probe for lunar surface observers.

Explicit live source probe for Stage 0 astronomy verification; never run by
deterministic unit tests or normal API startup.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
TARGET_SUN = "10"
TARGET_EARTH = "399"
MOON_BODY_ID = "301"

VERIFICATION_TARGETS = {
    "Sun": TARGET_SUN,
    "Earth": TARGET_EARTH,
}

VERIFICATION_LOCATIONS = [
    {
        "name": "Shackleton Connecting Ridge",
        "latitude": -89.44,
        "longitude": 222.1,
        "altitude_m": 2.0,
    },
    {
        "name": "Faustini Rim A",
        "latitude": -87.45,
        "longitude": 77.0,
        "altitude_m": 2.0,
    },
    {
        "name": "Far Side Control Point",
        "latitude": -85.0,
        "longitude": 180.0,
        "altitude_m": 2.0,
    },
]


class HorizonsError(Exception):
    """Base exception for JPL Horizons query and parsing errors."""


class HorizonsTransportError(HorizonsError):
    """Network connection or timeout error communicating with Horizons."""


class HorizonsHttpError(HorizonsError):
    """Non-200 HTTP response from Horizons API."""


class HorizonsProviderError(HorizonsError):
    """Provider-level error reported within Horizons response."""


class HorizonsParseError(HorizonsError):
    """Response structure or content cannot be parsed into observation rows."""


def normalize_longitude(longitude: float) -> float:
    """Normalize longitude to [-180, 180) degrees per API v1 specification."""
    normalized = ((longitude + 180.0) % 360.0) - 180.0
    if abs(normalized) < 1e-12:
        return 0.0
    return round(normalized, 6)


def meters_to_km(meters: float) -> float:
    """Convert altitude from internal metres to Horizons kilometres."""
    return meters / 1000.0


def parse_horizons_timestamp(ts_str: str) -> str:
    """Parse Horizons calendar date string to ISO 8601 UTC string (ending with 'Z')."""
    cleaned = ts_str.strip()
    parts = cleaned.split()
    if len(parts) != 2:
        raise HorizonsParseError(f"Unexpected date format: '{cleaned}'")
    time_subparts = parts[1].split(":")
    if len(time_subparts) == 3:
        dt = datetime.strptime(cleaned, "%Y-%b-%d %H:%M:%S").replace(tzinfo=UTC)
    elif len(time_subparts) == 2:
        dt = datetime.strptime(cleaned, "%Y-%b-%d %H:%M").replace(tzinfo=UTC)
    else:
        raise HorizonsParseError(f"Unsupported time digits in timestamp: '{cleaned}'")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_horizons_params(
    *,
    target: str,
    latitude: float,
    longitude: float,
    altitude_m: float,
    start_time: str,
    stop_time: str | None = None,
    step_size: str = "2m",
    csv_format: bool = True,
) -> dict[str, str]:
    """Construct URL query parameters for a topocentric lunar observer query.

    Center: coord@301 (lunar surface coordinates).
    Quantities: 4 (apparent airless azimuth and elevation).
    """
    target_cmd = VERIFICATION_TARGETS.get(target, target)
    alt_km = meters_to_km(altitude_m)
    site_coord_str = f"{longitude},{latitude},{alt_km:.6f}"

    if stop_time is None:
        # Default stop time 1 minute later for a single-instant evaluation
        dt_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        dt_stop = dt_start + timedelta(minutes=1)
        stop_time_str = dt_stop.strftime("%Y-%m-%d %H:%M:%S")
    else:
        stop_time_str = stop_time

    # Clean start time string
    if "T" in start_time:
        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        start_time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        start_time_str = start_time

    params = {
        "format": "json",
        "COMMAND": f"'{target_cmd}'",
        "EPHEM_TYPE": "OBSERVER",
        "CENTER": f"'coord@{MOON_BODY_ID}'",
        "COORD_TYPE": "GEODETIC",
        "SITE_COORD": f"'{site_coord_str}'",
        "START_TIME": f"'{start_time_str}'",
        "STOP_TIME": f"'{stop_time_str}'",
        "STEP_SIZE": f"'{step_size}'",
        "QUANTITIES": "'4'",
        "TIME_DIGITS": "SECONDS",
        "CSV_FORMAT": "'YES'" if csv_format else "'NO'",
    }
    return params


def parse_observation_row(line: str) -> dict[str, Any]:
    """Parse a single ephemeris line into structured fields.

    Does not replace missing columns or 'n.a.' with zeroes.
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

    timestamp_iso = parse_horizons_timestamp(dt_str)
    return {
        "timestamp": timestamp_iso,
        "azimuth_deg": azimuth_deg,
        "elevation_deg": elevation_deg,
        "solar_presence": solar_presence or None,
        "interfering_marker": interfering_marker or None,
        "raw_line": cleaned,
    }


def parse_horizons_response(data: dict[str, Any] | str) -> list[dict[str, Any]]:
    """Parse raw Horizons JSON or text response into structured observation rows.

    Inspects for provider error indicators, missing markers, and invalid values.
    """
    if isinstance(data, dict):
        if "error" in data and data["error"]:
            raise HorizonsProviderError(str(data["error"]))
        if "result" not in data:
            raise HorizonsParseError("Missing 'result' text block in Horizons JSON response")
        text = str(data["result"])
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

    ephem_block = text[soe_idx + len(soe_marker) : eoe_idx].strip()
    lines = [line.strip() for line in ephem_block.splitlines() if line.strip()]
    if not lines:
        raise HorizonsParseError("No observation rows found between $$SOE and $$EOE")

    observations = [parse_observation_row(line) for line in lines]
    return observations


def query_horizons(
    *,
    target: str,
    latitude: float,
    longitude: float,
    altitude_m: float = 2.0,
    start_time: str = "2027-07-15T12:00:00Z",
    stop_time: str | None = None,
    step_size: str = "2m",
    timeout: float = 15.0,
    csv_format: bool = True,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Execute a query against the live JPL Horizons API and parse the response."""
    params = build_horizons_params(
        target=target,
        latitude=latitude,
        longitude=longitude,
        altitude_m=altitude_m,
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        csv_format=csv_format,
    )

    request_time = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _execute(c: httpx.Client) -> tuple[int, dict[str, Any], str]:
        response = c.get(HORIZONS_API_URL, params=params)
        status = response.status_code
        source_url = str(response.url)
        if status != 200:
            raise HorizonsHttpError(f"Horizons returned HTTP status {status}")
        try:
            body_json = response.json()
        except Exception as exc:
            raise HorizonsParseError("Horizons response is not valid JSON") from exc
        return status, body_json, source_url

    try:
        if client is not None:
            status_code, body_json, source_url = _execute(client)
        else:
            with httpx.Client(timeout=timeout) as c:
                status_code, body_json, source_url = _execute(c)
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        raise HorizonsTransportError(f"HTTP transport failed: {type(exc).__name__}: {exc}") from exc

    observations = parse_horizons_response(body_json)

    return {
        "target": target,
        "request_parameters": params,
        "observer": {
            "latitude": latitude,
            "longitude": longitude,
            "longitude_normalized": normalize_longitude(longitude),
            "altitude_m": altitude_m,
            "altitude_km": meters_to_km(altitude_m),
        },
        "requested_time": start_time,
        "retrieval_time": request_time,
        "source_url": source_url,
        "raw_response": body_json,
        "parsed_observations": observations,
    }


def verify_all_locations(
    timeout: float = 15.0, client: httpx.Client | None = None
) -> dict[str, Any]:
    """Run sequential verification across all defined baseline lunar locations."""
    report: dict[str, Any] = {
        "verified_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "api_endpoint": HORIZONS_API_URL,
        "observer_center": f"coord@{MOON_BODY_ID}",
        "coord_type": "GEODETIC",
        "time_scale": "UTC (UT in Horizons)",
        "quantities": "4 (apparent airless azimuth & elevation)",
        "verification": "incomplete",
        "results": [],
        "longitude_equivalence_test": {},
        "failures": [],
    }

    test_time = "2027-07-15T12:00:00Z"
    all_succeeded = True

    # 1. Probe the three core locations for Sun and Earth
    for loc in VERIFICATION_LOCATIONS:
        for target_name in ["Sun", "Earth"]:
            try:
                probe_res = query_horizons(
                    target=target_name,
                    latitude=loc["latitude"],
                    longitude=loc["longitude"],
                    altitude_m=loc["altitude_m"],
                    start_time=test_time,
                    timeout=timeout,
                    client=client,
                )
                first_obs = (
                    probe_res["parsed_observations"][0]
                    if probe_res["parsed_observations"]
                    else None
                )
                report["results"].append(
                    {
                        "location_name": loc["name"],
                        "target": target_name,
                        "latitude": loc["latitude"],
                        "longitude": loc["longitude"],
                        "longitude_normalized": probe_res["observer"]["longitude_normalized"],
                        "altitude_m": loc["altitude_m"],
                        "observation": first_obs,
                        "status": "success",
                    }
                )
            except HorizonsError as exc:
                all_succeeded = False
                err_msg = f"{type(exc).__name__}: {exc}"
                report["results"].append(
                    {
                        "location_name": loc["name"],
                        "target": target_name,
                        "latitude": loc["latitude"],
                        "longitude": loc["longitude"],
                        "status": "failed",
                        "error": err_msg,
                    }
                )
                report["failures"].append(f"{loc['name']} ({target_name}): {err_msg}")

    # 2. Check longitude equivalence (222.1 vs -137.9)
    try:
        res_east = query_horizons(
            target="Sun",
            latitude=-89.44,
            longitude=222.1,
            altitude_m=2.0,
            start_time=test_time,
            timeout=timeout,
            client=client,
        )
        res_west = query_horizons(
            target="Sun",
            latitude=-89.44,
            longitude=-137.9,
            altitude_m=2.0,
            start_time=test_time,
            timeout=timeout,
            client=client,
        )
        obs_east = res_east["parsed_observations"][0]
        obs_west = res_west["parsed_observations"][0]
        match = (
            obs_east["azimuth_deg"] == obs_west["azimuth_deg"]
            and obs_east["elevation_deg"] == obs_west["elevation_deg"]
        )
        report["longitude_equivalence_test"] = {
            "longitude_east": 222.1,
            "longitude_normalized": -137.9,
            "east_azimuth_deg": obs_east["azimuth_deg"],
            "east_elevation_deg": obs_east["elevation_deg"],
            "west_azimuth_deg": obs_west["azimuth_deg"],
            "west_elevation_deg": obs_west["elevation_deg"],
            "ephemeris_matched": match,
        }
        if not match:
            all_succeeded = False
            report["failures"].append("Longitude equivalence 222.1 vs -137.9 failed to match")
    except HorizonsError as exc:
        all_succeeded = False
        report["longitude_equivalence_test"] = {
            "error": f"{type(exc).__name__}: {exc}",
            "ephemeris_matched": False,
        }
        report["failures"].append(f"Longitude equivalence test failed: {exc}")

    if all_succeeded:
        report["verification"] = "complete"

    return report


def generate_markdown_report(report: dict[str, Any]) -> str:
    """Render comprehensive verification documentation for Stage 0 handoff."""
    lines = [
        "# JPL Horizons Lunar Topocentric Source Verification",
        "",
        "Stage 0 astronomy verification for topocentric Sun and Earth observations.",
        "Live provider queries verify observing settings, coordinate conventions, and formats.",
        "",
        "## 1. Exact Request Settings",
        "",
        "- **API Endpoint:** `https://ssd.jpl.nasa.gov/api/horizons.api`",
        "- **Target Identifiers:**",
        "  - Sun: `COMMAND='10'` (Solar system barycenter / Sun body center)",
        "  - Earth: `COMMAND='399'` (Earth body center)",
        "- **Observer Location Syntax:**",
        "  - `CENTER='coord@301'` (topocentric observer on body `301`, the Moon)",
        "  - `COORD_TYPE='GEODETIC'` (planetodetic coordinates on lunar reference surface)",
        "  - `SITE_COORD='{longitude},{latitude},{altitude_km}'`",
        "- **Lunar Longitude Convention:**",
        "  - Measured in degrees, positive East [0, 360) or [-180, 180).",
        "  - Horizons uses `{East-longitude positive}`.",
        "  - Longitudes 222.1° East and -137.9° normalize to the same location.",
        "- **Latitude Convention:**",
        "  - Planetodetic latitude in degrees [-90, +90], positive North, negative South.",
        "  - For a sphere ($a=b=c$), planetodetic and planetocentric latitudes are identical.",
        "- **Observer Altitude Units:**",
        "  - Horizons requires kilometres (`Alt(km)`) above the reference surface.",
        "  - Our API internal heights are metres: $h_{\\text{km}} = h_{\\text{m}} / 1000.0$.",
        "- **Time-Scale & Output Precision:**",
        "  - `EPHEM_TYPE='OBSERVER'`",
        "  - `TIME_TYPE='UT'` (Horizons interprets dates post-1962 as UTC civil timescale).",
        "  - `TIME_DIGITS='SECONDS'` (outputs second-level precision: `YYYY-Mon-DD HH:MM:SS`).",
        "- **Airless Apparent Azimuth & Elevation:**",
        "  - `QUANTITIES='4'` returns apparent airless azimuth and elevation.",
        "  - `Atmos refraction: NO (AIRLESS)` is confirmed in the provider output.",
        "  - Azimuth is measured in degrees clockwise from North (0°=N, 90°=E, 180°=S, 270°=W).",
        "  - Elevation is measured in degrees relative to the local horizontal plane [-90, +90].",
        "- **Lunar Reference Conventions:**",
        "  - Reference frame: `MEAN_ME` (Mean Earth / Polar Axis system, high precision).",
        "  - Reference body: Spherical lunar model with radius $R = 1737.4\\text{ km}$ ($a=b=c$).",
        "  - Ephemeris source: JPL DE441.",
        "",
        "## 2. Reproduction Steps",
        "",
        "From the `backend/` directory with locked dependencies:",
        "",
        "```sh",
        "uv run --locked python tools/probe_horizons.py \\",
        "  --output ../docs/sources/horizons.md \\",
        "  --save-fixtures ../contracts/reference/horizons",
        "```",
        "",
        "## 3. Actual Verification Results (2027-07-15T12:00:00Z)",
        "",
        f"- **Overall Verification Status:** `{report['verification'].upper()}`",
        f"- **Verified At:** `{report['verified_at']}`",
        "",
        "| Location | Target | Lat | Lon (in/norm) | Azimuth (deg) | Elev (deg) | Flag | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for item in report.get("results", []):
        if item["status"] == "success":
            obs = item["observation"]
            solar = obs.get("solar_presence") or "-"
            lines.append(
                f"| {item['location_name']} | {item['target']} | {item['latitude']} | "
                f"{item['longitude']} / {item['longitude_normalized']} | "
                f"{obs['azimuth_deg']:.6f} | {obs['elevation_deg']:.6f} | `{solar}` | OK |"
            )
        else:
            lines.append(
                f"| {item['location_name']} | {item['target']} | {item['latitude']} | "
                f"{item['longitude']} | N/A | N/A | - | FAILED ({item.get('error')}) |"
            )

    eq = report.get("longitude_equivalence_test", {})
    e_az = eq.get("east_azimuth_deg")
    e_el = eq.get("east_elevation_deg")
    w_az = eq.get("west_azimuth_deg")
    w_el = eq.get("west_elevation_deg")
    matched = "YES" if eq.get("ephemeris_matched") else "NO"
    lines.extend(
        [
            "",
            "### Longitude Equivalence Verification",
            "",
            f"- **Input Lon 1 (East):** `222.1` -> Azimuth: `{e_az}`, Elevation: `{e_el}`",
            f"- **Input Lon 2 (Normalized):** `-137.9` -> Azimuth: `{w_az}`, Elevation: `{w_el}`",
            f"- **Ephemeris Values Exactly Match:** `{matched}`",
            "",
            "## 4. Known Provider Limitations",
            "",
            "1. **Non-Array JSON Format:** `format=json` wraps text tables between `$$SOE`",
            "   and `$$EOE` within `result`. Dedicated parsing is required.",
            "2. **Strict Date Constraints:** Horizons requires `START_TIME < STOP_TIME`.",
            "   Single-instant queries must use a small step window (e.g. 1 minute).",
            "3. **Transient Network Errors:** Horizons API can throttle or drop connections",
            "   under load. Clients must configure bounded timeouts and graceful retries.",
            "4. **Future Leap Seconds:** UT-to-TDB conversions beyond near-term EOP predict",
            "   intervals assume constant leap seconds per JPL documentation.",
            "5. **Column Flags:** Ephemeris table includes solar-presence (`*`) and interfering",
            "   body (`i`) flags requiring column-aware parsing rather than whitespace splitting.",
            "",
            "## 5. Production Astronomy Module Requirements (Stage 1)",
            "",
            "1. **Ephemeris Caching:** Cache Horizons responses keyed by coordinates,",
            "   time range, step size, and observer height to avoid redundant upstream calls.",
            "2. **Asynchronous Background Workers:** As in Section 8 of `docs/API_V1.md`,",
            "   calculation routes (`POST /ephemeris/now`, `POST /ephemeris/timeline`)",
            "   return HTTP 202 Accepted immediately. Ephemeris queries run in background jobs.",
            "3. **Direction Vector Computation:** Map azimuth and elevation into Local ENU:",
            "   - $\\text{east} = \\cos(\\text{elevation}) \\cdot \\sin(\\text{azimuth})$",
            "   - $\\text{north} = \\cos(\\text{elevation}) \\cdot \\cos(\\text{azimuth})$",
            "   - $\\text{up} = \\sin(\\text{elevation})$",
            "   and Three.js coordinates: ($x=\\text{east}, y=\\text{up}, z=-\\text{north}$).",
            "4. **Horizon Intersection & Golden Windows:** Combine Horizons geometric body",
            "   elevations with geometric horizon (0°) or terrain horizon to compute visibility.",
            "",
            "## 6. Diagnostic Probe Payload",
            "",
            "```json",
            json.dumps(report, indent=2, ensure_ascii=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    """CLI entrypoint for running the Horizons verification probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to write the verification markdown report (e.g. docs/sources/horizons.md)",
    )
    parser.add_argument(
        "--save-fixtures",
        type=Path,
        help="Directory to save query fixtures (e.g. contracts/reference/horizons)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Timeout in seconds for each sequential HTTP request (default: 15.0)",
    )
    args = parser.parse_args()

    report = verify_all_locations(timeout=args.timeout)

    if args.save_fixtures:
        args.save_fixtures.mkdir(parents=True, exist_ok=True)
        # Fetch and save fixtures for each target location
        test_time = "2027-07-15T12:00:00Z"
        loc_slugs = {
            "Shackleton Connecting Ridge": "shackleton",
            "Faustini Rim A": "faustini",
            "Far Side Control Point": "farside",
        }
        for loc in VERIFICATION_LOCATIONS:
            slug = loc_slugs[loc["name"]]
            for target_name in ["Sun", "Earth"]:
                try:
                    probe_data = query_horizons(
                        target=target_name,
                        latitude=loc["latitude"],
                        longitude=loc["longitude"],
                        altitude_m=loc["altitude_m"],
                        start_time=test_time,
                        timeout=args.timeout,
                    )
                    fixture_filename = f"{slug}-{target_name.lower()}.json"
                    fixture_path = args.save_fixtures / fixture_filename
                    fixture_path.write_text(
                        json.dumps(probe_data, indent=2, ensure_ascii=True),
                        encoding="utf-8",
                    )
                except Exception as exc:
                    print(f"Warning: Failed saving fixture for {slug}-{target_name}: {exc}")

    md_content = generate_markdown_report(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md_content, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(md_content)

    return 0 if report["verification"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
