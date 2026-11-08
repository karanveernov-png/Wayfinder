import { Link } from "react-router-dom";
import { CloudSun, Route } from "lucide-react";
import DataStatusBadge from "../components/journey/DataStatusBadge.jsx";
import RiskPanel from "../components/journey/RiskPanel.jsx";
import RecommendationsList from "../components/journey/RecommendationsList.jsx";
import WeatherSamples from "../components/journey/WeatherSamples.jsx";
import AlertsList from "../components/journey/AlertsList.jsx";
import { useJourney } from "../context/JourneyContext.jsx";
import { formatDistance, formatDuration } from "../lib/format.js";
import { usePageTitle } from "../hooks/usePageTitle.js";

export default function TravelInsightsPage() {
  usePageTitle("Travel Insights");

  const { journey } = useJourney();

  return (
    <main className="p-5 sm:p-8">
      <div className="mx-auto max-w-5xl">
        <p className="text-sm font-medium text-[#52708D]">CONDITIONS & SAFETY</p>
        <h1 className="mt-2 text-3xl font-semibold">Travel Insights</h1>
        <p className="mt-3 text-slate-500">
          Weather, risk assessment, and alerts for your most recently planned journey.
        </p>

        {!journey ? (
          <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-6">
            <CloudSun size={26} className="text-[#203C5A]" />
            <h2 className="mt-4 font-semibold">No journey analysed yet</h2>
            <p className="mt-2 text-sm text-slate-500">
              Plan a journey first — insights are generated from its live routing, weather and alert
              data.
            </p>
            <Link
              to="/trip-planner"
              className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#203C5A] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#172E46]"
            >
              <Route size={16} /> Plan a journey
            </Link>
          </section>
        ) : (
          <div className="mt-8 space-y-6">
            <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-5">
              <div>
                <p className="font-semibold">
                  {journey.journey.origin.display_name || journey.journey.origin.query} →{" "}
                  {journey.journey.destination.display_name || journey.journey.destination.query}
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  {formatDistance(journey.journey.distance_km)} · {formatDuration(journey.journey.duration_minutes)}
                </p>
              </div>
              <DataStatusBadge mode={journey.data_status?.mode} />
            </section>

            <RiskPanel assessment={journey.risk_assessment} />
            <RecommendationsList recommendations={journey.recommendations} />

            <section className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="font-semibold">Weather along the route</h3>
              <div className="mt-3">
                <WeatherSamples samples={journey.weather_samples} />
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="font-semibold">Alerts</h3>
              <div className="mt-3">
                <AlertsList alerts={journey.alerts} dataStatus={journey.data_status} />
              </div>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
