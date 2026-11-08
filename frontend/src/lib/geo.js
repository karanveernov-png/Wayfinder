/**
 * Small geo helpers shared by the Nearby Places page, MapView and
 * GlobeMapView.
 *
 * Keeps radius state in metres everywhere in the frontend; the backend's
 * `radius_km` query parameter is a derived value computed only at the API
 * boundary (see metersToKm below), never stored as frontend state.
 *
 * This file is the SINGLE source of truth for the radius contract (200 m -
 * 70 km) and the automatic street/regional/globe view-mode thresholds, so
 * the preset list, the min/max bounds and the thresholds are never
 * duplicated (and able to drift out of sync) elsewhere in the frontend.
 * The backend enforces its own copy of the min/max bounds independently
 * (see backend/app/core/config.py MIN_FACILITY_RADIUS_KM /
 * MAX_FACILITY_RADIUS_KM) - this module cannot import Python settings, so
 * keep the two in sync by hand if either changes.
 */

/** Full set of selectable radii for the Nearby Places radius control, in metres. */
export const RADIUS_PRESETS_M = [
  200, 300, 500, 1000, 2000, 5000, 10000, 20000, 50000, 70000,
];

/** Deprecated alias kept for compatibility with any existing imports. */
export const NEARBY_RADIUS_PRESETS_M = RADIUS_PRESETS_M;

export const DEFAULT_NEARBY_RADIUS_M = 300;

/** Hard bounds for the radius control - mirrors the backend's validation. */
export const MIN_RADIUS_M = 200;
export const MAX_RADIUS_M = 70000;

/** Clamps an arbitrary metres value into the supported [MIN_RADIUS_M, MAX_RADIUS_M] range. */
export function clampRadiusMeters(meters) {
  if (!Number.isFinite(meters)) return DEFAULT_NEARBY_RADIUS_M;
  return Math.min(MAX_RADIUS_M, Math.max(MIN_RADIUS_M, meters));
}

/**
 * Automatic view-mode thresholds, in metres. Configurable in one place:
 * <= streetMaxM -> "street", <= regionalMaxM -> "regional", above that -> "globe".
 * Matches the proposed thresholds (street 200m-1km, regional 1-20km, globe
 * 20-70km); change these two numbers to retune the whole app.
 */
export const VIEW_MODE_THRESHOLDS_M = {
  streetMaxM: 1000,
  regionalMaxM: 20000,
};

/** Picks the automatic view mode ("street" | "regional" | "globe") for a given radius. */
export function viewModeForRadiusMeters(radiusMeters) {
  if (!Number.isFinite(radiusMeters) || radiusMeters <= 0) return "street";
  if (radiusMeters <= VIEW_MODE_THRESHOLDS_M.streetMaxM) return "street";
  if (radiusMeters <= VIEW_MODE_THRESHOLDS_M.regionalMaxM) return "regional";
  return "globe";
}

const EARTH_RADIUS_M = 6371008.8; // IUGG mean Earth radius - same constant used by _haversine_km on the backend

/**
 * Great-circle "destination point given distance and bearing" formula,
 * walked around a full 360° to approximate a geodesic circle of the given
 * radius around (lat, lon). Returns a closed ring of [lon, lat] pairs
 * (GeoJSON coordinate order) suitable for a MapLibre GeoJSON polygon
 * source - this is what GlobeMapView draws the search-radius circle with,
 * since MapLibre (unlike Leaflet) has no built-in L.circle primitive.
 *
 * Uses the real spherical formula rather than a flat equirectangular
 * offset, since at 70 km radius and away from the equator a flat
 * approximation visibly distorts into an ellipse.
 */
export function circlePolygonCoords(lat, lon, radiusMeters, steps = 64) {
  if (!isValidLatLng(lat, lon) || !Number.isFinite(radiusMeters) || radiusMeters <= 0) {
    return [];
  }
  const latRad = (lat * Math.PI) / 180;
  const lonRad = (lon * Math.PI) / 180;
  const angular = radiusMeters / EARTH_RADIUS_M;
  const coords = [];
  for (let i = 0; i <= steps; i++) {
    const bearing = (i * 2 * Math.PI) / steps;
    const destLat = Math.asin(
      Math.sin(latRad) * Math.cos(angular) + Math.cos(latRad) * Math.sin(angular) * Math.cos(bearing)
    );
    const destLon =
      lonRad +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angular) * Math.cos(latRad),
        Math.cos(angular) - Math.sin(latRad) * Math.sin(destLat)
      );
    coords.push([(destLon * 180) / Math.PI, (destLat * 180) / Math.PI]);
  }
  return coords;
}

/** Great-circle distance between two {lat, lon} points, in meters. */
export function haversineMeters(a, b) {
  if (!isValidPoint(a) || !isValidPoint(b)) return Infinity;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
}

/** Metres -> kilometres, rounded to avoid floating-point noise in the query string. */
export function metersToKm(meters) {
  return Math.round(meters * 100) / 100000;
}

export function formatRadius(meters) {
  return meters >= 1000 ? `${(meters / 1000).toFixed(meters % 1000 === 0 ? 0 : 1)} km` : `${meters} m`;
}

/**
 * Pick a Leaflet zoom level that comfortably frames a circle of the given
 * radius around a point, so a 200 m search doesn't render at a city-wide
 * zoom and a 1 km search doesn't render at a street-level zoom.
 *
 * Uses the standard Web Mercator "metres per pixel" relationship
 * (156543.03392 m/px at zoom 0 on the equator, halving per zoom level,
 * scaled by cos(latitude) away from the equator) and solves for the zoom
 * at which the radius occupies a fixed, comfortable pixel budget. This is
 * a formula over the four presets, not a lookup table, so it degrades
 * sensibly if the radius or location ever changes.
 */
export function zoomForRadiusMeters(radiusMeters, latDeg = 0) {
  if (!Number.isFinite(radiusMeters) || radiusMeters <= 0) return 15;
  const TARGET_PIXEL_RADIUS = 140; // keep the circle well inside a ~400-500px map, clear of controls
  const metersPerPixelAtZoom0 = 156543.03392 * Math.cos((clampLat(latDeg) * Math.PI) / 180);
  const idealMetersPerPixel = radiusMeters / TARGET_PIXEL_RADIUS;
  const zoom = Math.log2(metersPerPixelAtZoom0 / idealMetersPerPixel);
  return Math.min(18, Math.max(3, Math.round(zoom)));
}

function clampLat(lat) {
  // cos(lat) blows up near the poles; nothing in this app's domain is near them,
  // but clamp defensively so a bad value can't produce a nonsensical zoom.
  return Math.max(-85, Math.min(85, lat));
}

export function isFiniteCoord(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function isValidLatLng(lat, lon) {
  return isFiniteCoord(lat) && isFiniteCoord(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}

export function isValidPoint(point) {
  return !!point && isValidLatLng(point.lat, point.lon);
}
