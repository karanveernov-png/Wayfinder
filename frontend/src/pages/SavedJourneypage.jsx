import { useNavigate } from "react-router-dom";
import { Bookmark, Trash2, ArrowRight } from "lucide-react";
import { useJourney } from "../context/JourneyContext.jsx";
import DataStatusBadge from "../components/journey/DataStatusBadge.jsx";
import ShareJourneyButton from "../components/journey/ShareJourneyButton.jsx";
import { formatDistance, formatDuration, riskStyle } from "../lib/format.js";
import { usePageTitle } from "../hooks/usePageTitle.js";

export default function SavedJourneysPage() {
  usePageTitle("Saved Journeys");

  const { savedJourneys, removeSavedJourney, loadSavedJourney } = useJourney();
  const navigate = useNavigate();

  function openJourney(id) {
    loadSavedJourney(id);
    navigate("/trip-planner");
  }

  return (
    <main className="p-5 sm:p-8">
      <div className="mx-auto max-w-4xl">
        <p className="text-sm font-medium text-[#52708D]">YOUR HISTORY</p>
        <h1 className="mt-2 text-3xl font-semibold">Saved Journeys</h1>
        <p className="mt-3 text-slate-500">
          Journeys you've saved from Trip Planner, tied to your account —
          available wherever you're signed in.
        </p>

        {savedJourneys.length === 0 ? (
          <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-6">
            <Bookmark size={26} className="text-[#203C5A]" />
            <h2 className="mt-4 font-semibold">No saved journeys yet</h2>
            <p className="mt-2 text-sm text-slate-500">
              Plan a journey in Trip Planner, then tap "Save journey" to keep it here.
            </p>
          </section>
        ) : (
          <ul className="mt-8 space-y-3">
            {savedJourneys.map((entry) => (
              <li
                key={entry.id}
                className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-5"
              >
                <div className="min-w-0">
                  <p className="font-semibold">
                    {entry.origin} → {entry.destination}
                  </p>
                  <p className="mt-1 text-sm text-slate-500">
                    {formatDistance(entry.distance_km)} · {formatDuration(entry.duration_minutes)} ·{" "}
                    {new Date(entry.created_at).toLocaleString()}
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${riskStyle(entry.risk_level).className}`}>
                      {riskStyle(entry.risk_level).label}
                    </span>
                    <DataStatusBadge mode={entry.data_status_mode} />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <ShareJourneyButton
                    journey={entry}
                    travelMode={entry.params_json?.travel_mode || "driving"}
                  />
                  <button
                    onClick={() => openJourney(entry.id)}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Open <ArrowRight size={14} />
                  </button>
                  <button
                    onClick={() => removeSavedJourney(entry.id)}
                    className="inline-flex items-center justify-center rounded-xl border border-slate-200 p-2 text-slate-400 hover:bg-red-50 hover:text-red-600"
                    aria-label="Delete saved journey"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
