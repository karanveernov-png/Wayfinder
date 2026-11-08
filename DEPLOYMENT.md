# Waymark — Deployment Guide
> Deploy to **Render.com** free tier using Docker + Supabase (already set up).
> All external APIs are keyless — no extra service accounts needed.

---

## Architecture (what you're deploying)

```
┌──────────────┐    HTTPS     ┌──────────────┐
│   Browser    │ ◄──────────► │  Frontend    │  (nginx serving React SPA)
│              │              │  container   │
└──────────────┘              └──────┬───────┘
                                     │ /api/v1/*
                                    ▼
                            ┌──────────────┐
                            │  Backend     │  (FastAPI on :8000)
                            │  container   │
                            └──────┬───────┘
                                   │
                      ┌────────────┼────────────┐
                      ▼            ▼            ▼
                 Nominatim    OSRM/Overpass  Open-Meteo / EONET
               (geocoding)  (routing/facility) (weather/alerts)
                           🆓 all free, no keys
                             ▲
                     ┌───────┴───────┐
                     │  Supabase     │  ← auth + saved journeys
                     │  (managed)    │     already configured ✅
                     └───────────────┘
```

---

## Pre-deploy checklist

Run these locally first to catch issues before they hit production:

```bash
cd D:\RDBMS project
make test          # 72 frontend + 174 backend tests (1 pre-existing Groq flake — ignore)
make build         # verify frontend builds cleanly
docker compose up --build   # smoke-test the full stack end-to-end
```

If local docker-compose works, production will too.

---

## Step 1 — Prepare your environment variables

```powershell
# Copy the template and fill in real values
Copy-Item .env.production.template .env.production
notepad .env.production
```

**Required fields to fill:**

| Variable | Where to get it |
|----------|----------------|
| `SUPABASE_JWT_SECRET` | Supabase Dashboard → Settings → API → JWT Settings (**NOT** anon key) |
| `VITE_API_BASE_URL` | Will become `https://your-backend.onrender.com/api/v1` after deploy |
| `CORS_ORIGINS` | Will become `https://your-app.onrender.com` after deploy |
| `HTTP_USER_AGENT` | Your real email or project URL (Nominatim policy) |
| `GROQ_API_KEY` | Optional — leave blank to disable AI trip-planning feature |

---

## Step 2 — Create a new Git repo (required by Render)

```bash
git init
git add -A
git commit -m "Initial commit — Waymark v1"
git remote add origin https://github.com/YOU/waymark.git
git push -u origin main
```

**Important**: your `.gitignore` must exclude `.env` files:
```
.env
.env.production
backend/.env
frontend/.env
```

---

## Step 3 — Deploy to Render (free tier, no credit card)

### A. Backend service
1. Go to [dashboard.render.com](https://dashboard.render.com) → **New** → **Web Service**
2. Connect your GitHub repo
3. Configure:
   - **Name**: `waymark-api`
   - **Region**: closest to your users
   - **Branch**: `main`
   - **Root Directory**: `/`
   - **Build Command**: `cd backend && pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: **Free** (wakes on first request, ~30s cold start)
4. Add Environment Variables from `.env.production`:
   - Set each variable manually (copied from `.env.production`, not uploaded as file)
5. Click **Create Web Service**

Wait ~3 minutes. Note the generated URL: `https://waymark-api.onrender.com`

### B. Frontend service
1. In the same dashboard → **New** → **Static Site**
2. Connect the same repo
3. Configure:
   - **Name**: `waymark-web`
   - **Build Command**: 
     ```
     cd frontend && npm ci && \
     VITE_API_BASE_URL=https://waymark-api.onrender.com/api/v1 \
     VITE_SUPABASE_URL=https://wxmvhqjxrseamshacynj.supabase.co \
     VITE_SUPABASE_ANON_KEY=<your-anon-key> \
     VITE_MAPTILER_API_KEY=9WEe8nFrM1GLkL6Wi7PV \
     npm run build
     ```
   - **Publish Directory**: `frontend/dist`
   - **Instance Type**: **Free**
4. Click **Create Static Site**

Note its URL: `https://waymark-web.onrender.com`

### C. Update CORS on the backend
After both services are live, go back to your backend service's **Environment** tab and update:
```
CORS_ORIGINS=https://waymark-web.onrender.com
```
Save and restart the backend. That's it — your front-end is now whitelisted.

---

## Step 4 — Final setup in Supabase

Open [Supabase SQL Editor](https://supabase.com/dashboard/project/wxmvhqjxrseamshacynj/editor):

```sql
-- Run this once to enable saved journeys for all logged-in users
\i backend/supabase/schema.sql
```

(Or copy-paste the contents of `backend/supabase/schema.sql` into the editor and run.)

This creates the `saved_journeys` table and RLS policies. Without it, save/journey features return 404.

---

## Known limitations (freemium trade-offs)

| Limitation | Impact | Workaround |
|------------|--------|-----------|
| Backend free tier goes idle after 30 min no traffic | First request takes ~30s to wake | Add a lightweight keep-alive cron (a $5/tier upgrade) or accept occasional first-request latency |
| No persistent disk between restarts | OK — we don't store anything locally | Already safe; all data lives in Supabase |
| Cold-start latency | ~5–10s on first page load per user | Acceptable for personal/hobby use |

---

## Alternative platforms

| Platform | Free Tier | Notes |
|----------|-----------|-------|
| **Render** | ✅ Best fit | Simplest setup, native Docker support, free Postgres optional |
| **Railway** | $5 monthly credit | Very developer-friendly, but requires payment method |
| **Fly.io** | Small free allowance | Requires `flyctl` CLI, more config overhead |
| **Vercel + API Routes** | Generous | Split frontend here, move backend to separate platform |

---

## Troubleshooting

**Saved journeys returning 401 "Invalid token"**
→ Check that `SUPABASE_JWT_SECRET` matches exactly what's in Supabase Dashboard → Settings → API → JWT Settings (trailing `==` matters!)

**Frontend shows "App is not configured"**
→ Verify `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` were baked into the frontend build at compile time (passed as build args, not runtime env vars)

**CORS errors in browser console**
→ Ensure `CORS_ORIGINS` on the backend includes the **exact** frontend URL (including `https://`)

**Route shows "Demo data" forever**
→ Backend can't reach `router.project-osrm.org`. This is expected on some network-restricted environments. The demo path still works fine for testing.
