import { createClient } from "@supabase/supabase-js";

// Optional chaining: Vite always provides import.meta.env as an object (so
// this is a no-op there), but import.meta.env is simply undefined under
// plain Node — which is how this module's own tests, and any test for a
// module that imports it (e.g. api.js), run (`node --test`, no Vite). An
// unguarded `.VITE_SUPABASE_URL` access crashed the import itself in that
// environment, which is why api.js previously had no real unit tests at
// all (see tests/api.test.js).
const SUPABASE_URL = import.meta.env?.VITE_SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env?.VITE_SUPABASE_ANON_KEY;

// createClient() throws synchronously ("supabaseUrl is required.") when
// either value is missing — and this module sits at the top of the import
// chain (main.jsx -> App.jsx -> AuthContext.jsx -> here), evaluated before
// React ever mounts. An unguarded createClient() call here previously
// crashed the whole bundle with an unhandled module-evaluation exception:
// a blank white page with nothing but a console error, which no
// <ErrorBoundary> further down the tree could catch (error boundaries only
// catch errors thrown by their own children during render/lifecycle/effects
// — not errors thrown while importing modules before anything renders).
// isSupabaseConfigured lets App.jsx show a clear configuration-error screen
// instead, before anything that depends on `supabase` mounts.
export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

if (!isSupabaseConfigured) {
  console.error(
    "Supabase is not configured: VITE_SUPABASE_URL and/or " +
      "VITE_SUPABASE_ANON_KEY are missing. Authentication and saved " +
      "journeys will be unavailable until these are set (see .env.example)."
  );
}

export const supabase = isSupabaseConfigured
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;