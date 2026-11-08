import { Settings } from "lucide-react";

/**
 * Shown instead of the app when required build-time configuration
 * (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY) is missing. Without this,
 * the Supabase client constructor throws during module evaluation — before
 * React mounts and before <ErrorBoundary> exists to catch anything — which
 * previously produced a blank white page with only a console error. This
 * runs instead of the app in that case, so a misconfigured deployment (a
 * forgotten environment variable on the hosting platform, most commonly)
 * is immediately obvious instead of looking like the site is simply down.
 */
export default function ConfigErrorScreen({ missing }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f7f8fa] p-5 sm:p-8">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-amber-50 text-amber-600">
          <Settings size={26} />
        </div>
        <h2 className="mt-5 text-lg font-semibold">App is not configured</h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          This deployment is missing required environment variables, so
          authentication and saved journeys cannot start.
        </p>
        <div className="mt-4 rounded-lg bg-slate-50 p-3 text-left text-xs text-slate-600">
          <p className="font-medium">Missing:</p>
          <ul className="mt-1.5 list-inside list-disc space-y-0.5">
            {missing.map((name) => (
              <li key={name} className="font-mono">{name}</li>
            ))}
          </ul>
        </div>
        <p className="mt-4 text-xs text-slate-400">
          Set these in the hosting platform's environment configuration
          (see frontend/.env.example), then rebuild and redeploy.
        </p>
      </div>
    </div>
  );
}
