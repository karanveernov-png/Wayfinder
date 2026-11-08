import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  MapPin,
  Fuel,
  Coffee,
  Hospital,
  ParkingCircle,
  Pill,
  Hotel,
  Crosshair,
  Loader2,
  SearchX,
  AlertTriangle,
  Flag,
  RefreshCw,
} from "lucide-react";
import MapView from "../components/map/MapView.jsx";
import DataStatusBadge from "../components/journey/DataStatusBadge.jsx";
import FacilityList from "../components/journey/FacilityList.jsx";
import { useJourney } from "../context/JourneyContext.jsx";
import { fetchNearbyFacilities, ApiError } from "../lib/api.js";
import {
  metersToKm,
  formatRadius,
  zoomForRadiusMeters,
  RADIUS_PRESETS_M,
  clampRadiusMeters,
  viewModeForRadiusMeters,
  haversineMeters,
} from "../lib/geo.js";
import { FACILITY_LEGEND } from "../lib/mapIcons.js";
import { usePageTitle } from "../hooks/usePageTitle.js";

// Lazy-loaded: maplibre-gl is a sizeable dependency that only the globe view
// needs. Code-splitting it here keeps it out of every other page's bundle
// (Trip Planner, Overview, etc. never import this module at all) and out of
// this page's own initial load until someone actually reaches a >20km
// radius search — see the acceptance criteria's "avoid loading two full map
// renderers on every page unnecessarily".
const GlobeMapView = lazy(() => import("../components/map/GlobeMapView.jsx"));

const categories = [
  { name: "all", label: "All", icon: MapPin },
  { name: "fuel", label: "Fuel", icon: Fuel },
  { name: "restaurant", label: "Restaurant & cafe", icon: Coffee },
  { name: "hospital", label: "Hospital", icon: Hospital },
  { name: "pharmacy", label: "Pharmacy", icon: Pill },
  { name: "lodging", label: "Lodging", icon: Hotel },
  { name: "rest_stop", label: "Rest stop", icon: ParkingCircle },
];

/**
 * Preset radii in metres — each maps to radius_km exactly. Sourced from
 * geo.js (the single source of truth for the 200m-70km radius contract)
 * rather than duplicated here, so the two can't drift out of sync.
 */
const NEARBY_RADIUS_PRESETS_M = RADIUS_PRESETS_M;

/** "auto" follows the radius thresholds in geo.js; the others are a manual pin. */
const VIEW_MODES = [
  { value: "auto", label: "Auto" },
  { value: "street", label: "Street" },
  { value: "regional", label: "Regional" },
  { value: "globe", label: "Globe" },
];

// Human-readable messages for the browser Geolocation API's error codes
// (1 = PERMISSION_DENIED, 2 = POSITION_UNAVAILABLE, 3 = TIMEOUT). Never
// fabricate a location when one of these fires — just explain what happened.
function geolocationErrorMessage(err) {
  switch (err.code) {
    case 1:
      return "Location permission denied. Allow location access in your browser's site settings to use this.";
    case 3:
      return "Getting your location timed out. Check your connection and try again.";
    default:
      return "Could not determine your location — check your device's location settings.";
  }
}

export default function NearbyPlacesPage() {
  usePageTitle("Nearby Places");

  const { journey } = useJourney();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialCategory = searchParams.get("category") || "all";
  // If the category shortcut passes a lat/lon, use that as the initial search center
  const initialLat = searchParams.get("lat") ? Number(searchParams.get("lat")) : null;
  const initialLon = searchParams.get("lon") ? Number(searchParams.get("lon")) : null;

  const [activeCategory, setActiveCategory] = useState(initialCategory);
  const [radiusMeters, setRadiusMeters] = useState(300);
  // "auto" picks street/regional/globe from the radius thresholds in geo.js;
  // a manual value pins the view and stops it from being changed just by
  // moving the radius slider, per the "respect manual view selection"
  // requirement.
  const [viewMode, setViewMode] = useState("auto");
  const [point, setPoint] = useState(() => {
    if (initialLat != null && initialLon != null) {
      return { lat: initialLat, lon: initialLon, label: "Selected location" };
    }
    // If no explicit lat/lon, fall back to journey origin or null
    const origin = journey?.journey?.origin?.resolved;
    if (origin) {
      return { ...origin, label: journey.journey.origin.display_name || journey.journey.origin.query };
    }
    return null;
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [gpsAccuracyMeters, setGpsAccuracyMeters] = useState(null);
  const [locating, setLocating] = useState(false);

  const [selectedFacilityId, setSelectedFacilityId] = useState(null);
  const [focusTarget, setFocusTarget] = useState(null);
  const focusTokenRef = useRef(0);

  // Where the map is currently centered, which can drift from `point` as
  // soon as the person pans/zooms — drives the "Search this area" button
  // below, the same affordance Google/Apple Maps use instead of silently
  // re-searching on every nudge.
  const [viewportCenter, setViewportCenter] = useState(null);
  useEffect(() => {
    // Same category of reset-on-new-search-point update as
    // setSelectedFacilityId/setFocusTarget in the search effect below.
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    setViewportCenter(null);
  }, [point]);

  const radiusKm = useMemo(() => metersToKm(radiusMeters), [radiusMeters]);
  const mapZoom = useMemo(
    () => (point ? zoomForRadiusMeters(radiusMeters, point.lat) : 8),
    [radiusMeters, point]
  );
  const effectiveViewMode = useMemo(
    () => (viewMode === "auto" ? viewModeForRadiusMeters(radiusMeters) : viewMode),
    [viewMode, radiusMeters]
  );

  const hasMovedFromSearchCenter =
    point && viewportCenter && haversineMeters(point, viewportCenter) > Math.max(radiusMeters * 0.5, 150);

  // Guards against a slower, earlier request overwriting a faster, later one
  // (e.g. two radius presets tapped in quick succession) — only the most
  // recently *started* search is ever allowed to update state.
  const latestRequestRef = useRef(0);

  const search = useCallback(async (searchPoint, category, radius) => {
    const requestId = ++latestRequestRef.current;
    setLoading(true);
    setError(null);
    try {
      const response = await fetchNearbyFacilities({
        lat: searchPoint.lat,
        lon: searchPoint.lon,
        radiusKm: radius,
        category,
      });
      if (requestId !== latestRequestRef.current) return; // superseded by a newer search
      setResult(response);
    } catch (err) {
      if (requestId !== latestRequestRef.current) return;
      setError(err instanceof ApiError ? err.message : "Could not load nearby places.");
      setResult(null);
    } finally {
      if (requestId === latestRequestRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!point) return;
    // A new search invalidates any facility selected from the previous result set,
    // and search() itself sets loading/result state as part of fetching — both are
    // standard data-fetching-effect state updates, by design.
    /* eslint-disable react-hooks/set-state-in-effect */
    setSelectedFacilityId(null);
    setFocusTarget(null);
    search(point, activeCategory, radiusKm);
    /* eslint-enable react-hooks/set-state-in-effect */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [point, activeCategory, radiusKm]);

  function handleCategoryChange(name) {
    setActiveCategory(name);
    setSearchParams(name === "all" ? {} : { category: name });
  }

  function applyJourneyPoint(which) {
    const loc = journey?.journey?.[which];
    if (!loc?.resolved) return;
    setGpsAccuracyMeters(null);
    setPoint({ ...loc.resolved, label: loc.display_name || loc.query });
  }

  /** Sets the radius, clamped to the supported 200m-70km range — defensive even
   * though every current caller passes a known-valid preset, so a bad value
   * (e.g. from a future custom-radius input or a malformed URL param) can
   * never reach the API request or the map. */
  function setClampedRadius(meters) {
    setRadiusMeters(clampRadiusMeters(meters));
  }

  function expandRadius() {
    const idx = NEARBY_RADIUS_PRESETS_M.indexOf(radiusMeters);
    const next = NEARBY_RADIUS_PRESETS_M[idx + 1];
    if (next) setClampedRadius(next);
  }

  function searchThisArea() {
    if (!viewportCenter) return;
    setPoint({ ...viewportCenter, label: "This area" });
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError("Geolocation is not available in this browser.");
      return;
    }
    setLocating(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude, accuracy } = position.coords;
        setGpsAccuracyMeters(Number.isFinite(accuracy) ? accuracy : null);
        setPoint({ lat: latitude, lon: longitude, label: "Your current location" });
        setLocating(false);
      },
      (err) => {
        setGpsAccuracyMeters(null);
        setLocating(false);
        setError(geolocationErrorMessage(err));
      },
      // High accuracy where the device supports it; a generous timeout since
      // a GPS fix can take several seconds, and no cached (possibly stale)
      // position so the accuracy circle reflects the current fix.
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
    );
  }

  function selectFacility(facilityId, { pan = true } = {}) {
    setSelectedFacilityId(facilityId);
    if (!pan) return;
    const facility = facilities.find((f, idx) => (f.id || `facility-${idx}`) === facilityId);
    if (!facility?.coordinates) return;
    focusTokenRef.current += 1;
    setFocusTarget({ lat: facility.coordinates.lat, lon: facility.coordinates.lon, zoom: 17, token: focusTokenRef.current });
  }

  const facilities = result?.facilities || [];
  const dataStatusMode = result?.data_status?.mode;
  // The backend's /facilities/nearby only ever returns "live" or "degraded" (no live
  // provider call was attempted for "demo"/"partial" on this single-point endpoint) —
  // a provider failure must never be mistaken for a quiet, successful empty search.
  const providerFailed = dataStatusMode === "degraded";
  const showEmptyState = !loading && !error && result && facilities.length === 0;
  const nextRadius = NEARBY_RADIUS_PRESETS_M[NEARBY_RADIUS_PRESETS_M.indexOf(radiusMeters) + 1];

  return (
    <main className="mx-auto max-w-[1400px] p-5 sm:p-8">
      <div className="mb-6">
        <p className="eyebrow-tight">Discover your surroundings</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Nearby Places</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
          Live hospitals, pharmacies, fuel stations, lodging, restaurants and rest stops around your
          chosen location.
        </p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        {!point ? (
          // No location selected yet — show empty state with actions
          <div className="py-12 text-center sm:py-16">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#EAF0F6] text-[#203C5A]">
              <MapPin size={26} />
            </div>
            <h2 className="mt-4 text-lg font-semibold">Select a location to search</h2>
            <p className="mx-auto mt-2 max-w-sm text-sm text-slate-500">
              Choose a search center using the buttons below, or use your device's current location.
            </p>
            <div className="mt-6 flex flex-col items-center gap-2.5">
              <button
                onClick={useMyLocation}
                disabled={locating}
                className="flex w-full max-w-xs items-center justify-center gap-2 rounded-xl bg-[#203C5A] px-5 py-3 text-sm font-medium text-white transition hover:bg-[#294D70] active:scale-[0.98] disabled:opacity-60"
              >
                {locating ? (
                  <>
                    <Loader2 size={18} className="animate-spin" /> Locating…
                  </>
                ) : (
                  <>
                    <Crosshair size={18} /> Use my location
                  </>
                )}
              </button>
              {journey?.journey?.origin?.resolved && (
                <button
                  onClick={() => applyJourneyPoint("origin")}
                  className="flex w-full max-w-xs items-center justify-center gap-2 rounded-xl border border-slate-200 px-5 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  <MapPin size={16} /> Near journey start
                </button>
              )}
              {journey?.journey?.destination?.resolved && (
                <button
                  onClick={() => applyJourneyPoint("destination")}
                  className="flex w-full max-w-xs items-center justify-center gap-2 rounded-xl border border-slate-200 px-5 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  <Flag size={16} /> Near journey destination
                </button>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-1.5 rounded-2xl border border-slate-100 bg-slate-50/60 p-1.5">
              {categories.map(({ name, label, icon: Icon }) => (
                <button
                  key={name}
                  onClick={() => handleCategoryChange(name)}
                  className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium transition-all duration-150 ${
                    activeCategory === name
                      ? "bg-[#203C5A] text-white shadow-sm"
                      : "text-slate-600 hover:-translate-y-0.5 hover:bg-white hover:shadow-sm"
                  }`}
                >
                  <Icon size={15} />
                  {label}
                </button>
              ))}
            </div>

            {/* Category legend */}
            <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1.5">
              {FACILITY_LEGEND.map(({ category, label, color }) => (
                <span key={category} className="inline-flex items-center gap-1.5 text-xs text-slate-500">
                  <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                  {label}
                </span>
              ))}
            </div>

            <div className="mb-4 flex flex-wrap items-center gap-3">
              <button
                onClick={useMyLocation}
                disabled={locating}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 transition hover:border-[#203C5A]/30 hover:bg-[#203C5A]/5 hover:text-[#203C5A] disabled:opacity-60"
              >
                {locating ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Locating…
                  </>
                ) : (
                  <>
                    <Crosshair size={14} />
                    Use my location
                  </>
                )}
              </button>
              {journey?.journey?.origin?.resolved && (
                <button
                  onClick={() => applyJourneyPoint("origin")}
                  className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  <MapPin size={14} />
                  Near journey start
                </button>
              )}
              {journey?.journey?.destination?.resolved && (
                <button
                  onClick={() => applyJourneyPoint("destination")}
                  className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  <Flag size={14} />
                  Near journey destination
                </button>
              )}

              <div className="ml-auto flex flex-wrap items-center gap-2">
                <span className="text-xs text-slate-500">Radius</span>
                {NEARBY_RADIUS_PRESETS_M.map((meters) => (
                  <button
                    key={meters}
                    onClick={() => setClampedRadius(meters)}
                    aria-pressed={radiusMeters === meters}
                    className={radiusMeters === meters ? "chip-glass-active" : "chip-glass"}
                  >
                    {formatRadius(meters)}
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span id="view-mode-label" className="text-xs text-slate-500">
                Map view
              </span>
              <div role="group" aria-labelledby="view-mode-label" className="flex flex-wrap gap-1.5">
                {VIEW_MODES.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setViewMode(value)}
                    aria-pressed={viewMode === value}
                    aria-label={value === "auto" ? `Auto (currently ${effectiveViewMode})` : `${label} view`}
                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                      viewMode === value
                        ? "border-[#203C5A] bg-[#203C5A] text-white"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {value === "auto" ? `Auto (${effectiveViewMode})` : label}
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-slate-500">
                {loading ? (
                  <span className="inline-flex items-center gap-2">
                    <Loader2 size={14} className="animate-spin" />
                    Searching within {formatRadius(radiusMeters)}…
                  </span>
                ) : error ? (
                  "Search failed"
                ) : (
                  `Showing ${facilities.length} ${facilities.length === 1 ? "place" : "places"} within ${formatRadius(radiusMeters)} of ${point.label}`
                )}
              </p>
              {result && !error && <DataStatusBadge mode={dataStatusMode} />}
            </div>
            {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
            {/* The backend caps how many raw elements it fetches per search (see
                MAX_FACILITY_RESULTS/FACILITY_RESULT_LIMIT_LARGE_RADIUS in
                config.py) — for a wide-radius search that cap can be hit before
                every real facility in the area is found, so result_truncated
                is surfaced honestly here rather than implying this list is
                exhaustive. */}
            {!loading && !error && result?.result_truncated && (
              <p className="mb-4 flex items-start gap-2 text-xs text-amber-700">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                Showing the closest {result.result_limit ?? facilities.length} matches returned by the provider —
                there may be more facilities in this radius that aren't listed. Try a smaller radius for a
                complete picture of a specific area.
              </p>
            )}

            <div className="relative" style={{ height: 420 }}>
              {/* "Search this area" — appears once the map has been dragged a
                  meaningful distance from the active search center, instead of
                  silently re-searching on every pan (which would fight anyone
                  just trying to look around) or never offering a way to
                  explore an adjacent area without typing a new location. */}
              {effectiveViewMode !== "globe" && (
                <div
                  className={`pointer-events-none absolute inset-x-0 top-3 z-[1000] flex justify-center transition-all duration-200 ${
                    hasMovedFromSearchCenter ? "translate-y-0 opacity-100" : "-translate-y-2 opacity-0"
                  }`}
                >
                  <button
                    onClick={searchThisArea}
                    className="pointer-events-auto inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-[#203C5A] shadow-md transition hover:-translate-y-0.5 hover:shadow-lg active:scale-95"
                  >
                    <RefreshCw size={14} />
                    Search this area
                  </button>
                </div>
              )}

              {effectiveViewMode === "globe" ? (
                // Large radii (>20 km, up to 70 km) hand off to the MapLibre-based
                // globe renderer — a real 3D projection, not the Leaflet flat map
                // zoomed out with a globe icon. This is a separate, isolated
                // component (see GlobeMapView.jsx) so the Leaflet path used
                // everywhere else (Trip Planner, Overview, street/regional here)
                // is completely untouched by this feature.
                <Suspense
                  fallback={
                    <div className="flex h-full w-full items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 text-sm text-slate-500">
                      <Loader2 size={16} className="animate-spin" /> Loading globe view…
                    </div>
                  }
                >
                  <GlobeMapView
                    searchCenter={point}
                    searchRadiusMeters={radiusMeters}
                    facilities={facilities}
                    selectedFacilityId={selectedFacilityId}
                    onSelectFacility={(id) => selectFacility(id, { pan: false })}
                    onReturnToFlatView={() => setViewMode("regional")}
                    heightClassName="h-full"
                  />
                </Suspense>
              ) : (
                <MapView
                  origin={point}
                  originTitle="Search center"
                  facilities={facilities}
                  center={[point.lat, point.lon]}
                  zoom={mapZoom}
                  fitMode="point"
                  searchCenter={point}
                  searchRadiusMeters={radiusMeters}
                  accuracyCenter={gpsAccuracyMeters != null ? point : null}
                  accuracyRadiusMeters={gpsAccuracyMeters}
                  selectedFacilityId={selectedFacilityId}
                  onSelectFacility={(id) => selectFacility(id, { pan: false })}
                  focusTarget={focusTarget}
                  onViewportIdle={setViewportCenter}
                  heightClassName="h-full"
                />
              )}
            </div>
            {gpsAccuracyMeters != null && (
              <p className="mt-2 text-xs text-slate-400">
                GPS accuracy ≈ ±{Math.round(gpsAccuracyMeters)} m (blue dashed circle) — separate from the {formatRadius(radiusMeters)} search
                radius shown in navy.
              </p>
            )}

            <div className="mt-6">
              {showEmptyState ? (
                providerFailed ? (
                  <div className="rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-700">
                    <div className="flex items-start gap-3">
                      <AlertTriangle size={18} className="mt-0.5 shrink-0" />
                      <div>
                        <p className="font-medium">The facility provider didn't respond.</p>
                        <p className="mt-1 text-red-600">This is not a confirmed empty area — try again shortly.</p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl border border-slate-100 bg-slate-50 p-4 text-sm text-slate-600">
                    <span className="inline-flex items-center gap-2">
                      <SearchX size={18} className="shrink-0 text-slate-400" />
                      No facilities confirmed within {formatRadius(radiusMeters)} of {point.label}.
                    </span>
                    {nextRadius && (
                      <button
                        onClick={expandRadius}
                        className="mt-3 shrink-0 rounded-full border border-[#203C5A] px-3 py-1.5 text-xs font-medium text-[#203C5A] hover:bg-[#eaf1f7]"
                      >
                        Expand to {formatRadius(nextRadius)}
                      </button>
                    )}
                  </div>
                )
              ) : (
                <FacilityList
                  facilities={facilities}
                  emptyLabel="No facilities found in this radius."
                  selectedId={selectedFacilityId}
                  onSelect={(id) => selectFacility(id, { pan: true })}
                />
              )}
            </div>
          </>
        )}
      </section>
    </main>
  );
}
