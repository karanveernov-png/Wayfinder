/**
 * Lightweight, dependency-free tests for the geo helpers.
 *
 * These files use ESM (`import`), so they run through Node's built-in ESM
 * loader. They cover the radius contract that the Nearby Places page and
 * the backend's /facilities/nearby endpoint both depend on.
 *
 * Run with:  node --test tests/geo.test.js
 */
import assert from "node:assert";
import { test } from "node:test";
import {
  metersToKm,
  formatRadius,
  zoomForRadiusMeters,
  isValidLatLng,
  isValidPoint,
  RADIUS_PRESETS_M,
  MIN_RADIUS_M,
  MAX_RADIUS_M,
  clampRadiusMeters,
  VIEW_MODE_THRESHOLDS_M,
  viewModeForRadiusMeters,
  circlePolygonCoords,
  haversineMeters,
} from "../src/lib/geo.js";

// ---- metersToKm: the radius contract -------------------------------
test("metersToKm maps the four preset radii to exact radius_km values", () => {
  assert.strictEqual(metersToKm(200), 0.2);
  assert.strictEqual(metersToKm(300), 0.3);
  assert.strictEqual(metersToKm(500), 0.5);
  assert.strictEqual(metersToKm(1000), 1.0);
});

test("metersToKm preserves fractional metres (no truncation)", () => {
  assert.strictEqual(metersToKm(1234), 1.234);
  assert.strictEqual(metersToKm(150), 0.15);
});

test("metersToKm returns 0 for 0 metres", () => {
  assert.strictEqual(metersToKm(0), 0);
});

// ---- formatRadius: human-readable labels ---------------------------
test("formatRadius renders metres and kilometres correctly", () => {
  assert.strictEqual(formatRadius(200), "200 m");
  assert.strictEqual(formatRadius(300), "300 m");
  assert.strictEqual(formatRadius(500), "500 m");
  assert.strictEqual(formatRadius(1000), "1 km");
  assert.strictEqual(formatRadius(1500), "1.5 km");
});

// ---- zoomForRadiusMeters: sane zoom for each preset -----------------
test("zoomForRadiusMeters stays within the 3..18 Leaflet range", () => {
  for (const m of [200, 300, 500, 1000]) {
    const z = zoomForRadiusMeters(m, 30.73);
    assert.ok(Number.isInteger(z), `zoom for ${m} m is an integer`);
    assert.ok(z >= 3 && z <= 18, `zoom for ${m} m (${z}) is within 3..18`);
  }
});

test("zoomForRadiusMeters zooms in for smaller radii", () => {
  assert.ok(zoomForRadiusMeters(200, 30.73) > zoomForRadiusMeters(1000, 30.73));
});

test("zoomForRadiusMeters clamps defensively for invalid input", () => {
  assert.strictEqual(zoomForRadiusMeters(0), 15);
  assert.strictEqual(zoomForRadiusMeters(-50), 15);
  assert.strictEqual(zoomForRadiusMeters(300, 91), zoomForRadiusMeters(300, 85));
});

// ---- coordinate validation ------------------------------------------
test("isValidLatLng accepts valid coordinates and rejects invalid ones", () => {
  assert.strictEqual(isValidLatLng(30.73, 76.77), true);
  assert.strictEqual(isValidLatLng(0, 0), true);
  assert.strictEqual(isValidLatLng(90, 180), true);
  assert.strictEqual(isValidLatLng(-90, -180), true);
  assert.strictEqual(isValidLatLng(91, 0), false);
  assert.strictEqual(isValidLatLng(0, 181), false);
  assert.strictEqual(isValidLatLng(NaN, 0), false);
  assert.strictEqual(isValidLatLng(30.73, Infinity), false);
});

test("isValidPoint rejects null/undefined and malformed points", () => {
  assert.strictEqual(isValidPoint({ lat: 30.73, lon: 76.77 }), true);
  assert.strictEqual(isValidPoint(null), false);
  assert.strictEqual(isValidPoint(undefined), false);
  assert.strictEqual(isValidPoint({ lat: 30.73, lon: "x" }), false);
});

// ---- RADIUS_PRESETS_M: the full 200m-70km contract -------------------
test("RADIUS_PRESETS_M spans 200m through 70km with the specified presets", () => {
  assert.deepStrictEqual(RADIUS_PRESETS_M, [
    200, 300, 500, 1000, 2000, 5000, 10000, 20000, 50000, 70000,
  ]);
  assert.strictEqual(MIN_RADIUS_M, 200);
  assert.strictEqual(MAX_RADIUS_M, 70000);
  assert.strictEqual(RADIUS_PRESETS_M[0], MIN_RADIUS_M);
  assert.strictEqual(RADIUS_PRESETS_M[RADIUS_PRESETS_M.length - 1], MAX_RADIUS_M);
});

// ---- clampRadiusMeters: boundary enforcement --------------------------
test("clampRadiusMeters passes through in-range values unchanged", () => {
  assert.strictEqual(clampRadiusMeters(200), 200);
  assert.strictEqual(clampRadiusMeters(1000), 1000);
  assert.strictEqual(clampRadiusMeters(20000), 20000);
  assert.strictEqual(clampRadiusMeters(50000), 50000);
  assert.strictEqual(clampRadiusMeters(70000), 70000);
});

test("clampRadiusMeters clamps below-minimum and negative values up to MIN_RADIUS_M", () => {
  assert.strictEqual(clampRadiusMeters(0), MIN_RADIUS_M);
  assert.strictEqual(clampRadiusMeters(-50), MIN_RADIUS_M);
  assert.strictEqual(clampRadiusMeters(199), MIN_RADIUS_M);
});

test("clampRadiusMeters clamps above-maximum values down to MAX_RADIUS_M", () => {
  assert.strictEqual(clampRadiusMeters(70001), MAX_RADIUS_M);
  assert.strictEqual(clampRadiusMeters(1000000), MAX_RADIUS_M);
});

test("clampRadiusMeters falls back to the default for non-finite input", () => {
  assert.strictEqual(clampRadiusMeters(NaN), 300);
  assert.strictEqual(clampRadiusMeters(undefined), 300);
  assert.strictEqual(clampRadiusMeters(Infinity), 300);
});

// ---- viewModeForRadiusMeters: street/regional/globe thresholds --------
test("viewModeForRadiusMeters picks street at and below the street threshold", () => {
  assert.strictEqual(viewModeForRadiusMeters(200), "street");
  assert.strictEqual(viewModeForRadiusMeters(500), "street");
  assert.strictEqual(viewModeForRadiusMeters(VIEW_MODE_THRESHOLDS_M.streetMaxM), "street");
});

test("viewModeForRadiusMeters picks regional between the street and regional thresholds", () => {
  assert.strictEqual(viewModeForRadiusMeters(VIEW_MODE_THRESHOLDS_M.streetMaxM + 1), "regional");
  assert.strictEqual(viewModeForRadiusMeters(5000), "regional");
  assert.strictEqual(viewModeForRadiusMeters(VIEW_MODE_THRESHOLDS_M.regionalMaxM), "regional");
});

test("viewModeForRadiusMeters picks globe above the regional threshold, up to 70km", () => {
  assert.strictEqual(viewModeForRadiusMeters(VIEW_MODE_THRESHOLDS_M.regionalMaxM + 1), "globe");
  assert.strictEqual(viewModeForRadiusMeters(50000), "globe");
  assert.strictEqual(viewModeForRadiusMeters(70000), "globe");
});

test("viewModeForRadiusMeters defaults to street for invalid input", () => {
  assert.strictEqual(viewModeForRadiusMeters(0), "street");
  assert.strictEqual(viewModeForRadiusMeters(-100), "street");
  assert.strictEqual(viewModeForRadiusMeters(NaN), "street");
});

// ---- zoomForRadiusMeters: extended range up to 70km --------------------
test("zoomForRadiusMeters stays within the 3..18 range across the full 200m-70km contract", () => {
  for (const m of RADIUS_PRESETS_M) {
    const z = zoomForRadiusMeters(m, 30.73);
    assert.ok(Number.isInteger(z), `zoom for ${m} m is an integer`);
    assert.ok(z >= 3 && z <= 18, `zoom for ${m} m (${z}) is within 3..18`);
  }
});

test("zoomForRadiusMeters monotonically zooms out as radius grows across the full contract", () => {
  for (let i = 1; i < RADIUS_PRESETS_M.length; i++) {
    const prevZoom = zoomForRadiusMeters(RADIUS_PRESETS_M[i - 1], 30.73);
    const zoom = zoomForRadiusMeters(RADIUS_PRESETS_M[i], 30.73);
    assert.ok(zoom <= prevZoom, `zoom for ${RADIUS_PRESETS_M[i]}m should not exceed zoom for ${RADIUS_PRESETS_M[i - 1]}m`);
  }
});

// ---- circlePolygonCoords: geodesic circle for the GlobeMapView ---------
test("circlePolygonCoords returns a closed ring of [lon, lat] pairs", () => {
  const ring = circlePolygonCoords(30.73, 76.77, 20000, 8);
  assert.strictEqual(ring.length, 9); // 8 steps + closing point
  const [firstLon, firstLat] = ring[0];
  const [lastLon, lastLat] = ring[ring.length - 1];
  assert.ok(Math.abs(firstLon - lastLon) < 1e-6, "ring should close (lon)");
  assert.ok(Math.abs(firstLat - lastLat) < 1e-6, "ring should close (lat)");
  for (const [lon, lat] of ring) {
    assert.ok(isValidLatLng(lat, lon), `(${lat}, ${lon}) should be a valid coordinate`);
  }
});

test("circlePolygonCoords points sit approximately radiusMeters from the center", () => {
  const center = { lat: 30.73, lon: 76.77 };
  const radiusMeters = 70000;
  const ring = circlePolygonCoords(center.lat, center.lon, radiusMeters, 16);
  const EARTH_RADIUS_M = 6371008.8;
  for (const [lon, lat] of ring.slice(0, -1)) {
    // Haversine distance from center to this ring point, mirroring the
    // backend's own _haversine_km formula so both sides agree on "distance".
    const toRad = (d) => (d * Math.PI) / 180;
    const dLat = toRad(lat - center.lat);
    const dLon = toRad(lon - center.lon);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(center.lat)) * Math.cos(toRad(lat)) * Math.sin(dLon / 2) ** 2;
    const distance = 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a));
    assert.ok(Math.abs(distance - radiusMeters) < 50, `ring point should be ~${radiusMeters}m away, got ${distance}m`);
  }
});

test("circlePolygonCoords returns an empty array for invalid input", () => {
  assert.deepStrictEqual(circlePolygonCoords(NaN, 76.77, 1000), []);
  assert.deepStrictEqual(circlePolygonCoords(30.73, 76.77, 0), []);
  assert.deepStrictEqual(circlePolygonCoords(30.73, 76.77, -500), []);
  assert.deepStrictEqual(circlePolygonCoords(999, 76.77, 1000), []);
});

// ---- haversineMeters: distance check behind the "Search this area" button
test("haversineMeters returns ~0 for the same point", () => {
  const p = { lat: 30.73, lon: 76.77 };
  assert.ok(haversineMeters(p, p) < 1e-6);
});

test("haversineMeters agrees with circlePolygonCoords' own ring distance", () => {
  // A ring point generated at exactly radiusMeters from the center should
  // measure back as ~radiusMeters via this same formula.
  const center = { lat: 30.73, lon: 76.77 };
  const radiusMeters = 5000;
  const [ring0] = circlePolygonCoords(center.lat, center.lon, radiusMeters, 8);
  const [lon, lat] = ring0;
  const distance = haversineMeters(center, { lat, lon });
  assert.ok(Math.abs(distance - radiusMeters) < 50, `expected ~${radiusMeters}m, got ${distance}m`);
});

test("haversineMeters returns Infinity for an invalid point", () => {
  assert.strictEqual(haversineMeters({ lat: 30.73, lon: 76.77 }, null), Infinity);
  assert.strictEqual(haversineMeters(null, { lat: 30.73, lon: 76.77 }), Infinity);
  assert.strictEqual(haversineMeters({ lat: 999, lon: 76.77 }, { lat: 30.73, lon: 76.77 }), Infinity);
});
