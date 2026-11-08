# Wayfinder API Contract

Version: 0.2.0
Base path: `/api/v1`
Interactive docs: `GET /docs` (Swagger UI), `GET /redoc`, raw schema at `GET /openapi.json`

This document is authoritative. If the implementation and this document
ever disagree, that is a bug - open an issue rather than coding against
the live response shape. If the contract changes, this file is updated
in the same change, and the "Changing the contract" section at the
bottom explains what the frontend must also update.

---

## Conventions used throughout

- All coordinates are `{ "lat": number, "lon": number }` in decimal degrees (WGS84).
- All timestamps are ISO 8601, UTC, e.g. `"2026-10-19T10:00:00Z"`.
- A field that **may be unavailable** is typed as nullable and will be
  `null`, never a fabricated placeholder (`0`, `"N/A"`, `-1`, etc.).
- Every response that aggregates external data includes a `data_status`
  object (see below) - **always check it** before treating numeric
  fields as reliable.
- Distances are kilometers (`distance_km`), durations are minutes
  (`duration_minutes`), unless a field name says otherwise.
- GeoJSON geometry coordinates are **`[longitude, latitude]`** pairs (the
  GeoJSON spec's order). Every other coordinate object in this API
  (`Coordinates`, used everywhere else - facility locations, alert
  locations, origin/destination) is **`{ "lat": ..., "lon": ... }`**.
  **These are not the same order.** If you're using Leaflet (which takes
  `[lat, lon]`), do not pass GeoJSON `geometry.coordinates` pairs to a
  Leaflet `LatLng` without swapping them first - this is a common,
  easy-to-miss bug. `Coordinates` objects need no swapping for Leaflet
  (just `[c.lat, c.lon]`); `geometry.coordinates` pairs do.

### `DataStatus` (appears in every data-bearing response)

```jsonc
{
  "mode": "live" | "partial" | "degraded" | "demo",
  "sources": [
    {
      "name": "osrm-routing",          // which provider/source this refers to
      "status": "ok" | "unavailable" | "error" | "not_configured",
      "detail": "string or null",      // human-readable explanation when status != "ok"
      "retrieved_at": "2026-10-19T10:00:00Z" // present only when status == "ok"
    }
  ]
}
```

- **`mode: "live"`** - every source the request actually needed returned usable data.
- **`mode: "partial"`** - the critical path succeeded (e.g. the route was
  calculated) but at least one non-critical source failed or was
  unavailable. The response still contains usable results; check
  `sources` to see what's missing.
- **`mode: "degraded"`** - a critical operation failed (e.g. the route
  could not be calculated). Dependent fields will be `null`.
- **`mode: "demo"`** - the response was assembled entirely from stored
  demonstration data (see "Demo mode" below), **not** from live provider
  calls. The frontend **must** render a visible "Demo data" indicator
  whenever `mode == "demo"` - never present it identically to a live
  result.

`source.status` meanings:
- `"ok"` - data was retrieved and used.
- `"unavailable"` - the provider could not be reached (timeout, network
  error, rate limit, 5xx), OR (for `alerts` specifically) a provider URL
  is configured but no integration has been implemented against it yet.
- `"error"` - the provider responded, but the response was invalid,
  unusable, or indicated the request failed (e.g. no geocoding match,
  no route found, malformed payload).
- `"not_configured"` - no provider URL is set for this deployment at all
  or the required credentials are missing
  (currently used for Bhuvan when its token is not set). This status comes from an explicit, structured `reason`
  set by the service that raised the error - **not** from pattern-matching
  the human-readable message text (an earlier version did that; it was
  fragile and has been removed).

**Frontend rule of thumb:** never render a numeric/score field as if it
were a confident answer without checking whether its corresponding
source is `"ok"`. Use `detail` as user-facing or debug explanatory text.

### Routing provider and backup

`POST /journeys/analyse` attempts Bhuvan Shortest Path when
`ISRO_BHUVAN_TOKEN` is set in the backend environment. On missing/expired
tokens, provider errors, or unusable GeoJSON, the backend uses its configured
OSRM routing provider as a backup. `data_status.sources` reports
`isro-bhuvan-routing` with the failure reason and `osrm-routing` with a
detail that the backup was used. The dashboard displays that fallback notice
to the user. If Bhuvan succeeds, geometry is returned,
but distance and duration are `null` because the documented Bhuvan response
only guarantees route GeoJSON; the backend does not invent those values.
OSRM's route includes distance and estimated duration.

---

## Demo mode

Every environment ships three pieces of stored, labeled demonstration
data for the Chandigarh -> Ludhiana corridor (`app/data/demo/`):
a route, 18 candidate roadside facilities, and 2 fictional alerts. Demo
mode lets the app be shown and developed against **without any external
network access or provider credentials** - useful for frontend
development, offline demos, and this sandboxed build/test environment,
none of which can reach the live providers.

Request it with `"demo": true` on `POST /journeys/analyse`:
```jsonc
{ "origin": "anything", "destination": "anything", "demo": true }
```
`origin`/`destination` are still required by the request schema but are
**ignored** in demo mode - the response always describes the fixed
Chandigarh -> Ludhiana demo journey regardless of what you send. No
provider calls are made at all (not even geocoding). The real risk
engine still runs over the demo alert data, so `risk_assessment` is
genuine rule-based output, not a hard-coded value.

The response has **`data_status.mode == "demo"`** and every
`data_status.sources[].status` is `"demo"`-labeled via its `name`
(`"demo-route"`, `"demo-facilities"`, `"demo-alerts"`) - check `mode`,
not individual source names, to detect demo mode reliably.

**Data integrity of the demo data itself** (what each piece actually is,
verified by inspecting the stored files, not assumed):
- **Route**: `app/data/demo/demo_journey.json`'s `_meta.provider_validated`
  is `false` - the distance/duration/geometry are a human-approximated
  estimate, **not** a captured OSRM response (network access to fetch a
  real one was unavailable in this environment - see
  `scripts/capture_demo_route.py` to produce a real one when you have
  network access). Do not treat demo route numbers as provider-accurate.
- **Facilities**: all 18 records have `verification_status:
  "unverified_coordinates"` (never `"verified"`) - their coordinates are
  manual address-derived estimates, not geocoder or Overpass output. See
  "Facility verification" below.
- **Alerts**: both records' `description` field **starts with the literal
  text `"[SIMULATED DEMO DATA — NOT a real incident report]"`** - this is
  in the field itself (what a consumer actually renders), not only in an
  internal note that gets stripped before the response. Both also have
  `source: "demo-data"` and `verified: false`.

---

## `GET /api/v1/health`

No parameters.

**200 response:**
```json
{ "status": "ok", "service": "wayfinder-api" }
```

---

## `POST /api/v1/journeys/analyse`

Full journey analysis: geocoding, routing, nearby facilities, weather,
alerts, and a risk assessment with recommendations - sampled along the
route, not only at the destination (see "Route-aware facilities/weather"
below). Or, with `"demo": true`, the stored demo response (see "Demo
mode" above) - no network calls at all.

### Request body

```jsonc
{
  "origin": "Chandigarh, India",               // required, 1-300 chars, non-blank
  "destination": "Ludhiana, Punjab, India",     // required, 1-300 chars, non-blank
  "travel_mode": "driving",                    // optional: driving, two-wheeler, cycling, transit
  "origin_coordinates": { "lat": 30.74, "lon": 76.78 }, // optional; bypasses origin geocoding
  "destination_coordinates": { "lat": 30.90, "lon": 75.86 }, // optional; bypasses destination geocoding
  "include_facilities": true,                  // optional, default true
  "include_alerts": true,                      // optional, default true
  "facility_radius_km": 5.0,                   // optional, default 5.0, (0, 50]
  "facility_categories": ["hospital", "fuel", "rest_stop"], // optional, default shown; any of: hospital, fuel, restaurant, rest_stop
  "demo": false                                // optional, default false - see "Demo mode"
}
```

Supported `travel_mode` values are `"driving"`, `"two-wheeler"`,
`"cycling"`, and `"transit"`. An unsupported value or a missing/blank
`origin`/`destination` returns `422` (see "Error responses" below).
Optional `origin_coordinates` and `destination_coordinates` use WGS84
`{lat, lon}` values and bypass text geocoding for the respective endpoint;
the required text fields are still retained as the query/display label.
This validation still applies in demo mode even though locations are
otherwise ignored there.

Bhuvan is used only for `"driving"`; all other modes use the configured
OSRM-compatible routing provider. `"two-wheeler"` uses its driving profile.
`"cycling"` requests its cycling profile, which must be enabled by the
configured OSRM deployment (the public OSRM demo may not provide it).
OSRM does not provide a transit profile: `"transit"` currently returns a
road-route approximation, not train paths, schedules, or a public-transit
itinerary. These limitations are returned in the `osrm-routing` source
detail and should be shown to users.

### 200 response shape

```jsonc
{
  "journey": {
    "origin": {
      "query": "Chandigarh, India",                 // echoes what the client sent (demo mode: the fixed demo origin)
      "resolved": { "lat": 30.74, "lon": 76.78 },    // null if geocoding failed
      "display_name": "Chandigarh, India"            // provider's normalized name; null if unresolved
    },
    "destination": { "query": "...", "resolved": {...} | null, "display_name": "..." | null },
    "distance_km": 35.0,           // null if the route could not be calculated
    "duration_minutes": 48.0,      // null if the route could not be calculated
    "geometry": {                  // GeoJSON LineString, null if unavailable. [lon, lat] pairs - see Conventions.
      "type": "LineString",
      "coordinates": [[76.78, 30.74], [76.40, 30.80], "..."]
    }
  },
  "facilities": [
    {
      "id": "node/123456",          // provider-native id (live) or a stable demo id; null if unavailable
      "name": "City Hospital",       // null if the source record has no name
      "category": "hospital",        // one of: hospital, fuel, restaurant, rest_stop
      "coordinates": { "lat": 30.74, "lon": 76.78 },
      "distance_km": 1.2,             // great-circle distance from the sample point it matched; null if not calculable
      "address": "12, Sector 32, Chandigarh" | null,
      "source": "overpass-osm" | "demo-deepak-directory",
      "verification_status": "verified" | "address_matched" | "unverified_coordinates" | "unavailable",
      "coordinate_source": "openstreetmap-overpass" | "address-derived-approximation (...)" | null,
      "last_verified_at": "2026-10-19T10:00:00Z" | null
    }
  ],
  "alerts": [
    {
      "id": "string | null",
      "description": "string",   // demo alerts: starts with "[SIMULATED DEMO DATA ...]" - see "Demo mode"
      "category": "string | null",
      "severity": "low" | "moderate" | "high" | "unknown",
      "location": { "lat": 0, "lon": 0 } | null,
      "source": "string",         // "demo-data" for demo alerts
      "retrieved_at": "2026-10-19T10:00:00Z" | null,
      "verified": true | false | null,
      "relevance": "string | null"
    }
  ],
  "weather_samples": [
    {
      "location": { "lat": 30.74, "lon": 76.78 },
      "observation_time": "2026-10-19T10:00:00Z" | null,
      "temperature_c": 24.5 | null,
      "windspeed_kmh": 12.0 | null,
      "winddirection_deg": 90 | null,
      "weather_code": 0 | null,
      "is_day": true | null,
      "source": "open-meteo"
    }
    // 0-3 entries: up to one per route sample point (origin/midpoint/destination)
    // that returned data. [] if weather was unavailable, not requested, or
    // (always, currently) in demo mode - see "Route-aware facilities/weather".
  ],
  "risk_assessment": {
    "level": "unknown" | "low" | "moderate" | "high",
    "score": 23.5,     // 0-100, HIGHER = more caution warranted. null when there's insufficient data (level will be "unknown" in that case)
    "reasons": [
      "Current weather near the route does not indicate hazardous conditions.",
      "This assessment reflects currently available data only. It does not predict accidents and does not guarantee travel safety."
    ]
  },
  "recommendations": [
    "No significant issues were found in the available data; standard travel precautions still apply."
  ],
  "data_status": {
    "mode": "live",    // or "partial" | "degraded" | "demo"
    "sources": [
      { "name": "nominatim-geocoding", "status": "ok", "retrieved_at": "..." },
      { "name": "nominatim-geocoding", "status": "ok", "retrieved_at": "..." },
      { "name": "osrm-routing", "status": "ok", "retrieved_at": "..." },
      { "name": "overpass-osm", "status": "ok", "retrieved_at": "..." },
      { "name": "open-meteo", "status": "ok", "retrieved_at": "..." },
      { "name": "alerts", "status": "ok" }
      // if ALERT_PROVIDER_URL were explicitly unset instead:
      // { "name": "alerts", "status": "not_configured", "detail": "ALERT_PROVIDER_URL is not configured..." }
    ]
  }
}
```

**This endpoint always returns `200`** for structurally valid requests,
even when every upstream provider fails - the honesty signal is
`data_status`/`risk_assessment.level`/`null` fields, not the HTTP status
code. This is a deliberate contract decision (see "Why always 200?"
below). The frontend should branch its UI on `data_status.mode` and
`risk_assessment.level`, not on HTTP status, for this endpoint.

**Important semantics:**
- `risk_assessment.level == "unknown"` and `score == null` together mean
  "we don't have enough reliable data to assess this journey" - render
  this distinctly from `"low"` (data was available and nothing adverse
  was found). Never collapse `"unknown"` into `"low"` in the UI.
- `recommendations` are generated from the actual findings for this
  specific response (not static boilerplate) - always render them,
  don't substitute your own generic copy.
- The risk engine's weather contribution uses only the **destination**
  weather sample (falling back to the last successful sample if that one
  specifically failed) - it does not average multiple samples together.

### Why always `200`?

A single journey-analysis request fans out to several independent
external calls. Failing the *whole* HTTP request because, say, the
weather provider timed out would throw away a perfectly good route and
facility list. Instead, each sub-system degrades independently and the
response says exactly what succeeded. A non-`200` from this endpoint
means the *request itself* was invalid or the server had an unexpected
internal error - not "an upstream provider was unavailable."

### Route-aware facilities/weather

Facilities and weather are sampled at **up to 3 points along the
route** - origin, an approximate midpoint, and destination
(`MAX_ROUTE_SAMPLE_POINTS` in `app/services/facilities.py`) - not only
at the destination (an earlier version only checked the destination;
this was a real limitation, now partially addressed).

**What this is:**
- Facilities: an independent nearby-search around each of the (up to 3)
  sample points, merged and deduplicated by facility id.
- Weather: an independent observation at each of the (up to 3) sample
  points, returned as `weather_samples` (a list, not a single value).
- The "midpoint" sample is the **middle vertex of the route polyline**
  when geometry is available (a simple approximation, not a
  distance-interpolated true midpoint), or the straight-line average of
  origin/destination otherwise.

**What this is NOT** (documented limitations, not hidden):
- Not a continuous corridor query - the space between sample points,
  if farther apart than roughly `2 x facility_radius_km`, is not covered.
- Not a comprehensive route forecast - `weather_samples` is 0-3 points
  in time and space, not a segment-by-segment forecast.
- The sample-point count is capped deliberately to bound the number of
  Overpass/Open-Meteo requests per journey-analysis call to a small,
  predictable number regardless of route length.

### Alert route-corridor relevance

Alert relevance to the route is checked against the **actual route
LineString geometry** (minimum distance from the alert's location to any
segment of the route line), not just the two endpoints - a genuinely
mid-route alert is correctly detected even though it may be far from
both the origin and the destination individually. The corridor
half-width is `ROUTE_CORRIDOR_KM = 10.0` km
(`app/engine/risk_engine.py`).

If route geometry is missing/invalid, relevance falls back to
endpoint-only distance, and `risk_assessment.reasons` explicitly says so
("Route geometry was unavailable... a mid-route alert could have been
missed.") - this fallback can only ever make the check *less* precise
(a possible false negative, missing a real mid-route alert), never a
false positive, since it only widens what counts as "close enough" by
replacing a correct check with a cruder one.

---

## `GET /api/v1/facilities/nearby`

| Param | Type | Required | Notes |
|---|---|---|---|
| `lat` | float | yes | -90..90 |
| `lon` | float | yes | -180..180 |
| `radius_km` | float | no (default 5.0) | must be >= 0.2 and <= 70 (`MIN_FACILITY_RADIUS_KM`/`MAX_FACILITY_RADIUS_KM`; raised from a 50km max for the hybrid map-to-globe feature's 200m-70km radius control) |
| `category` | string | no | one of `hospital`, `fuel`, `restaurant`, `rest_stop`; omit to search all four |

**200 response:**
```jsonc
{
  "query": { "lat": 30.73, "lon": 76.77 },
  "radius_km": 5.0,
  "category": "hospital" | null,
  "facilities": [ /* same Facility shape as in journey analysis, including verification_status etc. */ ],
  "data_status": { "mode": "live" | "degraded", "sources": [ { "name": "overpass-osm", "status": "...", ... } ] },
  "result_truncated": false,   // true if the provider's raw response hit its own result cap - see below
  "result_limit": null         // the cap that was hit, only populated when result_truncated is true
}
```

This endpoint always searches a **single point** (no route-corridor
sampling - that's specific to journey analysis). Live results always
have `verification_status: "verified"` (Overpass/OSM is this backend's
designated authoritative facility source, so its own returned
coordinates for a feature are treated as verified location data - this
is **not** a claim about the facility's operating status, hours, or
capabilities).

If the facility provider is unavailable, `facilities` is `[]` and
`data_status.mode` is `"degraded"` - this is distinct from a
successful, empty search result (which is also `facilities: []` but
`mode: "live"`). **Always check `data_status.mode`** before treating an
empty array as "confirmed nothing nearby."

`radius_km` below `MIN_FACILITY_RADIUS_KM` (default 0.2) or above
`MAX_FACILITY_RADIUS_KM` (default 70), or out-of-range coordinates,
return `422`.

#### Large-radius (>20km) safeguards

A request with `radius_km` above `FACILITY_LARGE_RADIUS_THRESHOLD_KM`
(default 20) uses a longer provider timeout
(`FACILITY_LARGE_RADIUS_TIMEOUT_SECONDS`, default 25s) and a larger,
explicit Overpass result cap (`FACILITY_LARGE_RADIUS_RESULT_LIMIT`,
default 400) instead of the small-radius defaults, since a wide area
can legitimately contain far more mapped facilities and take longer to
query. **`facilities` is never guaranteed exhaustive at any radius** -
Overpass's own `out` limit caps the raw response before this backend's
distance-sort runs. When that cap was hit, `result_truncated` is `true`
and `result_limit` names the cap; callers must not present the list as
"every facility in the radius" in that case.

### Facility verification

Three fields on every `Facility` describe confidence in its
**coordinates only** - never its operating status, hours, or
capabilities (open/closed, has EV charging, has CNG, etc. are never
asserted unless a source explicitly provides them):

| `verification_status` | Meaning |
|---|---|
| `"verified"` | Coordinates came directly from the designated authoritative geographic source for this data (currently: returned by the OSM/Overpass node itself). |
| `"address_matched"` | Coordinates came from geocoding a text address (e.g. Nominatim), not independently cross-checked against a second source. Not currently produced by any code path in this build - reserved for when/if demo facilities are run through a geocoder (see `scripts/` - none exists yet for this). |
| `"unverified_coordinates"` | Coordinates are a manual/approximate estimate, not geocoder or authoritative-map output. All 18 current demo facilities are this status. |
| `"unavailable"` | No usable coordinates could be established. Not currently produced (a facility with no coordinates isn't returned at all), reserved for future use. |

`coordinate_source` is a free-text string describing what produced the
coordinates (e.g. `"openstreetmap-overpass"`,
`"address-derived-approximation (manual estimate; not geocoded, not
Overpass-sourced)"`). `last_verified_at` is the UTC retrieval/check
timestamp, `null` for manual estimates.

**Frontend rule of thumb:** a facility with `verification_status !=
"verified"` should not be presented identically to a confirmed map
pin - e.g. a different marker style, or a "location approximate,
unverified" label - and should never be described as open, operational,
or having any specific capability unless another field explicitly says so.

---

## `GET /api/v1/weather`

| Param | Type | Required | Notes |
|---|---|---|---|
| `lat` | float | yes | -90..90 |
| `lon` | float | yes | -180..180 |

Single-point weather lookup - unrelated to the multi-sample
`weather_samples` used internally by journey analysis; this endpoint is
unchanged by that feature.

**200 response:**
```jsonc
{
  "observation": {
    "location": { "lat": 30.73, "lon": 76.77 },
    "observation_time": "2026-10-19T10:00:00Z" | null,
    "temperature_c": 24.5 | null,
    "windspeed_kmh": 12.0 | null,
    "winddirection_deg": 90 | null,
    "weather_code": 0 | null,   // WMO weather code, see https://open-meteo.com/en/docs
    "is_day": true | null,
    "source": "open-meteo"
  } | null,  // null when data_status.mode != "live"
  "data_status": { "mode": "live" | "degraded", "sources": [...] }
}
```

---

## `GET /api/v1/alerts`

| Param | Type | Required | Notes |
|---|---|---|---|
| `lat` | float | yes | -90..90 |
| `lon` | float | yes | -180..180 |
| `radius_km` | float | no (default 25.0) | (0, 200] |

**200 response:**
```jsonc
{
  "query": { "lat": 30.73, "lon": 76.77 },
  "alerts": [ /* Alert objects, see journey analysis shape above */ ],
  "data_status": { "mode": "live" | "degraded", "sources": [ { "name": "alerts", "status": "not_configured" | "unavailable" | "error" | "ok", "detail": "..." } ] }
}
```

**Provider (default):** NASA EONET (`https://eonet.gsfc.nasa.gov/api/v3`),
free and keyless - see `app/services/alerts.py` and the README "External
providers used" table. It returns ongoing natural-hazard events
(wildfires, severe storms, floods, volcanoes, landslides, earthquakes,
etc.), each normalized to the `Alert` shape above with a real
`location`, a conservative `severity` derived from its EONET category
(unmapped categories are honestly `"unknown"`, never guessed), and
`verified: null` (EONET aggregates multiple agencies; it does not itself
mark a report independently verified).

**Known limitation:** this is **not** a traffic/road-closure feed - no
free, keyless, sufficiently-current source of verified road
closures/incidents was found (particularly for the India corridor used
in the contract's example). If `ALERT_PROVIDER_URL`/`ALERT_PROVIDER_KEY`
are explicitly unset (e.g. a deployment that intentionally disables
alerts), this endpoint returns `alerts: []` with
`data_status.sources[0].status == "not_configured"`. **Do not interpret
the empty array as "no disruptions reported"** in that case - render the
`not_configured` state distinctly (e.g. "Alerts: not available for this
deployment" rather than "No alerts"). This status is determined by an
explicit `reason` the service sets, not by inspecting message text (see
`app/services/exceptions.py` `ServiceUnavailableError.reason`).

For demonstration alert data, use journey analysis with `"demo": true`
instead - this endpoint has no demo mode of its own.

---

## Error responses (client-input / server errors)

**One consistent envelope for every error response**, whatever raised
it (Pydantic validation, a manually-raised `HTTPException`, or a route
simply not existing):

```jsonc
{
  "error": {
    "code": "SOME_CODE",
    "message": "Human-readable explanation.",
    "details": [ /* present only for validation errors */ ]
  }
}
```

This **never** fires for upstream provider failures in journey/
facilities/weather/alerts - those are always reported via `data_status`
in a `200` response instead (see "Why always 200?").

Structurally invalid requests (bad coordinate ranges, unsupported
`travel_mode`, missing required fields, an out-of-range `radius_km`,
bodies that fail Pydantic validation) return:

```jsonc
// 422 Unprocessable Entity
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "details": [
      { "type": "value_error", "loc": ["body", "origin"], "msg": "Value error, must not be blank", "input": "   " }
    ]
  }
}
```

`details` is FastAPI/Pydantic's standard error-list shape (list of
`{type, loc, msg, input}`), so existing Pydantic-error-rendering code on
the frontend can be reused - it's just nested one level deeper than the
previous contract version (`error.details` instead of a top-level
`detail`).

A route that doesn't exist, or other framework-level HTTP errors:
```jsonc
// 404 Not Found
{ "error": { "code": "NOT_FOUND", "message": "Not Found" } }
```

An unexpected server-side bug returns:
```jsonc
// 500 Internal Server Error
{ "error": { "code": "INTERNAL_ERROR", "message": "An unexpected error occurred." } }
```
Stack traces and internal details are never included in this response
(they're logged server-side only).

`code` values currently produced: `VALIDATION_ERROR` (422),
`BAD_REQUEST` (400), `NOT_FOUND` (404), `METHOD_NOT_ALLOWED` (405),
`RATE_LIMITED` (429), `INTERNAL_ERROR` (500); any other HTTP status
from a manually-raised exception falls back to `HTTP_ERROR`.

---

## CORS

Allowed origins are controlled by the `CORS_ORIGINS` environment
variable (comma-separated; defaults include `http://localhost:5173` and
`http://127.0.0.1:5173` for a Vite dev server, alongside port 3000). All
methods and headers are allowed for those origins; credentials are
allowed. See `.env.example`.

---

## Provider compliance notes (affects behavior, not just config)

- **Nominatim** (geocoding): the default `HTTP_USER_AGENT` is an
  unmistakable placeholder (contains `CHANGE.ME`) - it is **not** a real,
  usable contact address, and the app logs a startup warning if it's
  still in use. Set a real one via `.env` before any non-trivial use.
  Geocoding requests are also throttled to at most one per
  `NOMINATIM_MIN_INTERVAL_SECONDS` (default 1.0s) process-wide, per
  Nominatim's public-instance usage policy.
- **OSRM** (routing): the public demo server used by default is
  explicitly a fair-use demo service, not for production load.

---

## Changing the contract

If you need to change this contract:

1. Update this file first, in the same change as the code.
2. Note explicitly here (in a dated changelog entry below) which fields
   changed and what the frontend must update: TypeScript types, any
   hardcoded field-name strings, and `data_status`-branching logic if
   the `mode`/`status` enums changed.
3. Prefer additive changes (new optional fields) over breaking ones
   (renaming/removing fields, changing a field's type or nullability)
   whenever possible, since the frontend is developed independently.

### Changelog

- **0.2.0**: Added `demo` mode (`"demo"` request field, `data_status.mode
  == "demo"`). Added `Facility.verification_status` /
  `coordinate_source` / `last_verified_at` (required field -
  **breaking** for any code constructing a `Facility` directly, but
  purely additive for API *consumers*, since it's a new field on an
  existing object). Added `weather_samples` to the journey-analysis
  response (previously computed internally but never returned - this is
  new data becoming visible, not a removal). Facilities/weather in
  journey analysis are now sampled at up to 3 points along the route
  instead of only at the destination. Alert relevance now checks the
  full route geometry, not just the two endpoints
  (`ROUTE_CORRIDOR_KM = 10.0`, was `ALERT_PROXIMITY_KM = 15.0` against
  endpoints only). Error responses changed shape: `{"error": {"code",
  "message", "details"}}` replaces the old `{"error": "validation_error",
  "detail": [...]}` - **breaking** for any frontend error-parsing code
  written against 0.1.0.
- **0.1.0** (initial): first implementation of all five endpoints described above.
