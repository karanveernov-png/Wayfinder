import { CloudSun, Wind } from "lucide-react";
import { weatherCodeLabel } from "../../lib/format.js";

export default function WeatherSamples({ samples }) {
  if (!samples || samples.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No weather samples available (demo mode, or the weather source was unavailable).
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {samples.map((sample, idx) => (
        <div key={idx} className="rounded-xl border border-slate-100 p-3">
          <div className="flex items-center gap-2 text-[#203C5A]">
            <CloudSun size={18} />
            <span className="text-sm font-medium">
              {sample.temperature_c !== null ? `${sample.temperature_c.toFixed(0)}°C` : "—"}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">{weatherCodeLabel(sample.weather_code)}</p>
          {sample.windspeed_kmh !== null && (
            <p className="mt-1 flex items-center gap-1 text-xs text-slate-400">
              <Wind size={12} /> {sample.windspeed_kmh.toFixed(0)} km/h
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
