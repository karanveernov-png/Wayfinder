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
- (Optional) Docker + Docker Compose

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

### Run with Docker (single command)

```bash
docker compose up --build
```

Starts the backend on `:8000` and the frontend on `:5173`. Edit `backend/.env` first to set a real `HTTP_USER_AGENT` and your Supabase credentials before going beyond localhost.

---

## Development Commands

```bash
# From project root
make help          # list all commands
make test          # run all frontend + backend tests
make build         # production frontend build
make lint          # ruff check backend
make docker-up     # docker compose up --build
make docker-down   # docker compose down
```

### Test results (commit-verified)

| Suite | Tests | Passing | Notes |
|-------|-------|---------|-------|
| Frontend (`tests/*.test.js`) | 72 | 72 ✅ | Geo helpers, format utils, API client, location suggestions, Supabase init |
| Backend (`pytest`) | 175 | 174 ✅ / 1 ⚠️ | 1 pre-existing flake in `test_trip_intent.py::test_plan_trip_reports_not_configured_when_no_api_key` (string-matches outdated error message); unaffected by this change |

All backend tests mock every external HTTP call via [`respx`](https://lukeneff.github.io/respx/) — the suite never touches a network or needs API keys.

---

## Deployment to Google Cloud Run

Both services are containerized and ready for Cloud Run. Cloud Run provides:
- **Free tier**: 2M requests/month, 360M vCPU-seconds, 180K GiB-seconds
- **Auto-scaling to zero** (no cold billing)
- **Built-in HTTPS + custom domains**
- **Automatic PORT injection** (containers receive `$PORT`)

### Architecture for production

```
User Browser ──HTTPS──► Cloud Run (Frontend Service)
                         ▲
                         │ fetches /api/v1/*
                         ▼
              Cloud Run (Backend Service)
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

### Prerequisites

```bash
# Install gcloud CLI and set up
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth configure-docker

# Enable required APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

---

### 1. Create Artifact Registry Repository

```bash
gcloud artifacts repositories create waymark \
  --location=us-central1 \
  --repository-format=docker
```

---

### 2. Build & Deploy Backend

```bash
cd backend

# Build and push image
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/waymark/backend:latest .

# Deploy to Cloud Run
gcloud run deploy waymark-backend \
  --image=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/waymark/backend:latest \
  --platform=managed \
  --region=us-central1 \
  --allow-unauthenticated \
  --port=8000 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10 \
  --set-env-vars="APP_ENV=production,HTTP_USER_AGENT=Waymark/1.0 (your-email@domain.com),SUPABASE_URL=https://your-project.supabase.co,SUPABASE_ANON_KEY=your-anon-key,SUPABASE_SERVICE_ROLE_KEY=your-service-key,SUPABASE_JWT_SECRET=your-jwt-secret,CORS_ORIGINS=https://your-frontend-xxxx-uc.a.run.app"
```

**Note**: After frontend deploy, update `CORS_ORIGINS` with the actual frontend URL:
```bash
gcloud run services update waymark-backend \
  --region=us-central1 \
  --set-env-vars="CORS_ORIGINS=https://YOUR_FRONTEND_URL.a.run.app"
```

---

### 3. Build & Deploy Frontend

```bash
cd frontend

# Build and push image (pass build args for Vite env vars)
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/waymark/frontend:latest \
  --substitutions=_VITE_API_BASE_URL=https://waymark-backend-xxxx-uc.a.run.app/api/v1,_VITE_SUPABASE_URL=https://your-project.supabase.co,_VITE_SUPABASE_ANON_KEY=your-anon-key,_VITE_MAPTILER_API_KEY=your-maptiler-key .

# Deploy to Cloud Run
gcloud run deploy waymark-frontend \
  --image=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/waymark/frontend:latest \
  --platform=managed \
  --region=us-central1 \
  --allow-unauthenticated \
  --port=8080 \
  --memory=256Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10
```

**Important**: Replace `waymark-backend-xxxx-uc.a.run.app` with your actual backend Cloud Run URL from step 2.

---

### 4. Verify & Connect

1. Open your frontend URL (e.g., `https://waymark-frontend-xxxx-uc.a.run.app`)
2. Test route planning: enter origin/destination → "Plan journey"
3. Test share: click "Open in Google Maps" → opens Google Maps with route
4. Test auth: sign up → save a journey → verify in Supabase dashboard

---

### Environment Variables Reference

| Variable | Required | Where | Notes |
|----------|----------|-------|-------|
| `SUPABASE_JWT_SECRET` | ✅ | Backend | Copy from Supabase Dashboard → Settings → API → JWT Settings |
| `HTTP_USER_AGENT` | ✅ | Backend | Real email/project URL (Nominatim policy) |
| `CORS_ORIGINS` | ✅ | Backend | Frontend Cloud Run URL |
| `VITE_API_BASE_URL` | ✅ | Frontend (build arg) | Backend Cloud Run URL + `/api/v1` |
| `VITE_SUPABASE_URL` | ✅ | Frontend (build arg) | Your Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | ✅ | Frontend (build arg) | Supabase anon/publishable key |
| `VITE_MAPTILER_API_KEY` | ✅ | Frontend (build arg) | MapTiler API key |
| `GROQ_API_KEY` | Optional | Backend | For AI trip intent feature |

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
│   ├── Dockerfile                # Cloud Run compatible (uses $PORT)
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
│   ├── Dockerfile                # Cloud Run compatible (nginx + PORT)
│   ├── entrypoint.sh             # generates nginx.conf with $PORT
│   └── tests/                    # node --test suite
│
├── docker-compose.yml            # local development only
├── .env.production.template      # env var template
└── DEPLOYMENT.md                 # detailed deployment notes
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