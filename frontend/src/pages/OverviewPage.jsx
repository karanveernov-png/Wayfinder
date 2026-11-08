import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  MapPin,
  Route,
  Search,
  ArrowRight,
  Navigation,
  Clock3,
  Fuel,
  Coffee,
  HeartPulse,
  CloudSun,
  Loader2,
  Bookmark,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import MapView from "../components/map/MapView.jsx";
import DataStatusBadge from "../components/journey/DataStatusBadge.jsx";
import LocationAutocomplete from "../components/journey/LocationAutocomplete.jsx";
import {
  riskStyle,
  formatDistance,
  formatDuration,
  formatRelativeTime,
  weatherCodeLabel,
} from "../lib/format.js";
import { formatSuggestionLabel } from "../lib/locationSuggestions.js";
import { useJourney } from "../context/JourneyContext.jsx";
import { usePageTitle } from "../hooks/usePageTitle.js";

// Matches this page's original plain <input> styling exactly - see
// LocationAutocomplete's own defaults (TripPlannerPage's look) for why
// this is overridden here instead of shared.
const FIELD_WRAPPER_CLASS =
  "flex items-center gap-3 rounded-xl border border-slate-200 px-3 transition focus-within:border-[#203C5A] focus-within:ring-2 focus-within:ring-[#203C5A]/10";
const FIELD_INPUT_CLASS = "min-w-0 w-full bg-transparent py-3.5 text-sm outline-none";

function buildNearbyLink(category, journey) {
  const params = new URLSearchParams({ category });
  // Prefer the journey origin as the search center if available
  const origin = journey?.journey?.origin?.resolved;
  if (origin) {
    params.set("lat", String(origin.lat));
    params.set("lon", String(origin.lon));
  }
  return `/nearby-places?${params.toString()}`;
}

function StatCard({ icon: Icon, label, value, accent }) {
  return (
    <div className="stat-card transition-all duration-150 hover:-translate-y-0.5 hover:shadow-sm">
      <div className="flex items-center justify-between">
        <p className="stat-label">{label}</p>
        <Icon size={15} className={accent || "text-slate-300"} />
      </div>
      <p className="stat-value">{value}</p>
    </div>
  );
}

export default function OverviewPage() {
  usePageTitle("Overview");

  const navigate = useNavigate();
  const { journey, loading, error, runAnalysis, savedJourneys, loadSavedJourney, removeSavedJourney } =
    useJourney();
  const [start, setStart] = useState("");
  const [destination, setDestination] = useState("");
  // Set only by an explicit LocationAutocomplete selection (see
  // handleOriginSelect/handleDestinationSelect below) - never guessed.
  // Cleared the moment the text is edited again (handleStartChange /
  // handleDestinationChange) so a stale selection never rides along with
  // freshly-typed text. Mirrors TripPlannerPage.jsx's identical pattern.
  const [selectedOrigin, setSelectedOrigin] = useState(null);
  const [selectedDestination, setSelectedDestination] = useState(null);

  function handleStartChange(value) {
    setStart(value);
    setSelectedOrigin(null);
  }

  function handleDestinationChange(value) {
    setDestination(value);
    setSelectedDestination(null);
  }

  function handleOriginSelect(suggestion) {
    setStart(formatSuggestionLabel(suggestion));
    setSelectedOrigin(suggestion.coordinates);
  }

  function handleDestinationSelect(suggestion) {
    setDestination(formatSuggestionLabel(suggestion));
    setSelectedDestination(suggestion.coordinates);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const origin = start.trim();
    const target = destination.trim();
    if (!origin || !target) return;
    try {
      await runAnalysis({
        origin,
        destination: target,
        originCoordinates: selectedOrigin,
        destinationCoordinates: selectedDestination,
        travelMode: "driving",
      });
      navigate("/trip-planner");
    } catch {
      // surfaced via context.error below
    }
  }

  function openJourney(id) {
    loadSavedJourney(id);
    navigate("/trip-planner");
  }

  const j = journey?.journey;
  const originCoord = j?.origin?.resolved
    ? { ...j.origin.resolved, label: j.origin.display_name || j.origin.query }
    : null;
  const destCoord = j?.destination?.resolved
    ? { ...j.destination.resolved, label: j.destination.display_name || j.destination.query }
    : null;
  const firstWeather = journey?.weather_samples?.[0];
  const recentJourneys = savedJourneys.slice(0, 5);

  const categories = [
    { label: "Fuel & charging", icon: Fuel, path: buildNearbyLink("fuel", journey) },
    { label: "Restaurants & cafés", icon: Coffee, path: buildNearbyLink("restaurant", journey) },
    { label: "Healthcare", icon: HeartPulse, path: buildNearbyLink("hospital", journey) },
  ];

  return (
    <div className="mx-auto max-w-[1500px] space-y-6 p-5 sm:p-8">
      <section>
        <p className="eyebrow-tight">Dashboard</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Every journey, better planned.
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
          Explore routes, discover useful stops, and prepare for the road ahead — all in one place.
        </p>
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          icon={Bookmark}
          label="Saved journeys"
          value={savedJourneys.length}
          accent="text-[#203C5A]"
        />
        <StatCard
          icon={ShieldAlert}
          label="Current risk"
          value={journey ? riskStyle(journey.risk_assessment.level).label : "—"}
          accent={journey ? undefined : "text-slate-300"}
        />
        <StatCard
          icon={Route}
          label="Last distance"
          value={journey ? formatDistance(j.distance_km) : "—"}
        />
        <StatCard
          icon={Clock3}
          label="Last duration"
          value={journey ? formatDuration(j.duration_minutes) : "—"}
        />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#EAF0F6] text-[#203C5A]">
            <Route size={22} />
          </div>
          <div>
            <h3 className="font-semibold">Plan a journey</h3>
            <p className="mt-1 text-sm text-slate-500">Where would you like to go?</p>
          </div>
        </div>

        <form className="grid gap-4 lg:grid-cols-[1fr_1fr_auto]" onSubmit={handleSubmit}>
          <label>
            <span className="mb-2 block text-sm font-medium">Starting point</span>
            <LocationAutocomplete
              id="overview-start"
              icon={MapPin}
              iconClassName="text-slate-400"
              wrapperClassName={FIELD_WRAPPER_CLASS}
              inputClassName={FIELD_INPUT_CLASS}
              required
              value={start}
              onChange={handleStartChange}
              onSelect={handleOriginSelect}
              placeholder="e.g. Jalandhar"
            />
          </label>

          <label>
            <span className="mb-2 block text-sm font-medium">Destination</span>
            <LocationAutocomplete
              id="overview-destination"
              icon={Navigation}
              iconClassName="text-slate-400"
              wrapperClassName={FIELD_WRAPPER_CLASS}
              inputClassName={FIELD_INPUT_CLASS}
              required
              value={destination}
              onChange={handleDestinationChange}
              onSelect={handleDestinationSelect}
              placeholder="e.g. Chandigarh"
            />
          </label>

          <button
            type="submit"
            disabled={loading}
            className="flex items-center justify-center gap-2 self-end rounded-xl bg-[#203C5A] px-5 py-3.5 text-sm font-medium text-white transition hover:bg-[#294D70] active:scale-[0.98] disabled:opacity-60"
          >
            {loading ? <Loader2 size={17} className="animate-spin" /> : <Search size={17} />}
            Plan trip
          </button>
        </form>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 p-5">
            <div>
              <h3 className="font-semibold">Route overview</h3>
              <p className="mt-1 text-sm text-slate-500">Your journey at a glance</p>
            </div>
            {journey && <DataStatusBadge mode={journey.data_status?.mode} />}
          </div>

          {journey ? (
            <MapView
              origin={originCoord}
              destination={destCoord}
              routeGeometry={j.geometry}
              facilities={journey.facilities}
              alerts={journey.alerts}
              heightClassName="h-[280px]"
            />
          ) : (
            <div className="flex min-h-[280px] items-center justify-center bg-[#EEF2F3] p-6">
              <div className="max-w-sm rounded-xl border border-white bg-white p-6 text-center shadow-sm">
                <MapPin size={30} className="mx-auto text-[#203C5A]" />
                <h4 className="mt-3 font-semibold">Your route starts here</h4>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  Enter your origin and destination to start planning.
                </p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 p-5">
            <div className="flex items-center gap-3">
              <Route size={20} className="text-slate-400" />
              <div>
                <p className="text-xs text-slate-500">Distance</p>
                <p className="text-sm font-semibold">
                  {journey ? formatDistance(j.distance_km) : "Awaiting route"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Clock3 size={20} className="text-slate-400" />
              <div>
                <p className="text-xs text-slate-500">Duration</p>
                <p className="text-sm font-semibold">
                  {journey ? formatDuration(j.duration_minutes) : "Awaiting route"}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Explore nearby</h3>
              <ArrowRight size={18} className="text-slate-400" />
            </div>
            <p className="mt-1 text-sm text-slate-500">Useful stops along your journey</p>

            <div className="mt-5 space-y-2">
              {categories.map(({ label, icon: Icon, path }) => (
                <button
                  key={label}
                  onClick={() => navigate(path)}
                  className="row-item group w-full"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#F4F6F9] text-[#203C5A] transition group-hover:bg-[#203C5A] group-hover:text-white">
                      <Icon size={19} />
                    </div>
                    <span className="text-sm font-medium">{label}</span>
                  </div>
                  <ArrowRight
                    size={16}
                    className="text-slate-400 transition group-hover:translate-x-0.5 group-hover:text-[#203C5A]"
                  />
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <CloudSun size={22} className="text-[#203C5A]" />
              <h3 className="font-semibold">Travel conditions</h3>
            </div>
            {journey ? (
              <div className="mt-4 space-y-3">
                <div className={`rounded-xl border p-4 text-sm ${riskStyle(journey.risk_assessment.level).className}`}>
                  <p className="font-medium">{riskStyle(journey.risk_assessment.level).label}</p>
                  {journey.risk_assessment.reasons?.[0] && (
                    <p className="mt-1 text-xs opacity-90">{journey.risk_assessment.reasons[0]}</p>
                  )}
                </div>
                {firstWeather && (
                  <div className="rounded-xl bg-[#F7F8FA] p-4">
                    <p className="text-sm font-medium">
                      {firstWeather.temperature_c !== null ? `${firstWeather.temperature_c.toFixed(0)}°C` : "—"} ·{" "}
                      {weatherCodeLabel(firstWeather.weather_code)}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">Near {j.origin.display_name || j.origin.query}</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-4 rounded-xl bg-[#F7F8FA] p-4">
                <p className="text-sm font-medium">No forecast connected</p>
                <p className="mt-1 text-sm leading-5 text-slate-500">
                  Plan a journey to see weather and risk insights here.
                </p>
              </div>
            )}
          </section>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold">Recent journeys</h3>
            <p className="mt-1 text-sm text-slate-500">Saved from Trip Planner, kept on this device</p>
          </div>
          {savedJourneys.length > 0 && (
            <button
              onClick={() => navigate("/saved-journeys")}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-[#203C5A] hover:underline"
            >
              View all <ArrowRight size={14} />
            </button>
          )}
        </div>

        {recentJourneys.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">
            Plan a journey and tap "Save journey" in Trip Planner to build your history here.
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-slate-100">
            {recentJourneys.map((entry) => (
              <li key={entry.id}>
                <div className="row-item group">
                  <button onClick={() => openJourney(entry.id)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#F4F6F9] text-[#203C5A]">
                      <Route size={16} />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {entry.origin} → {entry.destination}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {formatDistance(entry.distanceKm)} · {formatDuration(entry.durationMinutes)} ·{" "}
                        {formatRelativeTime(entry.savedAt)}
                      </p>
                    </div>
                  </button>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${riskStyle(entry.riskLevel).className}`}>
                      {riskStyle(entry.riskLevel).label}
                    </span>
                    <button
                      onClick={() => removeSavedJourney(entry.id)}
                      aria-label="Delete saved journey"
                      className="rounded-lg p-1.5 text-slate-300 opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="border-t border-slate-200 py-5 text-xs text-slate-400">
        Waymark · Travel intelligence for better journeys
      </footer>
    </div>
  );
}
