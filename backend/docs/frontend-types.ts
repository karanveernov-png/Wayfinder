/**
 * Wayfinder API types - matches docs/API_CONTRACT.md v0.2.0 exactly.
 *
 * No frontend exists yet in this repository. These types are the exact
 * contract a React/TypeScript/Leaflet frontend should build against -
 * generated from the actual backend schemas (app/schemas/*.py), not
 * guessed. If the contract changes, this file and API_CONTRACT.md are
 * updated together (see API_CONTRACT.md "Changing the contract").
 *
 * COORDINATE WARNING: `Coordinates` is { lat, lon }. GeoJSON
 * `RouteGeometry.coordinates` is [lon, lat] pairs (per the GeoJSON spec) -
 * NOT the same order. Leaflet's LatLng wants [lat, lon]. Swap
 * `geometry.coordinates` pairs before passing to Leaflet; `Coordinates`
 * objects do not need swapping (just use [c.lat, c.lon]).
 */

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

export interface Coordinates {
  lat: number;
  lon: number;
}

export type SourceStatus = "ok" | "unavailable" | "error" | "not_configured";

export interface SourceMeta {
  name: string;
  status: SourceStatus;
  detail: string | null;
  /** ISO 8601 UTC, e.g. "2026-10-19T10:00:00Z". Present only when status === "ok". */
  retrieved_at: string | null;
}

export type DataStatusMode = "live" | "partial" | "degraded" | "demo";

export interface DataStatus {
  mode: DataStatusMode;
  sources: SourceMeta[];
}

/**
 * GeoJSON LineString. coordinates are [longitude, latitude] pairs - see the
 * COORDINATE WARNING at the top of this file.
 */
export interface RouteGeometry {
  type: "LineString";
  coordinates: [number, number][];
}

// ---------------------------------------------------------------------------
// Facilities
// ---------------------------------------------------------------------------

export type FacilityCategory = "hospital" | "fuel" | "restaurant" | "rest_stop";

/**
 * Confidence in a Facility's COORDINATES only. Never implies the facility
 * is open, operational, or has any particular capability (emergency
 * services, EV charging, CNG, etc.) - the backend never asserts those
 * unless a source explicitly provides them.
 */
export type FacilityVerificationStatus =
  | "verified" // from the designated authoritative source (currently: Overpass/OSM)
  | "address_matched" // from geocoding a text address, not independently cross-checked
  | "unverified_coordinates" // manual/approximate estimate (all current demo facilities)
  | "unavailable"; // no usable coordinates could be established

export interface Facility {
  id: string | null;
  name: string | null;
  category: FacilityCategory;
  coordinates: Coordinates;
  distance_km: number | null;
  address: string | null;
  source: string; // e.g. "overpass-osm" | "demo-deepak-directory"
  verification_status: FacilityVerificationStatus;
  coordinate_source: string | null;
  /** ISO 8601 UTC. Null for manually-estimated or unavailable coordinates. */
  last_verified_at: string | null;
}

export interface FacilitySearchResponse {
  query: Coordinates;
  radius_km: number;
  category: FacilityCategory | null;
  facilities: Facility[];
  data_status: DataStatus;
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export type AlertSeverity = "low" | "moderate" | "high" | "unknown";

export interface Alert {
  id: string | null;
  /**
   * Demo alerts ALWAYS start with the literal text
   * "[SIMULATED DEMO DATA — NOT a real incident report]" - check for this
   * prefix (or source === "demo-data") and render demo alerts visibly
   * differently from real ones.
   */
  description: string;
  category: string | null;
  severity: AlertSeverity;
  location: Coordinates | null;
  source: string;
  retrieved_at: string | null;
  verified: boolean | null;
  relevance: string | null;
}

export interface AlertSearchResponse {
  query: Coordinates;
  alerts: Alert[];
  data_status: DataStatus;
}

// ---------------------------------------------------------------------------
// Weather
// ---------------------------------------------------------------------------

export interface WeatherObservation {
  location: Coordinates;
  observation_time: string | null;
  temperature_c: number | null;
  windspeed_kmh: number | null;
  winddirection_deg: number | null;
  /** WMO weather code - see https://open-meteo.com/en/docs */
  weather_code: number | null;
  is_day: boolean | null;
  source: string; // "open-meteo"
}

export interface WeatherResponse {
  observation: WeatherObservation | null;
  data_status: DataStatus;
}

// ---------------------------------------------------------------------------
// Journey analysis
// ---------------------------------------------------------------------------

export type TravelMode = "driving"; // only mode currently supported

export interface JourneyAnalyseRequest {
  origin: string;
  destination: string;
  travel_mode?: TravelMode; // default "driving"
  include_facilities?: boolean; // default true
  include_alerts?: boolean; // default true
  facility_radius_km?: number; // default 5.0, (0, 50]
  facility_categories?: FacilityCategory[]; // default ["hospital", "fuel", "rest_stop"]
  /**
   * Set true to get the stored Chandigarh->Ludhiana demo response instead
   * of making any live provider calls. origin/destination are still
   * required by validation but are IGNORED when demo is true. See
   * API_CONTRACT.md "Demo mode".
   */
  demo?: boolean; // default false
}

export interface Location {
  query: string;
  resolved: Coordinates | null;
  display_name: string | null;
}

export interface JourneyPayload {
  origin: Location;
  destination: Location;
  distance_km: number | null;
  duration_minutes: number | null;
  geometry: RouteGeometry | null;
}

export type RiskLevel = "unknown" | "low" | "moderate" | "high";

export interface RiskAssessment {
  level: RiskLevel;
  /** 0-100, higher = more caution warranted. Null when level === "unknown". */
  score: number | null;
  reasons: string[];
}

export interface JourneyAnalyseResponse {
  journey: JourneyPayload;
  facilities: Facility[];
  alerts: Alert[];
  /**
   * 0-3 weather observations at points sampled along the route
   * (origin/midpoint/destination) - a limited SAMPLE, not a comprehensive
   * forecast. Empty if weather was unavailable, not requested, or (always,
   * currently) in demo mode.
   */
  weather_samples: WeatherObservation[];
  risk_assessment: RiskAssessment;
  recommendations: string[];
  data_status: DataStatus;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/**
 * This NEVER represents an upstream provider failure (those are always a
 * 200 with data_status - see "Why always 200?" in API_CONTRACT.md). This
 * shape is only for client-input/validation errors and genuine server bugs.
 */
export interface ApiErrorResponse {
  error: {
    code:
      | "VALIDATION_ERROR"
      | "BAD_REQUEST"
      | "NOT_FOUND"
      | "METHOD_NOT_ALLOWED"
      | "RATE_LIMITED"
      | "INTERNAL_ERROR"
      | "HTTP_ERROR";
    message: string;
    /** Present only for VALIDATION_ERROR - FastAPI/Pydantic's standard error-list shape. */
    details?: Array<{
      type: string;
      loc: (string | number)[];
      msg: string;
      input: unknown;
    }>;
  };
}

// ---------------------------------------------------------------------------
// Minimal fetch helpers (adapt to your actual HTTP client / base URL config)
// ---------------------------------------------------------------------------

const API_BASE = "/api/v1"; // adjust to your deployment (e.g. import.meta.env.VITE_API_BASE)

export async function analyseJourney(
  req: JourneyAnalyseRequest,
): Promise<JourneyAnalyseResponse | ApiErrorResponse> {
  const res = await fetch(`${API_BASE}/journeys/analyse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return res.json();
}

export async function fetchNearbyFacilities(
  lat: number,
  lon: number,
  radiusKm = 5,
  category?: FacilityCategory,
): Promise<FacilitySearchResponse> {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon), radius_km: String(radiusKm) });
  if (category) params.set("category", category);
  const res = await fetch(`${API_BASE}/facilities/nearby?${params}`);
  return res.json();
}

export async function fetchWeather(lat: number, lon: number): Promise<WeatherResponse> {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
  const res = await fetch(`${API_BASE}/weather?${params}`);
  return res.json();
}

export async function fetchAlerts(
  lat: number,
  lon: number,
  radiusKm = 25,
): Promise<AlertSearchResponse> {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon), radius_km: String(radiusKm) });
  const res = await fetch(`${API_BASE}/alerts?${params}`);
  return res.json();
}

/** Type guard: distinguishes the error envelope from a success response. */
export function isApiError(body: unknown): body is ApiErrorResponse {
  return typeof body === "object" && body !== null && "error" in body;
}
