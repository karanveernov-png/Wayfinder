# Waymark — Travel Intelligence for Better Journeys

> Plan any trip with live routing, nearby facilities, weather, natural-hazard alerts, and an explainable risk assessment — all from one link you can share directly to Google Maps.

---

## Features

| Feature | Details |
|---------|---------|
| **Route Planning** | Origin → destination routing via OSRM (driving, cycling, transit, two-wheeler). Click on the map or type place names. |
| **Risk Assessment** | Rule-based score (0–100) with human-readable reasons covering weather, alert severity, and route geometry proximity. Never guesses — `"unknown"` is reported when data is insufficient. |
| **Nearby Facilities** | Hospitals, fuel stations, restaurants, rest stops found along the route corridor (Up to 70 km radius, sampled at origin / midpoint / destination). |
| **Live Alerts** | Natural-hazard events from NASA EONET — wildfires, storms, floods, volcanoes, landslides, earthquakes. Route-corridor aware (mid-route alerts are detected even if they're far from both endpoints). |
| **Weather Samples** | Temperature, wind, WMO code at up to 3 points along the route via Open-Meteo. |
| **Elevation Profile** | Interactive chart over the full route polyline. |
| **Share as Link** | One tap opens the route in [Google Maps](https://www.google.com/maps/dir/), ready to navigate on the receiver's phone. Or copy the URL. Works offline-friendly (PWA-ready). |
| **AI Trip Intent** | Describe your trip in plain English — *"Plan a scenic drive from Delhi to Shimla, show me pharmacies"* — and get a structured journey back via Groq + GPT-OSS-20B. |
| **Saved Journeys** | Sign up, save trips to the cloud (Supabase auth), access them anywhere you're logged in. Hybrid localStorage + Supabase sync works offline too. |
| **Offline Demo** | Chandigarh → Ludhiana corridor runs fully offline — no API keys, no internet. `demo: true` flag exercises the full pipeline against stored data. |
| **Dark Basemap** | CARTO Dark Matter tiles by default; Esri Light Gray Canvas fallback available. |

---

## Tech Stack

```
┌──────────────────────────────────────────────────────┐
│ Frontend (React 19 · Vite · Tailwind · Leaflet)    │
│  - PWA with service-worker caching                  │
│  - Supabase auth + saved journeys                   │
│  - Google Maps deep-link sharing                    │
└───────────────────────────┬──────────────────────────┘
                            │ REST (FastAPI + Pydantic v2)
┌───────────────────────────▼──────────────────────────┐
│ Backend (Python 3.12 · FastAPI · uvicorn)           │
│  - Journey analysis: geocode → route → sample → assess
│  - Deterministic risk engine (no ML weights)         │
│  - All external calls wrapped with honest degradation │
└───────────────────────────┬──────────────────────────┘
                            │ managed Postgres
┌───────────────────────────▼──────────────────────────┐
│ Supabase (auth · JWT validation · saved_journeys)   │
└──────────────────────────────────────────────────────┘
```

### External APIs used (all free/keyless by default)

| Service | What it provides | Key required? |
|---------|-----------------|---------------|
| [Nominatim](https://nominatim.org/) | Geocoding (place name → coordinates) | No, but requires a real User-Agent header |
| [OSRM Demo](https://project-osrm.org/) | Routing & distance/duration | No (fair-use only; use self-hosted for production) |
| [Overpass API](https://overpass-api.de/) | Nearby POIs from OpenStreetMap | No |
| [Open-Meteo](https://open-meteo.com/) | Weather forecasts | No (non-commercial) |
| [NASA EONET](https://eonet.gsfc.nasa.gov/) | Live natural-hazard alerts | No |
| [Groq](https://groq.com/) (optional) | AI trip-planning via LLM | Yes — `GROQ_API_KEY` in backend `.env` |
| [CARTO](https://carto.com/) (default basemap) | Map tile layer | No |

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node 20+

### Run locally (two terminals)

**Terminal 1 — Backend:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # defaults work out of the box
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Then open **[http://localhost:5173](http://localhost:5173)**. The frontend proxies all `/api/v1/*` requests to the backend.

---

## Development Commands

```bash
# From project root
# Backend
cd backend && python -m pytest tests/ -v        # run backend tests
cd backend && ruff check .                      # lint backend

# Frontend
cd frontend && npm test                         # run frontend tests
cd frontend && npm run build                    # production build
cd frontend && npm run lint                     # lint frontend
```

### Test results (commit-verified)

| Suite | Tests | Passing | Notes |
|-------|-------|---------|-------|
| Frontend (`tests/*.test.js`) | 72 | 72 ✅ | Geo helpers, format utils, API client, location suggestions, Supabase init |
| Backend (`pytest`) | 175 | 174 ✅ / 1 ⚠️ | 1 pre-existing flake in `test_trip_intent.py::test_plan_trip_reports_not_configured_when_no_api_key` (string-matches outdated error message); unaffected by this change |

All backend tests mock every external HTTP call via [`respx`](https://lukeneff.github.io/respx/) — the suite never touches a network or needs API keys.

---

## Deployment

The project is deployed across two hosting platforms:

- **Backend** → [SnapDeploy](https://snapdeploy.com) (managed container hosting)
- **Frontend** → [Vercel](https://vercel.com) (static + serverless)

### Architecture for production

```
User Browser ──HTTPS──► Vercel (Frontend - static React SPA)
                         ▲
                         │ fetches /api/v1/*
                         ▼
              SnapDeploy (Backend - FastAPI)
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         Nominatim   Overpass    Open-Meteo/EONET
         (free)      (free)      (free)
              │
              ▼
         Supabase Cloud
      (auth + postgres)
```

---

### Backend — SnapDeploy

The backend is a FastAPI service (Python 3.12) deployed to SnapDeploy as a container. SnapDeploy provides:

- **Zero-downtime deployments** on git push
- **Automatic HTTPS + custom domain**
- **Managed scaling** (no cold start)
- **Automatic PORT injection** (containers receive `$PORT`)

**Deploy steps:**

1. Push the `backend/` directory to your SnapDeploy git repository (or configure the SnapDeploy panel to point at `backend/`).
2. Set the following environment variables in the SnapDeploy dashboard:

| Variable | Required | Notes |
|----------|----------|-------|
| `APP_ENV` | ✅ | `production` |
| `PORT` | ✅ | `8000` (SnapDeploy injects this automatically) |
| `HTTP_USER_AGENT` | ✅ | Real email/project URL (Nominatim policy) |
| `SUPABASE_URL` | ✅ | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | ✅ | Supabase anon/publishable key |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Supabase service role key |
| `SUPABASE_JWT_SECRET` | ✅ | Copy from Supabase Dashboard → Settings → API → JWT Settings |
| `CORS_ORIGINS` | ✅ | Your Vercel frontend URL (e.g. `https://your-app.vercel.app`) |
| `GROQ_API_KEY` | Optional | For AI trip intent feature |

3. After deployment, note your backend public URL (e.g. `https://your-backend.snapdeploy.app`).

---

### Frontend — Vercel

The frontend is a Vite + React SPA deployed to Vercel. `frontend/vercel.json` already configures the build, output directory, SPA rewrites, and caching headers.

**Deploy steps:**

1. Push the `frontend/` directory to a Vercel-connected git repository (or use `vercel --prod` from the `frontend/` directory).
2. Set the following environment variables in Vercel → Project → Settings → Environment Variables:

| Variable | Required | Notes |
|----------|----------|-------|
| `VITE_API_BASE_URL` | ✅ | Your SnapDeploy backend URL + `/api/v1` |
| `VITE_SUPABASE_URL` | ✅ | Your Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | ✅ | Supabase anon/publishable key |
| `VITE_MAPTILER_API_KEY` | ✅ | MapTiler API key |

> **Note**: Vite bakes `VITE_*` variables in at **build time**. After changing any of them, trigger a fresh deployment (redeploy) so the new values take effect.

3. After deployment, note your frontend public URL (e.g. `https://your-app.vercel.app`) and set it as `CORS_ORIGINS` on the backend (SnapDeploy dashboard).

---

### Verify & Connect

1. Open your Vercel frontend URL.
2. Test route planning: enter origin/destination → "Plan journey".
3. Test share: click "Open in Google Maps" → opens Google Maps with route.
4. Test auth: sign up → save a journey → verify in Supabase dashboard.

---

### Database Setup (run once)

```bash
# In Supabase SQL Editor, run:
\i backend/supabase/schema.sql
```

---

## Project Structure

```
waymark/
├── backend/                       # Wayfinder API
│   ├── app/
│   │   ├── main.py               # FastAPI app, CORS, lifespan client, error handlers
│   │   ├── api/
│   │   │   ├── routes/           # health, journeys, facilities, weather, alerts, locations
│   │   │   └── deps.py           # FastAPI dependency providers (settings, HTTP client)
│   │   ├── schemas/              # Pydantic request/response models
│   │   ├── services/             # External provider integrations
│   │   │   ├── routing.py        # geocoding + Bhuvan/OSRM routing
│   │   │   ├── facilities.py     # Overpass nearby search
│   │   │   ├── weather.py        # Open-Meteo
│   │   │   ├── alerts.py         # NASA EONET
│   │   │   └── demo.py           # loads & validates stored demo data
│   │   ├── engine/
│   │   │   └── risk_engine.py    # deterministic rule-based scoring (no FastAPI dep)
│   │   └── core/
│   │       └── config.py         # environment-driven settings with startup checks
│   ├── docs/API_CONTRACT.md      # authoritative request/response contract
│   ├── scripts/capture_demo_route.py   # generates fresh demo route from live providers
│   ├── supabase/schema.sql       # run once to enable saved journeys
│   └── tests/                    # pytest suite (mocked)
│
├── frontend/                      # Waymark UI
│   ├── src/
│   │   ├── pages/                # Overview, TripPlanner, NearbyPlaces, SavedJourneys…
│   │   ├── components/
│   │   │   ├── journey/          # ShareJourneyButton, RiskPanel, FacilityList…
│   │   │   ├── layout/           # AppLayout, SidebarProfile
│   │   │   └── map/              # MapView (Leaflet), GlobeMapView
│   │   ├── context/              # JourneyContext, AuthContext
│   │   └── lib/                  # api.js, format.js, geo.js, storage.js
│   ├── public/                   # favicons, PWA icons
│   ├── vercel.json               # Vercel deployment config
│   └── tests/                    # node --test suite
│
├── .gitignore                    # git ignore rules
└── README.md                     # this file
```

---

## Design Decisions Worth Knowing

- **`POST /api/v1/journeys/analyse` always returns `200`** for valid requests, even when providers fail. Honesty comes through `data_status.mode`, `risk_assessment.level`, and `null` fields — not the HTTP status code.
- **Risk scores carry disclaimers.** Every response's `reasons` ends with "does not predict accidents." When there isn't enough data, level is `"unknown" / score null` — never guessed low.
- **Alert relevance uses full route geometry**, not just endpoints. A mid-route hazard is correctly flagged even when it sits 40 km from both origin and destination. Falls back gracefully with an explicit notice when geometry is missing.
- **Facility verification is coordinate-only.** We never assert whether a hospital is open, has CNG, or offers emergency services unless a source explicitly says so. The frontend should visually distinguish verified vs. unverified pins (done).
- **One error envelope for everything.** Validation errors, manual exceptions, and framework-level 404s all return `{"error": {"code", "message", "details?"}}`.
- **Share links use coordinates whenever available.** They resolve more reliably in Google Maps than text place names. Falls back to display names only when coordinates are missing (demo mode).

---

## Known Limitations

1. **Alerts cover natural hazards, not traffic/road closures.** NASA EONET is a genuinely useful feed for its domain; no free, keyless road-closure source was identified at build time. If one appears, extending `alerts.py` is scoped to a single service module.
2. **Public demo providers are rate-limited.** Nominatim ~1 req/s; OSRM fair-use only. Production deployments should use self-hosted instances or commercial alternatives. All provider URLs are environment-configurable.
3. **Route sampling is bounded.** Facilities and weather are checked at up to 3 points (origin, approximate midpoint, destination). Wide corridors between samples aren't covered. Documented in the contract — never presented as exhaustive.
4. **Demo data is intentionally imperfect.** Stored distances, durations, and facility coords are estimates (clearly labeled). Use `scripts/capture_demo_route.py` after gaining network access to replace them with real provider data.
5. **No SQLite/Postgres in the backend itself.** Persists nothing locally; all state lives in Supabase (for saved journeys) or in the ephemeral process. This is intentional — keeps the container lightweight and horizontally scalable. Add a database only when a persistence requirement emerges.

---

## License

MIT. Built during an academic project (RDBMS course, Panjab University, 2026).