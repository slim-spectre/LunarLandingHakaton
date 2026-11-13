# JPL Horizons Lunar Topocentric Source Verification

Stage 0 astronomy verification for topocentric Sun and Earth observations.
Live provider queries verify observing settings, coordinate conventions, and formats.

## 1. Exact Request Settings

- **API Endpoint:** `https://ssd.jpl.nasa.gov/api/horizons.api`
- **Target Identifiers:**
  - Sun: `COMMAND='10'` (Solar system barycenter / Sun body center)
  - Earth: `COMMAND='399'` (Earth body center)
- **Observer Location Syntax:**
  - `CENTER='coord@301'` (topocentric observer on body `301`, the Moon)
  - `COORD_TYPE='GEODETIC'` (planetodetic coordinates on lunar reference surface)
  - `SITE_COORD='{longitude},{latitude},{altitude_km}'`
- **Lunar Longitude Convention:**
  - Measured in degrees, positive East [0, 360) or [-180, 180).
  - Horizons uses `{East-longitude positive}`.
  - Longitudes 222.1° East and -137.9° normalize to the same location.
- **Latitude Convention:**
  - Planetodetic latitude in degrees [-90, +90], positive North, negative South.
  - For a sphere ($a=b=c$), planetodetic and planetocentric latitudes are identical.
- **Observer Altitude Units:**
  - Horizons requires kilometres (`Alt(km)`) above the reference surface.
  - Our API internal heights are metres: $h_{\text{km}} = h_{\text{m}} / 1000.0$.
- **Time-Scale & Output Precision:**
  - `EPHEM_TYPE='OBSERVER'`
  - `TIME_TYPE='UT'` (Horizons interprets dates post-1962 as UTC civil timescale).
  - `TIME_DIGITS='SECONDS'` (outputs second-level precision: `YYYY-Mon-DD HH:MM:SS`).
- **Airless Apparent Azimuth & Elevation:**
  - `QUANTITIES='4'` returns apparent airless azimuth and elevation.
  - `Atmos refraction: NO (AIRLESS)` is confirmed in the provider output.
  - Azimuth is measured in degrees clockwise from North (0°=N, 90°=E, 180°=S, 270°=W).
  - Elevation is measured in degrees relative to the local horizontal plane [-90, +90].
- **Lunar Reference Conventions:**
  - Reference frame: `MEAN_ME` (Mean Earth / Polar Axis system, high precision).
  - Reference body: Spherical lunar model with radius $R = 1737.4\text{ km}$ ($a=b=c$).
  - Ephemeris source: JPL DE441.

## 2. Reproduction Steps

From the `backend/` directory with locked dependencies:

```sh
uv run --locked python tools/probe_horizons.py \
  --output ../docs/sources/horizons.md \
  --save-fixtures ../contracts/reference/horizons
```

## 3. Actual Verification Results (2027-07-15T12:00:00Z)

- **Overall Verification Status:** `COMPLETE`
- **Verified At:** `2026-11-13T21:14:02Z`

| Location | Target | Lat | Lon (in/norm) | Azimuth (deg) | Elev (deg) | Flag | Status |
|---|---|---|---|---|---|---|---|
| Shackleton Connecting Ridge | Sun | -89.44 | 222.1 / -137.9 | 177.278712 | -1.088272 | `-` | OK |
| Shackleton Connecting Ridge | Earth | -89.44 | 222.1 / -137.9 | 142.714718 | -6.178829 | `-` | OK |
| Faustini Rim A | Sun | -87.45 | 77.0 / 77.0 | 322.365998 | 1.490814 | `*` | OK |
| Faustini Rim A | Earth | -87.45 | 77.0 / 77.0 | 288.064862 | -4.947411 | `*` | OK |
| Far Side Control Point | Sun | -85.0 | 180.0 / -180.0 | 219.515614 | -4.390937 | `-` | OK |
| Far Side Control Point | Earth | -85.0 | 180.0 / -180.0 | 184.908246 | -10.712201 | `-` | OK |

### Longitude Equivalence Verification

- **Input Lon 1 (East):** `222.1` -> Azimuth: `177.278712`, Elevation: `-1.088272`
- **Input Lon 2 (Normalized):** `-137.9` -> Azimuth: `177.278712`, Elevation: `-1.088272`
- **Ephemeris Values Exactly Match:** `YES`

## 4. Known Provider Limitations

1. **Non-Array JSON Format:** `format=json` wraps text tables between `$$SOE`
   and `$$EOE` within `result`. Dedicated parsing is required.
2. **Strict Date Constraints:** Horizons requires `START_TIME < STOP_TIME`.
   Single-instant queries must use a small step window (e.g. 1 minute).
3. **Transient Network Errors:** Horizons API can throttle or drop connections
   under load. Clients must configure bounded timeouts and graceful retries.
4. **Future Leap Seconds:** UT-to-TDB conversions beyond near-term EOP predict
   intervals assume constant leap seconds per JPL documentation.
5. **Column Flags:** Ephemeris table includes solar-presence (`*`) and interfering
   body (`i`) flags requiring column-aware parsing rather than whitespace splitting.

## 5. Production Astronomy Module Requirements (Stage 1)

1. **Ephemeris Caching:** Cache Horizons responses keyed by coordinates,
   time range, step size, and observer height to avoid redundant upstream calls.
2. **Asynchronous Background Workers:** As in Section 8 of `docs/API_V1.md`,
   calculation routes (`POST /ephemeris/now`, `POST /ephemeris/timeline`)
   return HTTP 202 Accepted immediately. Ephemeris queries run in background jobs.
3. **Direction Vector Computation:** Map azimuth and elevation into Local ENU:
   - $\text{east} = \cos(\text{elevation}) \cdot \sin(\text{azimuth})$
   - $\text{north} = \cos(\text{elevation}) \cdot \cos(\text{azimuth})$
   - $\text{up} = \sin(\text{elevation})$
   and Three.js coordinates: ($x=\text{east}, y=\text{up}, z=-\text{north}$).
4. **Horizon Intersection & Golden Windows:** Combine Horizons geometric body
   elevations with geometric horizon (0°) or terrain horizon to compute visibility.

## 6. Diagnostic Probe Payload

```json
{
  "verified_at": "2026-11-13T21:14:02Z",
  "api_endpoint": "https://ssd.jpl.nasa.gov/api/horizons.api",
  "observer_center": "coord@301",
  "coord_type": "GEODETIC",
  "time_scale": "UTC (UT in Horizons)",
  "quantities": "4 (apparent airless azimuth & elevation)",
  "verification": "complete",
  "results": [
    {
      "location_name": "Shackleton Connecting Ridge",
      "target": "Sun",
      "latitude": -89.44,
      "longitude": 222.1,
      "longitude_normalized": -137.9,
      "altitude_m": 2.0,
      "observation": {
        "timestamp": "2027-07-15T12:00:00Z",
        "azimuth_deg": 177.278712,
        "elevation_deg": -1.088272,
        "solar_presence": null,
        "interfering_marker": null,
        "raw_line": "2027-Jul-15 12:00:00, , , 177.278712,    -1.088272,"
      },
      "status": "success"
    },
    {
      "location_name": "Shackleton Connecting Ridge",
      "target": "Earth",
      "latitude": -89.44,
      "longitude": 222.1,
      "longitude_normalized": -137.9,
      "altitude_m": 2.0,
      "observation": {
        "timestamp": "2027-07-15T12:00:00Z",
        "azimuth_deg": 142.714718,
        "elevation_deg": -6.178829,
        "solar_presence": null,
        "interfering_marker": null,
        "raw_line": "2027-Jul-15 12:00:00, , , 142.714718,    -6.178829,"
      },
      "status": "success"
    },
    {
      "location_name": "Faustini Rim A",
      "target": "Sun",
      "latitude": -87.45,
      "longitude": 77.0,
      "longitude_normalized": 77.0,
      "altitude_m": 2.0,
      "observation": {
        "timestamp": "2027-07-15T12:00:00Z",
        "azimuth_deg": 322.365998,
        "elevation_deg": 1.490814,
        "solar_presence": "*",
        "interfering_marker": null,
        "raw_line": "2027-Jul-15 12:00:00,*, , 322.365998,     1.490814,"
      },
      "status": "success"
    },
    {
      "location_name": "Faustini Rim A",
      "target": "Earth",
      "latitude": -87.45,
      "longitude": 77.0,
      "longitude_normalized": 77.0,
      "altitude_m": 2.0,
      "observation": {
        "timestamp": "2027-07-15T12:00:00Z",
        "azimuth_deg": 288.064862,
        "elevation_deg": -4.947411,
        "solar_presence": "*",
        "interfering_marker": null,
        "raw_line": "2027-Jul-15 12:00:00,*, , 288.064862,    -4.947411,"
      },
      "status": "success"
    },
    {
      "location_name": "Far Side Control Point",
      "target": "Sun",
      "latitude": -85.0,
      "longitude": 180.0,
      "longitude_normalized": -180.0,
      "altitude_m": 2.0,
      "observation": {
        "timestamp": "2027-07-15T12:00:00Z",
        "azimuth_deg": 219.515614,
        "elevation_deg": -4.390937,
        "solar_presence": null,
        "interfering_marker": null,
        "raw_line": "2027-Jul-15 12:00:00, , , 219.515614,    -4.390937,"
      },
      "status": "success"
    },
    {
      "location_name": "Far Side Control Point",
      "target": "Earth",
      "latitude": -85.0,
      "longitude": 180.0,
      "longitude_normalized": -180.0,
      "altitude_m": 2.0,
      "observation": {
        "timestamp": "2027-07-15T12:00:00Z",
        "azimuth_deg": 184.908246,
        "elevation_deg": -10.712201,
        "solar_presence": null,
        "interfering_marker": null,
        "raw_line": "2027-Jul-15 12:00:00, , , 184.908246,   -10.712201,"
      },
      "status": "success"
    }
  ],
  "longitude_equivalence_test": {
    "longitude_east": 222.1,
    "longitude_normalized": -137.9,
    "east_azimuth_deg": 177.278712,
    "east_elevation_deg": -1.088272,
    "west_azimuth_deg": 177.278712,
    "west_elevation_deg": -1.088272,
    "ephemeris_matched": true
  },
  "failures": []
}
```
