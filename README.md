# RouteVision + Wayfinder — Full-Stack App

This repo combines two already-paired projects into one runnable app:

- **`backend/`** — Wayfinder API (FastAPI + Pydantic v2 + HTTPX). Journey
  analysis combining routing, nearby facilities, weather, travel alerts,
  and a rule-based risk assessment.
- **`frontend/`** — RouteVision UI (React 19 + Vite + Tailwind + Leaflet).
  Consumes the Wayfinder API via the contract in
  `backend/docs/API_CONTRACT.md`.

They were built against the same contract, so no glue code was needed —
only wiring, verification, and packaging. Confirmed while assembling this
package:

- Backend: **91/91 tests pass** (`pytest`), no network access required.
- Backend demo endpoint (`POST /api/v1/journeys/analyse` with
  `"demo": true`) returns a full, valid response with no external calls.
- Frontend: **builds cleanly** (`npm run build`), and its API client
  (`src/lib/api.js`) already targets the backend's exact routes, request/
  response shapes, and error envelope.
- CORS on the backend (`http://localhost:5173`) and `VITE_API_BASE_URL`
  on the frontend (`http://localhost:8000/api/v1`) already match for
  local dev — no changes needed.

## Quick start (two terminals)

**Terminal 1 — backend:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # defaults work out of the box for local dev
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend:**
```bash
cd frontend
npm install
npm run dev
```

Then open **http://localhost:5173**. The frontend talks to the backend
at `http://localhost:8000/api/v1` (set in `frontend/.env`).

No API keys are required: routing, geocoding, facilities, weather, and
travel alerts (natural-hazard events via NASA EONET) all use free,
keyless providers by default. One optional upgrade needs a key: NASA
FIRMS active-fire detections. See "Travel alerts / NASA & ISRO APIs"
below for exactly which API to get and where to paste it. If you have no
network access, the UI's demo/offline path (`demo: true`) exercises the
full pipeline against stored Chandigarh → Ludhiana data — see
`backend/README.md`.

## Travel alerts / NASA & ISRO APIs

This is the piece that makes trip planning "real" end-to-end: without a
live alerts source, every journey analysis has to report alerts as
unavailable rather than invent data.

- **Works with zero setup — [NASA EONET](https://eonet.gsfc.nasa.gov/docs/v3).**
  Free, keyless, no account. Already set as the default
  `ALERT_PROVIDER_URL` in `backend/.env.example` / `backend/.env`. It
  covers ongoing natural-hazard events (wildfires, severe storms, floods,
  volcanoes, landslides, earthquakes, etc.) with real coordinates, pulled
  from NASA's own curated feed — not a traffic/road-closure service (no
  free one exists for this), but genuinely live hazard data near your
  route.
- **ISRO Bhuvan Shortest Path — optional primary routing provider.**
  Set `ISRO_BHUVAN_TOKEN` in `backend/.env` to enable it. Keep the token
  server-side. If it is missing/expired or Bhuvan returns an unusable
  route, the backend falls back to OSRM and the dashboard shows that the
  backup is in use. The public OSRM demo server is fair-use only; use a
  production routing provider for production availability.

Restart the backend after editing `.env` for changes to take effect.

## Quick start (Docker)

```bash
docker compose up --build
```

This starts the backend on `:8000` and a production build of the
frontend served on `:5173`. Edit `backend/.env` first if you want to
change provider URLs or set a real `HTTP_USER_AGENT` (required before
any serious Nominatim traffic — see `backend/README.md`).

## Before deploying anywhere beyond local dev

Edit `backend/.env`:
- `HTTP_USER_AGENT` — the shipped value is a placeholder; Nominatim's
  usage policy requires a real contact.
- `CORS_ORIGINS` — add your deployed frontend's origin.
- `ISRO_BHUVAN_TOKEN` — optional; add the Bhuvan token here, not in
  `frontend/.env`.
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` —
  required for authentication and saved journeys. `SUPABASE_JWT_SECRET`
  is the project's JWT signing secret (Supabase dashboard → Project
  Settings → API → JWT Settings), **not** the anon or service-role key.
  Run `backend/supabase/schema.sql` once in the Supabase SQL editor
  before using saved journeys — the `saved_journeys` table does not
  exist until you do.

And `frontend/.env`:
- `VITE_API_BASE_URL` — point it at your deployed backend's `/api/v1`.
- `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` — required for
  authentication. If either is missing, the app now shows a clear
  "App is not configured" screen instead of a blank page.

## Project docs

- API contract: `backend/docs/API_CONTRACT.md`
- Frontend TypeScript types matching the contract: `backend/docs/frontend-types.ts`
- Backend details, test report, known limitations: `backend/README.md`
- Frontend scaffold notes: `frontend/README.md`
