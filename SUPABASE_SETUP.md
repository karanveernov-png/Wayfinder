# Supabase Setup Guide for Saved Journeys

If you see **"Invalid token"** or **401 Unauthorized** errors when trying to save journeys, follow these steps:

---

## Step 1: Create the Database Table

1. Go to your Supabase Dashboard: https://supabase.com/dashboard/project/[your-project]
2. Click **SQL Editor** in the left sidebar
3. Copy and paste the contents of `backend/supabase/schema.sql`
4. Click **Run**
5. Verify by running: `SELECT * FROM saved_journeys;` — it should return an empty result set without errors

---

## Step 2: Configure JWT Secret

The JWT secret in `backend/.env` must match what Supabase uses to sign tokens:

1. In Supabase Dashboard, go to **Settings** → **API**
2. Scroll down to **JWT Settings** section
3. Copy the **JWT Secret** value
4. Paste it into `backend/.env`:
   ```env
   SUPABASE_JWT_SECRET=<paste-your-jwt-secret-here>
   ```

**Important:** This is NOT your anon key or service role key. It's specifically the JWT signing secret found in the "JWT Settings" subsection.

---

## Step 3: Restart the Backend

After updating `.env`, restart your backend:

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

---

## Step 4: Verify Frontend Auth

Make sure your frontend is correctly configured in `frontend/.env`:

```env
VITE_SUPABASE_URL=https://wxmvhqjxrseamshacynj.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_4AKX3PMV6DfkKRqh_krBlQ_M5VdRmjf
```

Then reload the frontend page. You should no longer see "Invalid token" errors.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| "Invalid token" | JWT secret mismatch | Re-copy JWT secret from Supabase Dashboard → Settings → API → JWT Settings |
| 401 on `/saved-journeys` | User not logged in | Sign in through the app's login page first |
| Table doesn't exist | Schema not run | Run `backend/supabase/schema.sql` in Supabase SQL Editor |
| CORS error | Backend not running | Ensure backend is running on port 8000 |

---

## What This Does

Once configured, users can:
- **Save** routes they plan (stored per-user in Supabase)
- **View** their saved journeys in the sidebar
- **Delete** old journeys they no longer need
- All data is private — users only see their own saved trips
