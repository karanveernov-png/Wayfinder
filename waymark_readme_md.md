# Waymark — Travel Intelligence for Better Journeys

> Plan any trip with live routing, nearby facilities, weather, natural-hazard alerts, and an explainable risk assessment — all from one link you can share directly to Google Maps.

---

## Features

| Feature | Details |
|---------|---------|
| **Route Planning** | Origin → destination routing via OSRM (driving, cycling, transit, two-wheeler). Click on the map or type place names. |
| **Risk Assessment** | Rule-based score (0–100) with human-readable reasons covering weather, alert severity, and route geometry proximity. Never guesses — `"unknown"` is reported when data is insufficient. |
| **Nearby Facilities** | Hospitals, fuel stations, restaurants, rest stops found along the route corridor (up to 70 km radius, sampled at origin / midpoint / destination). |
| **Live Alerts** | Natural-hazard events from NASA EONET — wildfires, storms, floods, volcanoes, landslides, earthquakes. Route-corridor aware (mid-route alerts are detected even if they are far from both endpoints). |
| **Weather Samples** | Temperature, wind, and WMO weather code at up to 3 points along the route via Open-Meteo. |
| **Elevation Profile** | Interactive chart over the full route polyline. |
| **Share as Link** | One tap opens the route in [Google Maps](https://www.google.com/maps/dir/), ready to navigate on the receiver's phone, or copy the URL. Works offline-friendly (PWA-ready). |
| **AI Trip Intent** | Describe your trip in plain English — *"Plan a scenic drive from Delhi to Shimla, show me pharmacies"* — and get a structured journey back via Groq + GPT-OSS-20B. |
| **Saved Journeys** | Sign up, save trips to the cloud (Supabase Auth), and access them anywhere you are logged in. Hybrid `localStorage` + Supabase sync works offline too. |
| **Offline Demo** | Chandigarh → Ludhiana corridor runs fully offline — no API keys, no internet. The `demo: true` flag exercises the full pipeline against stored data. |
| **Dark Basemap** | CARTO Dark Matter tiles by default; Esri Light Gray Canvas fallback available. |

---

## Tech Stack

```
┌──────────────────────────────────────────────────────┐
│ Frontend (React 19 · Vite · Tailwind · Leaflet)      │
│  - PWA with service-worker caching                   │
│  - Supabase auth + saved journeys                    │
│  - Google Maps deep-link sharing                     │
└───────────────────────────┬──────────────────────────┘
                            │ REST (FastAPI + Pydantic v2)
┌───────────────────────────▼──────────────────────────┐
│ Backend (Python 3.12 · FastAPI · uvicorn)            │
│  - Journey analysis: geocode → route → sample → assess│
│  - Deterministic risk engine (no ML weights)         │
│  - All external calls wrapped with honest degradation│
└───────────────────────────┬──────────────────────────┘
                            │ managed Postgres
┌───────────────────────────▼──────────────────────────┐
│ Supabase (auth · JWT validation · saved_journeys)    │
└──────────────────────────────────────────────────────┘
```

### External APIs Used (All Free / Keyless by Default)

| Service | What it provides | Key required? |
|---------|-----------------|---------------|
| [Nominatim](https://nominatim.org/) | Geocoding (place name → coordinates) | No, but requires a real `HTTP_USER_AGENT` header |
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

### Run Locally (Two Terminals)

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
# Backend
cd backend && python -m pytest tests/ -v        # run backend tests
cd backend && ruff check .                      # lint backend

# Frontend
cd frontend && npm test                         # run frontend tests
cd frontend && npm run build                    # production build
cd frontend && npm run lint                     # lint frontend
```

### Test Results (Commit-Verified)

| Suite | Tests | Passing | Notes |
|-------|-------|---------|-------|
| Frontend (`tests/*.test.js`) | 72 | 72 ✅ | Geo helpers, format utils, API client, location suggestions, Supabase init |
| Backend (`pytest`) | 175 | 174 ✅ / 1 ⚠️ | 1 pre-existing flake in `test_trip_intent.py::test_plan_trip_reports_not_configured_when_no_api_key` (string-matches outdated error message) |

All backend tests mock every external HTTP call via [`respx`](https://lukeneff.github.io/respx/) — the suite never touches a network or needs API keys.

---

## Production Deployment

The application is deployed across two hosting platforms:

- **Backend** → [Render](https://render.com) (Python Web Service)
- **Frontend** → [Vercel](https://vercel.com) (Static Vite + React SPA)

### Production Architecture

```
User Browser ──HTTPS──► Vercel (Frontend - static React SPA)
                         ▲
                         │ fetches /api/v1/*
                         ▼
              Render (Backend - FastAPI)
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

### 1. Backend — Render

The backend runs as a Python 3.12 Web Service on Render from the `backend/` subdirectory.

- **Automatic deploys** on git push to `main`
- **Automatic HTTPS** (`*.onrender.com`)
- **Free tier**: ~750 free hours/month; spins down after idle (~30–50s cold start on first request)
- **Automatic `$PORT` injection**

**Deploy Steps:**

1. Log in to [dashboard.render.com](https://dashboard.render.com) and click **New +** → **Web Service**.
2. Connect your GitHub repository (`Wayfinder`) and configure these build settings:

| Setting | Value |
|---------|-------|
| **Language** | `Python 3` |
| **Branch** | `main` |
| **Root Directory** | `backend` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

3. Open the **Environment** tab and set the following environment variables:

| Variable | Required | Example / Notes |
|----------|----------|-----------------|
| `PYTHON_VERSION` | ✅ | `3.12.8` *(prevents Render from defaulting to Python 3.14 where `pydantic-core` has no prebuilt wheel)* |
| `APP_ENV` | ✅ | `production` |
| `HTTP_USER_AGENT` | ✅ | `wayfinder-backend/0.1 (your-email@example.com)` *(required by Nominatim usage policy)* |
| `CORS_ORIGINS` | ✅ | `https://wayfinder-mauve.vercel.app,http://localhost:5173` *(comma-separated, no trailing slashes)* |
| `SUPABASE_URL` | ✅ | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | ✅ | Supabase anon/publishable key |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Supabase service role key |
| `SUPABASE_JWT_SECRET` | ✅ | Supabase Dashboard → Project Settings → API → JWT Settings |
| `GROQ_API_KEY` | Optional | Enables AI natural-language trip intent |

4. Click **Deploy web service** and note your backend URL (e.g., `https://wayfinder-backend-fypx.onrender.com`).

---

### 2. Frontend — Vercel

The frontend is a Vite + React SPA deployed to Vercel. `frontend/vercel.json` configures SPA rewrites and caching headers.

**Deploy Steps:**

1. Import the repository in [vercel.com](https://vercel.com) with **Root Directory** set to `frontend`.
2. Add the following variables in **Project → Settings → Environment Variables**:

| Variable | Required | Value / Notes |
|----------|----------|---------------|
| `VITE_API_BASE_URL` | ✅ | `https://wayfinder-backend-fypx.onrender.com/api/v1` *(must include `/api/v1` with no trailing slash)* |
| `VITE_SUPABASE_URL` | ✅ | Your Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | ✅ | Supabase anon/publishable key |
| `VITE_MAPTILER_API_KEY` | Optional | MapTiler API key (if using custom vector tiles) |

> **Important:** Vite embeds `VITE_*` variables at **build time**. Whenever you add or edit a `VITE_*` variable, open **Deployments → `...` → Redeploy** so the bundle rebuilds with the new value.

3. Confirm your live Vercel domain (e.g., `https://wayfinder-mauve.vercel.app`) matches the origin listed in `CORS_ORIGINS` on Render.

---

### 3. Database Setup (Run Once)

In your **Supabase SQL Editor**, execute:

```sql
\i backend/supabase/schema.sql
```

*(Or paste the contents of `backend/supabase/schema.sql` directly into the SQL Editor and click **Run**.)*

---

### 4. Verify Production Deployment

1. Check backend health directly: open `https://<your-render-service>.onrender.com/api/v1/health` and confirm a `200 OK` JSON response.
2. Open your Vercel frontend URL (`https://wayfinder-mauve.vercel.app`) and hard-refresh (`Ctrl + Shift + R`) to clear any cached service worker state.
3. Confirm the header status indicator shows the backend is connected (no `"Backend unreachable"` badge).
4. Test route planning (enter origin and destination → **Plan journey**), Google Maps sharing, and Supabase sign-in / saved journeys.

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
- **Risk scores carry disclaimers.** Every response's `reasons` ends with `"does not predict accidents."` When there isn't enough data, the level is `"unknown"` and score is `null` — never guessed low.
- **Alert relevance uses full route geometry**, not just endpoints. A mid-route hazard is correctly flagged even when it sits 40 km from both origin and destination. Falls back gracefully with an explicit notice when geometry is missing.
- **Facility verification is coordinate-only.** We never assert whether a hospital is open, has CNG, or offers emergency services unless a source explicitly says so. The frontend visually distinguishes verified vs. unverified pins.
- **One error envelope for everything.** Validation errors, manual exceptions, and framework-level 404s all return `{"error": {"code", "message", "details?"}}`.
- **Share links use coordinates whenever available.** They resolve more reliably in Google Maps than text place names, falling back to display names only when coordinates are missing (demo mode).

---

## Known Limitations

1. **Alerts cover natural hazards, not traffic/road closures.** NASA EONET is a reliable feed for natural events; no free, keyless road-closure source was identified at build time. Extending `alerts.py` is scoped to a single service module if one becomes available.
2. **Public demo providers are rate-limited.** Nominatim allows ~1 req/s and OSRM is fair-use only. Production deployments under heavier load should use self-hosted instances or commercial alternatives (all provider URLs are configurable via environment variables).
3. **Route sampling is bounded.** Facilities and weather are checked at up to 3 points (origin, approximate midpoint, destination), so wide corridors between samples aren't covered.
4. **Demo data is intentionally imperfect.** Stored distances, durations, and facility coordinates are estimates (clearly labeled). Run `scripts/capture_demo_route.py` with network access to refresh them from live providers.
5. **Stateless backend.** The FastAPI container persists nothing locally; all user state lives in Supabase (`saved_journeys`), keeping the Render service lightweight and horizontally scalable.

---

## License

MIT. Built during an academic project (RDBMS course, Panjab University, 2026).