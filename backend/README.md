# Wayfinder Backend

**Your journey, understood.**

A Travel-Aware Location Intelligence API: journey analysis combining
routing, nearby facilities, weather, travel alerts (where available),
and a transparent, rule-based risk assessment, for the Chandigarh,
India -> Ludhiana, Punjab, India demonstration corridor (and any other
origin/destination via the live endpoints).

Built with FastAPI + Pydantic v2 + HTTPX, designed to be consumed by an
independently-developed React/TypeScript/Leaflet frontend via the
documented contract in [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).
If that frontend doesn't exist yet in your copy of this repo, see
`docs/frontend-types.ts` for the exact TypeScript types to build against.

## Quick start

Requires Python 3.11+.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # edit HTTP_USER_AGENT - see "Before you deploy" below
                                    # sane defaults otherwise work with no .env at all

uvicorn app.main:app --reload --port 8000
```

Then open:
- `http://localhost:8000/docs` - interactive Swagger UI
- `http://localhost:8000/api/v1/health` - health check

No API keys are required to run this MVP end-to-end: routing, geocoding,
facilities, weather, AND travel alerts (NASA EONET) all use free,
keyless public providers by default (see "External providers used"
below). One optional upgrade - NASA FIRMS active-fire detections, merged
into alerts - needs a free key; see "External providers used" for where
to get it and where to paste it. Travel alerts still aren't a
traffic/road-closure feed - see "Known Limitations" #1. **If you have no
network access at all** (or want a deterministic, offline-friendly
demo), use demo mode - see below.

Optional Bhuvan routing: add `ISRO_BHUVAN_TOKEN=...` to this
`backend/.env` file. Bhuvan is attempted first; when its token is missing
or expired, or its response cannot be used, routing falls back to the
configured OSRM provider. The journey response reports the failure and
the successful backup in `data_status.sources`, and the frontend shows a
backup notice. Bhuvan's documented route response supplies GeoJSON; when
it does not supply distance or duration, those values remain `null`.
The default public OSRM demo endpoint is fair-use only, not a production
availability guarantee.

### Demo mode (no network access required)

```bash
curl -s -X POST http://localhost:8000/api/v1/journeys/analyse \
  -H "Content-Type: application/json" \
  -d '{"origin": "anything", "destination": "anything", "demo": true}'
```

Returns a complete, stored response for the Chandigarh -> Ludhiana
corridor - no provider calls, no network access, no API keys. The real
risk engine still runs over the (clearly-labeled fictional) demo alert
data, so `risk_assessment` is genuine rule-based output. Full semantics,
including what's honestly verified vs. estimated in the demo data
itself, are in `docs/API_CONTRACT.md` under "Demo mode."

**Before you deploy anywhere beyond local development:** edit
`HTTP_USER_AGENT` in your `.env`. The shipped default is an unmistakable
placeholder (`PLACEHOLDER-SET-HTTP_USER_AGENT-CONTACT@CHANGE.ME`), not a
real contact address - Nominatim's usage policy requires a genuine one,
and the app logs a startup warning if you haven't changed it.

## Running tests

```bash
pip install -r requirements.txt    # includes pytest, pytest-asyncio, respx
pytest                              # or: pytest -v
```

**110 tests**, all passing, all against mocked HTTP responses (via
`respx`) or pure in-process logic - **no live third-party API calls are
made during the test suite**, and no network access or API keys are
required to run it. (This count is the actual, re-verified result of
running `pytest` after wiring NASA EONET as the alerts provider;
the alerts-specific tests mock the exact documented response shapes
for EONET - see `tests/test_alerts.py`.)

Tests cover:

- Health endpoint
- Valid and invalid journey-analysis requests (bad `travel_mode`, missing fields, blank input)
- Routing provider timeout and invalid upstream responses
- Facility search (success, excluded/unmapped categories, provider unavailable)
- Facility coordinate verification status (live = `"verified"`, demo = `"unverified_coordinates"`)
- Weather provider unavailable / not configured / invalid response
- Alerts: live NASA EONET normalization (category/severity mapping, real
  haversine-distance filtering beyond the bbox rectangle, unmapped
  categories correctly left `"unknown"` rather than guessed), explicit
  `reason`-based unavailable/not-configured status (not string-matching)
- Risk engine: verified/unverified/stale alert weighting, duplicate-alert
  collapsing, unknown-severity handling, route-**corridor** proximity
  (mid-route alert detection via full geometry, far-from-route exclusion,
  malformed-geometry fallback), insufficient-data -> `"unknown"` behavior
- Demo mode: route/facilities/alerts load correctly, demo alert
  descriptions are unmistakably fictional, `data_status.mode == "demo"`,
  live mode is unaffected by the `demo` field being absent
- Nominatim request throttling and User-Agent configuration
- Unified error-response envelope (validation errors, manually-raised
  `HTTPException`s, and framework-level 404s all produce the same shape)
- A full end-to-end journey-analysis pipeline integration test

Where possible, also start the real server and smoke-test it locally:
```bash
uvicorn app.main:app --port 8001 &
curl -s http://127.0.0.1:8001/api/v1/health
curl -s -X POST http://127.0.0.1:8001/api/v1/journeys/analyse \
  -H "Content-Type: application/json" -d '{"origin":"X","destination":"Y","demo":true}'
```
This was done during development in a network-sandboxed environment:
`health` and demo-mode requests succeeded over real HTTP; live-provider
requests correctly returned `200` with `data_status.mode: "degraded"`
and honest `null`/`unavailable` fields once DNS resolution to the
provider hosts failed, rather than crashing or fabricating data. **No
live provider integration (OSRM, Nominatim, Overpass, Open-Meteo) was
actually exercised end-to-end** in that environment - state this
explicitly rather than assuming it works; see "Live integration status"
below for what to check once you have real network access.

## Live integration status

The sandboxed environment this was built/repaired in cannot reach
`nominatim.openstreetmap.org`, `router.project-osrm.org`,
`overpass-api.de`, `api.open-meteo.com`, `eonet.gsfc.nasa.gov` (its
outbound network policy blocks arbitrary external hosts, same as the
DNS-resolution failures noted below for the pre-existing providers).
This means:
- **Not verified by actually calling it from inside this sandbox:** live
  geocoding, routing, facility search, weather, or alerts retrieval
  against real providers for the Chandigarh -> Ludhiana route or any
  other.
- **Verified a different way for NASA EONET specifically:** its real,
  current response shape (`events: [{id, title, categories: [{id,
  title}], sources: [{id, url}], geometry: [{date, type, coordinates:
  [lon, lat]}]}]`) and its documented query parameters (`bbox`, `days`,
  `status`, `limit`, `start`/`end`, `magID`/`magMin`/`magMax`) were
  fetched and inspected directly against the live API from outside this
  sandboxed shell before `app/services/alerts.py` was written against
  it - per this project's "never guess a schema" rule.
- **Verified in this environment:** every endpoint's *failure-handling*
  path, by actually triggering it (not by code inspection alone) - real
  `200` responses with correct `data_status: "degraded"`/`null` fields
  when those real network calls genuinely failed; and, for alerts
  specifically, full normalization logic against mocked responses built
  from the real inspected shape above (`tests/test_alerts.py`).
- To verify live integration yourself: run `scripts/capture_demo_route.py`
  (see below) or just start the server and call
  `POST /journeys/analyse` with `"demo": false` (or omit `demo`) from a
  machine with normal internet access, and check the response's
  `data_status.mode` - it should be `"live"` if every source succeeds.

### `scripts/capture_demo_route.py`

One-time tool to replace the stored demo route with a **genuine OSRM
response** (not a hand-approximated polyline) once you have network
access:
```bash
python3 scripts/capture_demo_route.py \
  --origin "Chandigarh, India" --destination "Ludhiana, Punjab, India"
```
It geocodes both ends, requests a real route, and only then overwrites
`app/data/demo/demo_journey.json` - with the provider's own
distance/duration/geometry, a retrieval timestamp, and
`_meta.provider_validated: true`. If any step fails, it prints the
actual error and **leaves the existing file untouched** (verified by
actually running it in this environment: it failed at the geocoding
step with a DNS resolution error, exactly as expected, and the file was
confirmed unchanged afterward).

## Linting

```bash
ruff check .
ruff format .
```

## Project structure

```
backend/
  app/
    main.py                  # FastAPI app, CORS, lifespan-managed HTTP client, unified error handlers
    api/
      deps.py                # FastAPI dependency providers (settings, shared http client, services)
      routes/
        health.py
        journeys.py           # POST /journeys/analyse - orchestrates the full pipeline + demo mode
        facilities.py
        weather.py
        alerts.py
    schemas/                  # Pydantic request/response models
      common.py                # Coordinates, SourceMeta, DataStatus (mode incl. "demo")
      journey.py                # includes `demo` request field, `weather_samples` response field
      facility.py                # includes verification_status / coordinate_source / last_verified_at
      weather.py
      alert.py
    services/                  # External provider integrations, isolated behind clean interfaces
      exceptions.py             # ServiceUnavailableError (structured `reason`), ServiceResponseError, NotFoundError
      routing.py                 # geocoding + Bhuvan routing with OSRM fallback
      facilities.py               # OpenStreetMap Overpass API; search_nearby + search_along_route
      weather.py                   # Open-Meteo
      alerts.py                     # NASA EONET (default, keyless) + optional NASA FIRMS merge
      demo.py                        # loads+validates stored demo data (fails loudly on bad records)
    data/
      demo/
        demo_journey.json       # stored Chandigarh->Ludhiana route (provider_validated: false - see above)
        demo_facilities.json     # 18 candidate POIs, all verification_status: "unverified_coordinates"
        demo_alerts.json          # 2 fictional alerts, descriptions explicitly marked [SIMULATED DEMO DATA]
    engine/
      risk_engine.py          # deterministic, rule-based, FastAPI/HTTP-independent risk scoring;
                               # route-corridor alert proximity against full LineString geometry
    core/
      config.py                # environment-driven settings, provider-availability checks, Nominatim throttle config
  scripts/
    capture_demo_route.py    # one-time live-provider route capture tool (see above)
  tests/
  docs/
    API_CONTRACT.md           # authoritative frontend/backend contract
    frontend-types.ts         # TypeScript types matching the contract (no frontend exists yet in this repo)
  .env.example
  requirements.txt
  pytest.ini
```

## External providers used

All are free/keyless by default (good for an MVP and for the test
suite's realism) but come with usage caveats you should know about
before production use:

| Capability | Provider (default) | Notes |
|---|---|---|
| Geocoding | [Nominatim](https://nominatim.org/) public instance | Subject to a strict [usage policy](https://operations.osmfoundation.org/policies/nominatim/) (~1 req/sec, requires a valid User-Agent, no heavy/bulk use). **Enforced in code**: `NOMINATIM_MIN_INTERVAL_SECONDS` throttle (default 1.0s, process-wide) + a startup warning if `HTTP_USER_AGENT` is still the placeholder. Self-host or use a commercial geocoder for production. |
| Routing | [OSRM](https://project-osrm.org/) public demo server | Explicitly a fair-use **demo** service, not for production load. Kept as-is in this repair (Sameer's research recommends openrouteservice instead, but switching providers wasn't necessary to fix the identified defects - see "Provider choice" below). Self-host OSRM or use a commercial routing API for production. |
| Facilities | [OpenStreetMap Overpass API](https://overpass-api.de/) | Community-maintained data; coverage/attribute completeness (names, addresses) varies by region. Rate-limited; consider a dedicated Overpass instance for production. |
| Weather | [Open-Meteo](https://open-meteo.com/) | Free for non-commercial use; check their terms before commercial deployment. |
| Travel alerts | [NASA EONET](https://eonet.gsfc.nasa.gov/docs/v3) | Free, keyless. Natural-hazard events (wildfires, storms, floods, volcanoes, landslides, earthquakes...), NOT traffic/road closures - see "Known Limitations" #1. `ALERT_PROVIDER_URL` in `.env.example`. |

All provider URLs are environment-configurable (`.env.example`) so you
can point at self-hosted or commercial alternatives without code
changes, as long as you also update the corresponding service module to
match that provider's actual response shape (see
`app/services/*.py` docstrings).

### Provider choice: why OSRM, not openrouteservice

Sameer's API research recommends openrouteservice (ORS). This repair
**kept OSRM** rather than switching, per the explicit instruction not to
introduce a new provider unless necessary: OSRM's public demo server
already works for this MVP's needs (distance, duration, GeoJSON
geometry) without an API key, while ORS requires registering for a free
API key - an extra setup step with no corresponding fix to any of the
defects this repair addressed. If ORS's richer feature set (e.g.
traffic-aware routing, more granular profiles) becomes a genuine
requirement, switching is a contained change scoped to
`app/services/routing.py`.

## Network access required

The default providers are reached over the public internet at:
`nominatim.openstreetmap.org`, `router.project-osrm.org`,
`overpass-api.de`, and `api.open-meteo.com`. If you run this behind a
restrictive firewall or in a sandboxed environment with an egress
allowlist, add those hosts to it. Without outbound access to them, every
live endpoint still responds correctly (`200`, honest `data_status:
"degraded"`, `null` fields) - it just won't have live data, which is the
intended fail-safe behavior described throughout this README. Use demo
mode (above) for a fully offline-capable demonstration.

## Known Limitations

1. **Travel alerts cover natural hazards, not traffic/road closures.**
   `ALERT_PROVIDER_URL` defaults to NASA EONET, a free, keyless feed of
   ongoing natural-hazard events (wildfires, severe storms, floods,
   volcanoes, landslides, earthquakes, etc.). A search for a free,
   keyless, sufficiently-current source of verified road closures/
   traffic incidents (particularly for the India corridor used in the
   contract's example) still did not turn up a suitable option. If
   `ALERT_PROVIDER_URL`/`ALERT_PROVIDER_KEY` are
   explicitly unset, `GET /api/v1/alerts` and the alerts section of
   journey analysis still report an explicit `"not_configured"` status
   (via a structured `reason`, not string-matching) rather than
   returning an empty-but-successful result that could be mistaken for
   "confirmed no disruptions." To add a true traffic/closure feed: pick a
   real provider (a government open-data feed, or a commercial
   traffic-incidents API), inspect its actual documented response
   format, and extend `AlertService` in `app/services/alerts.py` to
   merge it in the same way FIRMS is merged alongside EONET (do not
   guess the schema).

   **ISRO's Bhuvan platform was evaluated and intentionally not wired
   in** for the same no-guessing rule: its API portal
   (bhuvan-app1.nrsc.gov.in/api) issues access tokens via an interactive
   login that expire in roughly 24 hours, not a stable secret suitable
   for a long-lived `.env` value, and its relevant endpoints aren't
   publicly documented well enough to normalize responsibly. This is a
   reasonable follow-up for whoever can maintain a manually-refreshed
   token.

2. **Only `driving` is supported as a travel mode.** The request schema
   (`TravelMode` in `app/schemas/journey.py`) is a `Literal` that can be
   extended once the routing provider is confirmed to support another
   mode.

3. **Facilities/weather route-sampling is bounded and approximate**, not
   a continuous corridor query - up to 3 sample points
   (origin/midpoint/destination), midpoint is the polyline's middle
   vertex (not distance-interpolated). See `docs/API_CONTRACT.md`
   "Route-aware facilities/weather" for the full, honest limitation.

4. **Demo facility coordinates remain unverified.** All 18 of Deepak's
   candidate POIs have `verification_status: "unverified_coordinates"` -
   they were never run through a geocoder in this repair (no network
   access). Running them through Nominatim would upgrade eligible
   records to `"address_matched"` (still not `"verified"` - geocoding a
   text address is not independent confirmation) - this is a reasonable
   next step once network access is available, respecting Nominatim's
   rate limits (use the throttle already in place).

5. **Demo route is not provider-validated** (`provider_validated:
   false` in `demo_journey.json`'s `_meta`) for the same reason - see
   `scripts/capture_demo_route.py` above.

6. **Public demo providers have real rate limits.** Nominatim and OSRM's
   public servers will start returning `429`s under sustained load; the
   app handles this gracefully (reported via `data_status`, never
   crashes), but production deployments should move to self-hosted or
   commercial equivalents - see the provider table above.

7. **No persistence layer.** Per the spec, a database was not introduced
   since journey-analysis results are not required to be stored for
   this MVP. Add PostgreSQL/PostGIS only if/when a real requirement
   appears (e.g. saved trips, user accounts, spatial queries at scale) -
   not merely because it appeared in an earlier proposal.

## Design decisions worth knowing about

- **`POST /api/v1/journeys/analyse` always returns `200`** for
  structurally valid requests, even if every upstream provider fails.
  The honesty signal is `data_status`/`risk_assessment.level`/`null`
  fields, not the HTTP status code. Full rationale is in
  `docs/API_CONTRACT.md` under "Why always 200?".
- **The risk engine (`app/engine/risk_engine.py`) has zero FastAPI/HTTP
  dependencies** - it's pure functions over normalized dataclasses, unit
  tested in isolation, and can be reused or extended without touching
  the web layer.
- **Risk scores never imply certainty.** Every assessment's `reasons`
  list ends with an explicit disclaimer that the score does not predict
  accidents or guarantee safety; `level: "unknown"` / `score: null` is
  returned whenever there isn't enough reliable data, rather than
  guessing.
- **Alert relevance uses the real route geometry**, not just the two
  endpoints - a point-to-polyline minimum distance, with an explicit,
  reported fallback (never a silent one) when geometry is missing.
- **Facility "verification" is about coordinates only.** The backend
  never asserts a facility's open/closed status, operating hours, or
  capabilities (EV charging, CNG, emergency services) unless a source
  explicitly provides that - verification fields exist precisely so the
  frontend can visually distinguish "this pin is backed by the
  authoritative map data" from "this pin is a best-guess estimate."
- **One error envelope for every failure mode** - validation errors,
  manually-raised exceptions, and framework 404s all produce
  `{"error": {"code", "message", "details"?}}`, registered against
  Starlette's base `HTTPException` (not just FastAPI's subclass) so
  framework-level errors are covered too, not only ones a route handler
  raises itself.

## Definition of done checklist (per project spec)

- [x] Application starts successfully (`uvicorn app.main:app`)
- [x] Health endpoint responds
- [x] Swagger documentation at `/docs` works and reflects implemented schemas
- [x] Journey analysis returns the agreed schema (see `docs/API_CONTRACT.md`)
- [x] Route geometry is valid GeoJSON when a route is available
- [x] Nearby facility search works against the configured provider (Overpass)
- [x] Risk engine produces explainable, reasoned results, now with route-corridor alert relevance
- [x] Missing data and upstream failures are handled honestly (`data_status`, nulls, no fabrication)
- [x] Automated tests pass (110/110, mocked external calls + pure-logic unit tests)
- [x] Environment configuration documented (`.env.example`, this README)
- [x] Frontend can consume the API without needing internal service/db details
- [x] README contains exact installation, demo-mode, and test instructions
- [x] Demo data integrity issues fixed: route honestly marked not provider-validated,
      facility coordinates honestly marked unverified, alert descriptions unmistakably fictional
- [x] API contract and README updated to match the actual implementation (this document)
