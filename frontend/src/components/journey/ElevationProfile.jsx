// frontend/src/components/journey/ElevationProfile.jsx
//
// npm install recharts
//
// Usage in TripPlannerPage.jsx, alongside the existing WeatherSamples /
// RiskPanel sections:
//
//   <section className="rounded-2xl border border-slate-200 bg-white p-5">
//     <h3 className="font-semibold">Elevation profile</h3>
//     <div className="mt-3">
//       <ElevationProfile routeGeometry={j?.geometry} onHoverPoint={setHoverPoint} />
//     </div>
//   </section>
//
// `onHoverPoint` is optional — wire it to a small extra <CircleMarker>
// prop on MapView if you want the classic "hover the chart, see the dot
// move along the route" sync; omit it and the chart still works standalone.

import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { TrendingUp, TrendingDown, Loader2 } from "lucide-react";
import { useElevationProfile } from "../../hooks/useElevationProfile.js";

function ElevationTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-sm backdrop-blur">
      <p className="font-medium text-slate-700">{point.elevationM} m</p>
      <p className="text-slate-500">{point.distanceKm.toFixed(1)} km along route</p>
    </div>
  );
}

export default function ElevationProfile({ routeGeometry, onHoverPoint }) {
  const { data, loading, error, totalAscentM, totalDescentM } = useElevationProfile(routeGeometry);

  const chartData = useMemo(
    () => data.map((d) => ({ ...d, distanceKm: Math.round(d.distanceKm * 10) / 10 })),
    [data]
  );

  if (!routeGeometry) {
    return <p className="text-sm text-slate-500">Plan a journey to see its elevation profile.</p>;
  }

  if (loading && chartData.length === 0) {
    return (
      <p className="inline-flex items-center gap-2 text-sm text-slate-500">
        <Loader2 size={14} className="animate-spin" /> Reading terrain along the route…
      </p>
    );
  }

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  return (
    <div>
      <div className="mb-3 flex gap-4 text-sm">
        <span className="inline-flex items-center gap-1.5 text-emerald-700">
          <TrendingUp size={15} /> {totalAscentM} m ascent
        </span>
        <span className="inline-flex items-center gap-1.5 text-amber-700">
          <TrendingDown size={15} /> {totalDescentM} m descent
        </span>
      </div>

      <div className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={chartData}
            onMouseMove={(state) => {
              const point = state?.activePayload?.[0]?.payload;
              if (point) onHoverPoint?.(point);
            }}
            onMouseLeave={() => onHoverPoint?.(null)}
          >
            <defs>
              <linearGradient id="elevationFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#203C5A" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#203C5A" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e4e7ec" vertical={false} />
            <XAxis
              dataKey="distanceKm"
              tickFormatter={(v) => `${v} km`}
              tick={{ fontSize: 11, fill: "#8a95a5" }}
              axisLine={{ stroke: "#e4e7ec" }}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v) => `${v} m`}
              tick={{ fontSize: 11, fill: "#8a95a5" }}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <Tooltip content={<ElevationTooltip />} />
            <Area
              type="monotone"
              dataKey="elevationM"
              stroke="#203C5A"
              strokeWidth={2}
              fill="url(#elevationFill)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
