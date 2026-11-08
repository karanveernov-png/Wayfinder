// frontend/src/components/journey/RouteComparisonPanel.jsx
//
// Calls POST /journeys/compare-routes and renders each alternate as an
// interactive card: hovering a card previews that route's geometry on the
// map immediately (via onPreviewRoute), clicking "pins" it so the preview
// survives after the mouse leaves — click the same card again to unpin.

import { useEffect, useState } from "react";
import { GitCompareArrows, Clock3, Route as RouteIcon, ShieldAlert, CloudSun, TriangleAlert, Loader2 } from "lucide-react";
import { compareRoutes } from "../../lib/api.js";
import { useAbortableRequest } from "../../hooks/useAbortableRequest.js";
import { riskStyle, formatDistance, formatDuration, weatherCodeLabel } from "../../lib/format.js";

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-xl border border-slate-200 bg-white p-4">
      <div className="h-3 w-24 rounded bg-slate-100" />
      <div className="mt-3 h-5 w-32 rounded bg-slate-100" />
      <div className="mt-4 h-4 w-full rounded bg-slate-100" />
      <div className="mt-2 h-4 w-3/4 rounded bg-slate-100" />
    </div>
  );
}

export default function RouteComparisonPanel({
  origin,
  destination,
  originCoordinates,
  destinationCoordinates,
  travelMode,
  onPreviewRoute,
}) {
  const run = useAbortableRequest();
  const [routes, setRoutes] = useState(null); // null = not yet compared
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hoverIndex, setHoverIndex] = useState(null);
  const [pinnedIndex, setPinnedIndex] = useState(null);

  const activeIndex = hoverIndex ?? pinnedIndex;

  useEffect(() => {
    if (!onPreviewRoute) return;
    const active = activeIndex != null ? routes?.[activeIndex] : null;
    onPreviewRoute(active?.geometry || null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex, routes]);

  // Clear any pinned preview if the panel unmounts mid-comparison (e.g.
  // the person navigates away) so a stale route doesn't linger on the map.
  useEffect(() => () => onPreviewRoute?.(null), [onPreviewRoute]);

  async function handleCompare() {
    setLoading(true);
    setError("");
    setRoutes(null);
    setPinnedIndex(null);

    const result = await run((signal) =>
      compareRoutes({ origin, destination, originCoordinates, destinationCoordinates, travelMode, signal })
    );
    if (result.aborted) return;

    if (result.value?.routes) {
      setRoutes(result.value.routes);
      if (result.value.routes.length === 0) {
        setError("No alternate routes could be found between these points.");
      }
    } else {
      setError("Could not compare routes right now.");
    }
    setLoading(false);
  }

  return (
    <div>
      <button
        type="button"
        onClick={handleCompare}
        disabled={loading || !origin || !destination}
        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-[#203C5A]/30 hover:bg-[#203C5A]/5 hover:text-[#203C5A] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? <Loader2 size={16} className="animate-spin" /> : <GitCompareArrows size={16} />}
        {loading ? "Comparing routes…" : "Compare alternate routes"}
      </button>

      {loading && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {!loading && error && (
        <p className="mt-3 inline-flex items-center gap-2 text-sm text-amber-700">
          <TriangleAlert size={14} /> {error}
        </p>
      )}

      {!loading && routes && routes.length > 0 && (
        <>
          <p className="mt-4 text-xs text-slate-500">
            Hover a route to preview it on the map above; click to pin it.
          </p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {routes.map((option, idx) => {
              const style = riskStyle(option.risk_assessment?.level);
              const isActive = activeIndex === idx;
              const isPinned = pinnedIndex === idx;
              return (
                <button
                  key={`${option.label}-${idx}`}
                  type="button"
                  onMouseEnter={() => setHoverIndex(idx)}
                  onMouseLeave={() => setHoverIndex(null)}
                  onFocus={() => setHoverIndex(idx)}
                  onBlur={() => setHoverIndex(null)}
                  onClick={() => setPinnedIndex((current) => (current === idx ? null : idx))}
                  className={`group rounded-xl border bg-white p-4 text-left transition-all duration-150 ${
                    isActive
                      ? "-translate-y-0.5 border-[#203C5A]/40 shadow-md ring-2 ring-[#203C5A]/15"
                      : "border-slate-200 hover:-translate-y-0.5 hover:shadow-sm"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">{option.label}</span>
                    {isPinned && (
                      <span className="rounded-full bg-[#203C5A]/10 px-2 py-0.5 text-[10px] font-medium text-[#203C5A]">
                        Pinned
                      </span>
                    )}
                  </div>

                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {option.is_fastest && (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                        Fastest
                      </span>
                    )}
                    {option.is_shortest_distance && (
                      <span className="rounded-full bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-700">
                        Shortest
                      </span>
                    )}
                  </div>

                  <div className="mt-3 flex items-center gap-4 text-sm text-slate-600">
                    <span className="inline-flex items-center gap-1.5">
                      <RouteIcon size={14} className="text-slate-400" /> {formatDistance(option.distance_km)}
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <Clock3 size={14} className="text-slate-400" /> {formatDuration(option.duration_minutes)}
                    </span>
                  </div>

                  <div className={`mt-3 inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium ${style.className}`}>
                    <ShieldAlert size={13} /> {style.label}
                  </div>

                  {option.weather && (
                    <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-slate-500">
                      <CloudSun size={13} />
                      {option.weather.temperature_c !== null ? `${option.weather.temperature_c.toFixed(0)}°C` : "—"} ·{" "}
                      {weatherCodeLabel(option.weather.weather_code)}
                    </p>
                  )}

                  {option.alerts_count > 0 && (
                    <p className="mt-1.5 text-xs text-amber-700">
                      {option.alerts_count} active alert{option.alerts_count === 1 ? "" : "s"} nearby
                    </p>
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
