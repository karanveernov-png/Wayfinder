/**
 * Regression test for a startup crash: src/lib/supabase.js used to call
 * createClient(import.meta.env.VITE_SUPABASE_URL, ...VITE_SUPABASE_ANON_KEY)
 * unconditionally at module scope. @supabase/supabase-js's createClient()
 * throws synchronously ("supabaseUrl is required.") when either argument is
 * missing/undefined — and this module sits at the top of the import chain
 * (main.jsx -> App.jsx -> AuthContext.jsx -> here), evaluated before React
 * ever mounts, so the throw crashed the whole bundle: a blank white page,
 * uncatchable by <ErrorBoundary> (which only catches errors from its own
 * children, not errors thrown while importing modules before anything
 * renders).
 *
 * Running this file under plain Node (no Vite) reproduces exactly that
 * missing-configuration condition, because import.meta.env is undefined
 * outside Vite — the same as a real deployment that forgot to set
 * VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY. Before the fix (optional
 * chaining + a guarded createClient call), importing this module here
 * would throw and this whole test file would fail to run at all.
 *
 * Run with: node --test tests/supabase.test.js
 */

import assert from "node:assert";
import { test } from "node:test";

test("supabase.js imports cleanly with no VITE_* config, and reports itself unconfigured", async () => {
  const mod = await import("../src/lib/supabase.js");
  assert.strictEqual(mod.isSupabaseConfigured, false);
  assert.strictEqual(mod.supabase, null);
});
