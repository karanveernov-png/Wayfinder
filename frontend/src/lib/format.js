/**
 * Formatting / mapping helpers shared across pages. Keeps the
 * `data_status.mode`, `risk_assessment.level`, and facility
 * `verification_status` presentation rules from API_CONTRACT.md in one
 * place instead of duplicated per page.
 */

/** GeoJSON LineString ([lon, lat] pairs) -> Leaflet [lat, lon] pairs. Never skip this swap. */
export function geometryToLatLngs(geometry) {
  if (!geometry || geometry.type !== "LineString" || !Array.isArray(geometry.coordinates)) {
    return [];
  }
  return geometry.coordinates.map(([lon, lat]) => [lat, lon]);
}

export function coordToLatLng(coord) {
  if (!coord) return null;
  return [coord.lat, coord.lon];
}

export function formatDistance(km) {
  if (km === null || km === undefined) return "—";
  return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`;
}

export function formatDuration(minutes) {
  if (minutes === null || minutes === undefined) return "—";
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m} min`;
  return `${h} h ${m} min`;
}

/** "3 hours ago" / "2 days ago" / falls back to a locale date beyond ~a month. */
export function formatRelativeTime(isoString) {
  if (!isoString) return "—";
  const then = new Date(isoString).getTime();
  if (Number.isNaN(then)) return "—";
  const diffSeconds = Math.round((Date.now() - then) / 1000);
  if (diffSeconds < 60) return "just now";
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes} min ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 30) return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
  return new Date(isoString).toLocaleDateString();
}

export const DATA_STATUS_STYLES = {
  live: { label: "Live data", className: "bg-emerald-50 text-emerald-700" },
  partial: { label: "Partial data", className: "bg-amber-50 text-amber-700" },
  degraded: { label: "Degraded", className: "bg-red-50 text-red-700" },
  demo: { label: "Demo data", className: "bg-amber-50 text-amber-700" },
};

export function dataStatusStyle(mode) {
  return DATA_STATUS_STYLES[mode] || { label: mode || "Unknown", className: "bg-slate-100 text-slate-600" };
}

export const RISK_STYLES = {
  low: { label: "Low risk", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  moderate: { label: "Moderate risk", className: "bg-amber-50 text-amber-700 border-amber-200" },
  high: { label: "High risk", className: "bg-red-50 text-red-700 border-red-200" },
  unknown: { label: "Risk unknown", className: "bg-slate-100 text-slate-600 border-slate-200" },
};

export function riskStyle(level) {
  return RISK_STYLES[level] || RISK_STYLES.unknown;
}

/**
 * Resolve the origin/destination of a journey, accepting either shape in
 * use across the app:
 *  - the live JourneyAnalyseResponse (`journey.journey.origin` is a
 *    {display_name|query|resolved} object, risk level at
 *    `risk_assessment.level`), or
 *  - a saved-journey list row (`origin`/`destination` are plain strings,
 *    with the full response tucked under `journey_json` and the request
 *    params under `params_json`).
 *
 * Returns { origin, destination, originCoord, destCoord } where the coords
 * are {lat, lon} or null. Coords are preferred over names for sharing
 * because they resolve more reliably in a maps app.
 */
export function extractJourneyEndpoints(journey) {
  if (!journey) return { origin: "Origin", destination: "Destination", originCoord: null, destCoord: null };

  // Saved-journey list row: origin/destination are plain strings, and the
  // full analysed response (with coordinates) is nested under journey_json.
  if (typeof journey.origin === "string") {
    const nested = journey.journey_json?.journey;
    return {
      origin: journey.origin || "Origin",
      destination: journey.destination || "Destination",
      originCoord: nested?.origin?.resolved || null,
      destCoord: nested?.destination?.resolved || null,
    };
  }

  // Live JourneyAnalyseResponse returned from the API: endpoints are under
  // .journey. Handle it either way — the analyse endpoint wraps everything
  // in { journey: { ... } }, but internal calls / some tests keep the
  // inner shape flat on the caller side.
  const inner = journey.journey ?? journey;

  if (inner.origin || inner.destination) {
    return {
      origin: inner.origin?.display_name || inner.origin?.query || "Origin",
      destination: inner.destination?.display_name || inner.destination?.query || "Destination",
      originCoord: inner.origin?.resolved || null,
      destCoord: inner.destination?.resolved || null,
    };
  }

  return { origin: "Origin", destination: "Destination", originCoord: null, destCoord: null };
}

/**
 * Plain-text summary of a journey, for the Web Share API / clipboard.
 * Accepts either shape in use across the app: the live JourneyAnalyseResponse
 * (`journey.journey.origin` is a {display_name|query} object, risk level at
 * `risk_assessment.level`) or a saved-journey list row (`origin`/`destination`
 * are plain strings, risk level flat at `risk_level`).
 */
export function journeyShareText(journey) {
  if (!journey) return "";
  const { origin, destination } = extractJourneyEndpoints(journey);
  const parts = [`${origin} → ${destination}`];
  if (journey.distance_km != null) parts.push(formatDistance(journey.distance_km));
  if (journey.duration_minutes != null) parts.push(formatDuration(journey.duration_minutes));
  const level = journey.risk_assessment?.level || journey.risk_level;
  if (level) parts.push(riskStyle(level).label);
  return `Waymark journey: ${parts.join(" · ")}`;
}

/** Google Maps travel-mode values (the API's own enum, not OSRM's). */
const GOOGLE_MAPS_TRAVEL_MODES = {
  driving: "driving",
  "two-wheeler": "driving",
  cycling: "bicycling",
  transit: "transit",
};

/** Google Maps directions base URL (`/maps/dir/?api=1`). */
const GOOGLE_MAPS_DIRECTIONS_URL = "https://www.google.com/maps/dir/?api=1";

/**
 * Build a Google Maps directions link for a journey. The receiver only has
 * to tap the link for Google Maps to open with the route already loaded —
 * origin/destination coordinates are used when available (they resolve more
 * reliably than place names), falling back to the display names.
 *
 * Accepts the same shapes as journeyShareText(). `travelMode` is optional;
 * it defaults to "driving" or is read from a saved journey's params_json.
 */
export function journeyShareUrl(journey, travelMode) {
  if (!journey) return "";
  const { origin, destination, originCoord, destCoord } = extractJourneyEndpoints(journey);

  const params = new URLSearchParams({ api: "1" });
  if (originCoord?.lat != null && originCoord?.lon != null) {
    params.set("origin", `${originCoord.lat},${originCoord.lon}`);
  } else {
    params.set("origin", origin || "Origin");
  }
  if (destCoord?.lat != null && destCoord?.lon != null) {
    params.set("destination", `${destCoord.lat},${destCoord.lon}`);
  } else {
    params.set("destination", destination || "Destination");
  }

  const mode =
    GOOGLE_MAPS_TRAVEL_MODES[travelMode] || GOOGLE_MAPS_TRAVEL_MODES.driving;
  params.set("travelmode", mode);

  return `${GOOGLE_MAPS_DIRECTIONS_URL}&${params.toString()}`;
}

export const FACILITY_CATEGORY_LABELS = {
  hospital: "Hospital",
  fuel: "Fuel & charging",
  restaurant: "Restaurant & cafe",
  rest_stop: "Rest stop",
  pharmacy: "Pharmacy",
  lodging: "Lodging",
};

/** Per API_CONTRACT.md: a non-"verified" facility must never look identical to a confirmed pin. */
export function isFacilityVerified(facility) {
  return facility?.verification_status === "verified";
}

export function facilityVerificationLabel(status) {
  switch (status) {
    case "verified":
      return "Verified location";
    case "address_matched":
      return "Address-matched (not cross-checked)";
    case "unverified_coordinates":
      return "Approximate — unverified coordinates";
    case "unavailable":
      return "Location unavailable";
    default:
      return "Unverified";
  }
}

/** WMO weather codes (Open-Meteo) -> short description. */
const WMO_CODES = {
  0: "Clear sky",
  1: "Mainly clear",
  2: "Partly cloudy",
  3: "Overcast",
  45: "Fog",
  48: "Depositing rime fog",
  51: "Light drizzle",
  53: "Moderate drizzle",
  55: "Dense drizzle",
  61: "Slight rain",
  63: "Moderate rain",
  65: "Heavy rain",
  71: "Slight snow",
  73: "Moderate snow",
  75: "Heavy snow",
  80: "Slight rain showers",
  81: "Moderate rain showers",
  82: "Violent rain showers",
  95: "Thunderstorm",
  96: "Thunderstorm, slight hail",
  99: "Thunderstorm, heavy hail",
};

export function weatherCodeLabel(code) {
  if (code === null || code === undefined) return "Unknown conditions";
  return WMO_CODES[code] || `Weather code ${code}`;
}

export function isDemoAlert(alert) {
  if (!alert) return false;
  return alert.source === "demo-data" || (alert.description && alert.description.startsWith("[SIMULATED DEMO DATA"));
}

export const SEVERITY_STYLES = {
  low: "bg-slate-100 text-slate-600",
  moderate: "bg-amber-50 text-amber-700",
  high: "bg-red-50 text-red-700",
  unknown: "bg-slate-100 text-slate-600",
};
