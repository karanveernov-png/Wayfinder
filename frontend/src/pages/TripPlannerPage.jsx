import { useState } from "react";
import { Route, MapPin, Flag, ArrowRight, Loader2, Bookmark, BookmarkCheck, LogIn } from "lucide-react";
import MapView from "../components/map/MapView.jsx";
import DataStatusBadge from "../components/journey/DataStatusBadge.jsx";
import RiskPanel from "../components/journey/RiskPanel.jsx";
import RecommendationsList from "../components/journey/RecommendationsList.jsx";
import FacilityList from "../components/journey/FacilityList.jsx";
import AlertsList from "../components/journey/AlertsList.jsx";
import WeatherSamples from "../components/journey/WeatherSamples.jsx";
import ElevationProfile from "../components/journey/ElevationProfile.jsx";
import RouteComparisonPanel from "../components/journey/RouteComparisonPanel.jsx";
import ShareJourneyButton from "../components/journey/ShareJourneyButton.jsx";
import TripIntentForm from "../components/journey/TripIntentForm.jsx";
import LocationAutocomplete from "../components/journey/LocationAutocomplete.jsx";
import { useJourney } from "../context/JourneyContext.jsx";
import { useAuth } from "../context/useAuth.js";
import { formatDistance, formatDuration } from "../lib/format.js";
import { formatSuggestionLabel } from "../lib/locationSuggestions.js";
import { usePageTitle } from "../hooks/usePageTitle.js";
import { useNavigate } from "react-router-dom";

const TRAVEL_MODES = [
  { value: "driving", label: "Driving" },
  { value: "two-wheeler", label: "Two-wheeler" },
  { value: "cycling", label: "Cycling" },
  { value: "transit", label: "Transit" },
];

// Presets in km for the facility-search radius sent as facility_radius_km —
// matches the 5 km default analyseJourney already falls back to.
const FACILITY_RADIUS_PRESETS_KM = [2, 5, 10, 20];

export default function TripPlannerPage() {
  usePageTitle("Trip Planner");

  const { journey, loading, error, runAnalysis, saveCurrentJourney } = useJourney();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [start, setStart] = useState("");
  const [destination, setDestination] = useState("");
  const [travelMode, setTravelMode] = useState("driving");
  const [facilityRadiusKm, setFacilityRadiusKm] = useState(5);
  const [selectedOrigin, setSelectedOrigin] = useState(null);
  const [selectedDestination, setSelectedDestination] = useState(null);
  const [routeDirty, setRouteDirty] = useState(false);
  const [demo, setDemo] = useState(false);
  const [formError, setFormError] = useState("");
  const [saved, setSaved] = useState(false);
  const [previewRouteGeometry, setPreviewRouteGeometry] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaved(false);

    const origin = start.trim();
    const target = destination.trim();

    if (!demo) {
      if (!origin || !target) {
        setFormError("Please enter both your starting point and destination.");
        return;
      }
      if (origin.toLowerCase() === target.toLowerCase()) {
        setFormError("Your starting point and destination must be different.");
        return;
      }
    }

    setFormError("");
    try {
      await runAnalysis({
        origin: demo ? "Chandigarh, India" : origin,
        destination: demo ? "Ludhiana, Punjab, India" : target,
        originCoordinates: demo ? undefined : selectedOrigin,
        destinationCoordinates: demo ? undefined : selectedDestination,
        travelMode,
        facilityRadiusKm,
        demo,
      });
      setRouteDirty(false);
    } catch {
      // error is already surfaced via context.error
    }
  }

  const j = journey?.journey;
  const originCoord = j?.origin?.resolved
    ? { ...j.origin.resolved, label: j.origin.display_name || j.origin.query }
    : null;
  const destCoord = j?.destination?.resolved
    ? { ...j.destination.resolved, label: j.destination.display_name || j.destination.query }
    : null;
  const mapOrigin = selectedOrigin
    ? { ...selectedOrigin, label: start }
    : (!start.trim() ? originCoord : null);
  const mapDestination = selectedDestination
    ? { ...selectedDestination, label: destination }
    : (!destination.trim() ? destCoord : null);

  function formatMapPoint(point) {
    return `Map point (${point.lat.toFixed(5)}, ${point.lng.toFixed(5)})`;
  }

  function handlePointPick(point, type) {
    const coordinates = { lat: point.lat, lon: point.lng };
    const label = formatMapPoint(point);
    if (type === "origin") {
      setSelectedOrigin(coordinates);
      setStart(label);
    } else {
      setSelectedDestination(coordinates);
      setDestination(label);
    }
    setRouteDirty(true);
    setFormError("");
  }

  function handleMarkerDrag(point, type) {
    handlePointPick(point, type);
  }

  function handleStartChange(value) {
    setStart(value);
    // The text no longer matches whatever was previously selected (map
    // click or a suggestion) - never let stale coordinates ride along
    // with freshly-edited text.
    setSelectedOrigin(null);
    setRouteDirty(true);
  }

  function handleDestinationChange(value) {
    setDestination(value);
    setSelectedDestination(null);
    setRouteDirty(true);
  }

  // Called when the user picks a suggestion from LocationAutocomplete
  // (see components/journey/LocationAutocomplete.jsx) - sets the
  // canonical display text and the real coordinates together, the same
  // *Coordinates shape a map-click selection already produces (see
  // handlePointPick above), so it flows into the existing journey
  // pipeline without any changes there.
  function handleOriginSelect(suggestion) {
    setStart(formatSuggestionLabel(suggestion));
    setSelectedOrigin(suggestion.coordinates);
    setRouteDirty(true);
    setFormError("");
  }

  function handleDestinationSelect(suggestion) {
    setDestination(formatSuggestionLabel(suggestion));
    setSelectedDestination(suggestion.coordinates);
    setRouteDirty(true);
    setFormError("");
  }

  return (
    <main className="min-h-screen bg-[#F7F8FA] p-5 sm:p-8">
      <div className="mx-auto max-w-5xl">
        <div className="flex items-center gap-3">
          <Route size={28} className="text-[#203C5A]" />
          <h1 className="text-3xl font-semibold">Trip Planner</h1>
        </div>

        <p className="mt-3 text-slate-500">
          Plan your journey and prepare for the road ahead — routing, nearby stops, weather, and a
          risk assessment, all from live data where available.
        </p>

        <div className="mt-8">
          <TripIntentForm />
        </div>

        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Plan a new journey</h2>
            {journey && <DataStatusBadge mode={journey.data_status?.mode} />}
          </div>
          <p className="mt-2 text-sm text-slate-500">
            Enter your locations, or try the demo corridor (Chandigarh → Ludhiana) with no network
            access required.
          </p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-5">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={demo}
                onChange={(event) => setDemo(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300"
              />
              Use demo corridor (no live providers, works offline)
            </label>

            <div>
              <label htmlFor="start" className="mb-2 block text-sm font-medium text-slate-700">
                Starting point
              </label>
              <LocationAutocomplete
                id="start"
                icon={MapPin}
                value={start}
                onChange={handleStartChange}
                onSelect={handleOriginSelect}
                placeholder="e.g. Jalandhar, India"
                disabled={demo}
              />
            </div>

            <div>
              <label htmlFor="destination" className="mb-2 block text-sm font-medium text-slate-700">
                Destination
              </label>
              <LocationAutocomplete
                id="destination"
                icon={Flag}
                value={destination}
                onChange={handleDestinationChange}
                onSelect={handleDestinationSelect}
                placeholder="e.g. Chandigarh, India"
                disabled={demo}
              />
            </div>

            <div>
              <h3 id="travelModeLabel" className="mb-2 text-sm font-medium text-slate-700">
                Travel mode
              </h3>
              <div
                role="radiogroup"
                aria-labelledby="travelModeLabel"
                className="inline-flex flex-wrap gap-1 rounded-2xl border border-white/60 bg-white/50 p-1.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] backdrop-blur-xl"
              >
                {TRAVEL_MODES.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={travelMode === value}
                    onClick={() => setTravelMode(value)}
                    className={`rounded-xl px-4 py-2 text-sm font-medium transition ${
                      travelMode === value
                        ? "bg-[#203C5A]/90 text-white shadow-sm"
                        : "text-slate-600 hover:bg-white/70"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Non-driving modes use the configured OSRM fallback. Cycling requires a cycling-enabled
                OSRM profile; two-wheeler uses the road profile, and Transit is currently an approximate
                road route, not a train itinerary or timetable.
              </p>
            </div>

            <div>
              <h3 id="facilityRadiusLabel" className="mb-2 text-sm font-medium text-slate-700">
                Nearby facility radius
              </h3>
              <div
                role="radiogroup"
                aria-labelledby="facilityRadiusLabel"
                className="inline-flex gap-1 rounded-2xl border border-white/60 bg-white/50 p-1.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] backdrop-blur-xl"
              >
                {FACILITY_RADIUS_PRESETS_KM.map((km) => (
                  <button
                    key={km}
                    type="button"
                    role="radio"
                    aria-checked={facilityRadiusKm === km}
                    onClick={() => setFacilityRadiusKm(km)}
                    className={`rounded-xl px-4 py-2 text-sm font-medium transition ${
                      facilityRadiusKm === km
                        ? "bg-[#203C5A]/90 text-white shadow-sm"
                        : "text-slate-600 hover:bg-white/70"
                    }`}
                  >
                    {km} km
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs text-slate-500">
                How far from the route to search for hospitals, fuel, rest stops and restaurants.
              </p>
            </div>

            <div>
              <h3 className="mb-2 text-sm font-medium text-slate-700">Choose points on the map</h3>
              <p className="mb-3 text-xs text-slate-500">
                Click once to set Point A, click again to set Point B. Drag either marker to adjust it.
                You can also enter place names above.
              </p>
              <MapView
                origin={mapOrigin}
                destination={mapDestination}
                routeGeometry={previewRouteGeometry || (routeDirty ? null : j?.geometry)}
                facilities={journey?.facilities || []}
                alerts={journey?.alerts || []}
                isPicking={!demo}
                onPointPick={handlePointPick}
                onMarkerDrag={handleMarkerDrag}
                heightClassName="h-[380px]"
              />
            </div>

            {!demo && (
              <div>
                <h3 className="mb-2 text-sm font-medium text-slate-700">Compare routes (optional)</h3>
                <RouteComparisonPanel
                  origin={start.trim()}
                  destination={destination.trim()}
                  originCoordinates={selectedOrigin}
                  destinationCoordinates={selectedDestination}
                  travelMode={travelMode}
                  onPreviewRoute={setPreviewRouteGeometry}
                />
              </div>
            )}

            {formError && (
              <p role="alert" className="text-sm text-red-600">
                {formError}
              </p>
            )}
            {error && (
              <p role="alert" className="text-sm text-red-600">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#203C5A] px-5 py-3 font-medium text-white transition hover:bg-[#172E46] disabled:opacity-60 sm:w-auto"
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="animate-spin" /> Analysing journey…
                </>
              ) : (
                <>
                  Plan journey <ArrowRight size={18} />
                </>
              )}
            </button>
          </form>
        </section>

        {journey && (
          <div className="mt-6 space-y-6">
            <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-[#52708D]">JOURNEY SUMMARY</p>
                  <p className="mt-1 font-semibold">
                    {j.origin.display_name || j.origin.query} → {j.destination.display_name || j.destination.query}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <ShareJourneyButton journey={journey} travelMode={travelMode} />
                  {user ? (
                    <button
                      onClick={() => {
                        saveCurrentJourney().then(() => setSaved(true)).catch(() => {});
                      }}
                      className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      {saved ? <BookmarkCheck size={16} className="text-emerald-600" /> : <Bookmark size={16} />}
                      {saved ? "Saved" : "Save journey"}
                    </button>
                  ) : (
                    <button
                      onClick={() => navigate("/login")}
                      className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      <LogIn size={16} />
                      Sign in to save
                    </button>
                  )}
                </div>
              </div>

              <div className="mt-4 flex gap-3 rounded-2xl border border-white/50 bg-gradient-to-br from-[#203C5A]/8 to-[#203C5A]/2 p-3 backdrop-blur-sm sm:w-80">
                <div className="flex-1 rounded-xl bg-white/65 px-4 py-2.5 backdrop-blur-md">
                  <p className="text-[11px] text-slate-500">Distance</p>
                  <p className="text-sm font-semibold">{formatDistance(j.distance_km)}</p>
                </div>
                <div className="flex-1 rounded-xl bg-white/65 px-4 py-2.5 backdrop-blur-md">
                  <p className="text-[11px] text-slate-500">Duration</p>
                  <p className="text-sm font-semibold">{formatDuration(j.duration_minutes)}</p>
                </div>
              </div>

            </section>

            <RiskPanel assessment={journey.risk_assessment} />
            <RecommendationsList recommendations={journey.recommendations} />

            <section className="grid gap-5 lg:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h3 className="font-semibold">Nearby facilities ({journey.facilities.length})</h3>
                <div className="mt-3 max-h-80 overflow-y-auto pr-1">
                  <FacilityList facilities={journey.facilities} />
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h3 className="font-semibold">Alerts</h3>
                <div className="mt-3 max-h-80 overflow-y-auto pr-1">
                  <AlertsList alerts={journey.alerts} dataStatus={journey.data_status} />
                </div>
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="font-semibold">Weather along the route</h3>
              <div className="mt-3">
                <WeatherSamples samples={journey.weather_samples} />
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="font-semibold">Elevation profile</h3>
              <div className="mt-3">
                <ElevationProfile routeGeometry={j?.geometry} />
              </div>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
