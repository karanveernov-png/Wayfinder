/**
 * Wayfinder API client.
 *
 * Mirrors the contract in wayfinder-backend/backend/docs/API_CONTRACT.md
 * (v0.2.0) and docs/frontend-types.ts. Every function returns the parsed
 * JSON body on success and throws an `ApiError` on a non-2xx response or
 * network failure — callers should wrap calls in try/catch.
 *
 * Base URL comes from VITE_API_BASE_URL (see .env.example); defaults to a
 * local backend running on port 8000.
 */

import { supabase } from "./supabase.js";

// Optional chaining on import.meta.env: see the comment in supabase.js —
// import.meta.env is undefined under plain Node (no Vite), which otherwise
// crashes this module on import rather than just falling through to the
// default below.
const API_BASE = (
  import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, { code, status, details } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code || "UNKNOWN";
    this.status = status ?? null;
    this.details = details || null;
  }
}

async function getAuthHeaders() {
  try {
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token
      ? { Authorization: `Bearer ${session.access_token}` }
      : {};
  } catch (error) {
    // If there's an error getting the session, return empty headers
    // This will result in a 401 Unauthorized response from the server
    return {};
  }
}

async function request(path, options = {}) {
  const authHeaders = await getAuthHeaders();
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...authHeaders },
      ...options,
    });
  } catch (error) {
    // Network failure, CORS block, backend not running, etc.
    throw new ApiError(
      error instanceof TypeError ?
        "Could not reach the Wayfinder API. Is the backend running?" :
        "Network error: " + error.message,
      { code: "NETWORK_ERROR" }
    );
  }

  let body = null;
  try {
    body = await res.json();
  } catch {
    // Non-JSON body (e.g. a proxy error page) — fall through, body stays null.
  }

  if (!res.ok) {
    const envelope = body?.error;
    const message = envelope?.message || `Request failed (${res.status}).`;
    // Add helpful context for common auth failures
    const hint = res.status === 401
      ? " You may need to log in again. Try refreshing the page or signing out and back in."
      : "";
    throw new ApiError(message + hint, {
      code: envelope?.code || "HTTP_ERROR",
      status: res.status,
      details: envelope?.details || null,
    });
  }

  return body;
}

/** POST /journeys/analyse — the primary endpoint: routing, facilities, weather, alerts, risk. */
export function analyseJourney({
  origin,
  destination,
  originCoordinates,
  destinationCoordinates,
  travelMode = "driving",
  includeFacilities = true,
  includeAlerts = true,
  facilityRadiusKm = 5.0,
  facilityCategories,
  demo = false,
} = {}) {
  const body = {
    origin,
    destination,
    travel_mode: travelMode,
    include_facilities: includeFacilities,
    include_alerts: includeAlerts,
    facility_radius_km: facilityRadiusKm,
    demo,
  };
  if (originCoordinates) body.origin_coordinates = originCoordinates;
  if (destinationCoordinates) body.destination_coordinates = destinationCoordinates;
  if (facilityCategories) body.facility_categories = facilityCategories;

  return request("/journeys/analyse", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * POST /trip-intent/plan — natural-language trip planning. The backend
 * uses Groq to turn `message` into the same structured parameters
 * analyseJourney() above accepts, then runs the exact same journey
 * pipeline. Response shape: { status: "ok"|"needs_clarification"|"error",
 * intent, message, journey }. `journey` (present only when status=="ok")
 * is the exact same JourneyAnalyseResponse analyseJourney() returns.
 */
export function planTripFromText({ message, signal } = {}) {
  return request("/trip-intent/plan", {
    method: "POST",
    body: JSON.stringify({ message }),
    signal,
  });
}

/** POST /journeys/compare-routes — alternate routes with a risk/weather assessment per route. */
export function compareRoutes({
  origin,
  destination,
  originCoordinates,
  destinationCoordinates,
  travelMode = "driving",
  maxAlternatives = 3,
  signal,
} = {}) {
  const body = {
    origin,
    destination,
    travel_mode: travelMode,
    max_alternatives: maxAlternatives,
  };
  if (originCoordinates) body.origin_coordinates = originCoordinates;
  if (destinationCoordinates) body.destination_coordinates = destinationCoordinates;

  return request("/journeys/compare-routes", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

/** GET /facilities/nearby — single-point facility search (no route sampling). */
export function fetchNearbyFacilities({ lat, lon, radiusKm = 5, category } = {}) {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    radius_km: String(radiusKm),
  });
  if (category && category !== "all") params.set("category", category);
  return request(`/facilities/nearby?${params}`);
}

/** GET /weather — single-point current weather. */
export function fetchWeather({ lat, lon } = {}) {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
  return request(`/weather?${params}`);
}

/** GET /alerts — travel alerts near a point (currently always not_configured; see contract). */
export function fetchAlerts({ lat, lon, radiusKm = 25 } = {}) {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    radius_km: String(radiusKm),
  });
  return request(`/alerts?${params}`);
}

/**
 * GET /locations/suggest — location autocomplete / misspelling /
 * disambiguation suggestions for an origin or destination field (see
 * docs/LOCATION_AUTOCOMPLETE_GUIDE.md at the repo root). Pass `signal` from
 * useAbortableRequest so an in-flight request is cancelled when the user
 * keeps typing. Response shape: { query, suggestions: [...],
 * used_fallback, data_status }.
 */
export function suggestLocations({ query, limit = 6, signal } = {}) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return request(`/locations/suggest?${params}`, { signal });
}

/** GET /health — basic liveness check. */
export function checkHealth() {
  return request("/health");
}

/** POST /saved-journeys — save a journey for the authenticated user. */
export async function saveJourney(data) {
  return request("/saved-journeys", { method: "POST", body: JSON.stringify(data) });
}

/** GET /saved-journeys — list saved journeys for the authenticated user. */
export async function listSavedJourneys() {
  return request("/saved-journeys");
}

/** GET /saved-journeys/:id — get a single saved journey. */
export async function getSavedJourney(id) {
  return request(`/saved-journeys/${id}`);
}

/** DELETE /saved-journeys/:id — delete a saved journey. */
export async function deleteSavedJourney(id) {
  return request(`/saved-journeys/${id}`, { method: "DELETE" });
}

export const FACILITY_CATEGORIES = ["hospital", "fuel", "restaurant", "rest_stop"];
