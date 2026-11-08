/**
 * Tests for src/lib/api.js — request construction, query/body
 * serialization, auth header injection, and error handling.
 *
 * Before this file existed, api.js had zero test coverage: a file named
 * tests/api.test.js existed but actually tested format.js (now renamed to
 * tests/format.test.js), and api.js could not even be imported under plain
 * Node — `import.meta.env` is undefined outside Vite, and the unguarded
 * `import.meta.env.VITE_API_BASE_URL` / `...SUPABASE_URL` property access
 * (in api.js and the supabase.js it imports) threw on import. Both were
 * changed to optional chaining (`import.meta.env?.X`) as part of this same
 * audit, which is what makes this file possible.
 *
 * supabase.js is replaced with node:test's mock.module() (requires
 * --experimental-test-module-mocks, set in package.json's "test" script)
 * so these tests never touch a real Supabase client or network.
 *
 * Run with: node --experimental-test-module-mocks --test tests/api.test.js
 */

import assert from "node:assert";
import { test, before, beforeEach, afterEach, mock } from "node:test";

let mockSession = null;

before(() => {
  mock.module("../src/lib/supabase.js", {
    namedExports: {
      isSupabaseConfigured: false,
      supabase: {
        auth: {
          getSession: async () => ({ data: { session: mockSession } }),
        },
      },
    },
  });
});

let api;
before(async () => {
  api = await import("../src/lib/api.js");
});

let originalFetch;
let fetchCalls;

beforeEach(() => {
  mockSession = null;
  fetchCalls = [];
  originalFetch = globalThis.fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

/** Installs a fetch stub that records every call and returns `response`. */
function stubFetch(response) {
  globalThis.fetch = async (url, options) => {
    fetchCalls.push({ url, options });
    return response;
  };
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

// ---- Query-parameter construction (the radius pipeline) -----------------

test("fetchNearbyFacilities sends radius_km=0.2 as a query param for a 200m search", async () => {
  stubFetch(jsonResponse(200, { facilities: [] }));
  await api.fetchNearbyFacilities({ lat: 30.7, lon: 76.7, radiusKm: 0.2, category: "hospital" });

  assert.strictEqual(fetchCalls.length, 1);
  const url = new URL(fetchCalls[0].url);
  assert.strictEqual(url.pathname, "/api/v1/facilities/nearby");
  assert.strictEqual(url.searchParams.get("radius_km"), "0.2");
  assert.strictEqual(url.searchParams.get("lat"), "30.7");
  assert.strictEqual(url.searchParams.get("lon"), "76.7");
  assert.strictEqual(url.searchParams.get("category"), "hospital");
});

test("fetchNearbyFacilities omits category when it is 'all'", async () => {
  stubFetch(jsonResponse(200, { facilities: [] }));
  await api.fetchNearbyFacilities({ lat: 1, lon: 2, radiusKm: 5, category: "all" });
  const url = new URL(fetchCalls[0].url);
  assert.strictEqual(url.searchParams.has("category"), false);
});

test("fetchNearbyFacilities defaults radiusKm to 5 when not provided", async () => {
  stubFetch(jsonResponse(200, { facilities: [] }));
  await api.fetchNearbyFacilities({ lat: 1, lon: 2 });
  const url = new URL(fetchCalls[0].url);
  assert.strictEqual(url.searchParams.get("radius_km"), "5");
});

test("fetchNearbyFacilities forwards a fractional km value for every supported radius preset", async () => {
  // 200m, 300m, 500m, 1km, 5km, 20km, 50km, 70km — mirrors geo.js's
  // metersToKm() outputs for the frontend's radius presets.
  const presets = [0.2, 0.3, 0.5, 1.0, 5.0, 20.0, 50.0, 70.0];
  for (const radiusKm of presets) {
    fetchCalls.length = 0;
    stubFetch(jsonResponse(200, { facilities: [] }));
    await api.fetchNearbyFacilities({ lat: 1, lon: 2, radiusKm });
    const url = new URL(fetchCalls[0].url);
    assert.strictEqual(
      url.searchParams.get("radius_km"),
      String(radiusKm),
      `radiusKm=${radiusKm} should be sent verbatim, not rounded/truncated`
    );
  }
});

test("fetchAlerts defaults radiusKm to 25", async () => {
  stubFetch(jsonResponse(200, { alerts: [] }));
  await api.fetchAlerts({ lat: 1, lon: 2 });
  const url = new URL(fetchCalls[0].url);
  assert.strictEqual(url.searchParams.get("radius_km"), "25");
});

test("fetchWeather sends only lat/lon", async () => {
  stubFetch(jsonResponse(200, {}));
  await api.fetchWeather({ lat: 30.7, lon: 76.7 });
  const url = new URL(fetchCalls[0].url);
  assert.strictEqual(url.pathname, "/api/v1/weather");
  assert.deepStrictEqual([...url.searchParams.keys()].sort(), ["lat", "lon"]);
});

test("suggestLocations sends q and limit, forwards the abort signal", async () => {
  stubFetch(jsonResponse(200, { suggestions: [] }));
  const controller = new AbortController();
  await api.suggestLocations({ query: "Chandig", limit: 3, signal: controller.signal });
  const url = new URL(fetchCalls[0].url);
  assert.strictEqual(url.searchParams.get("q"), "Chandig");
  assert.strictEqual(url.searchParams.get("limit"), "3");
  assert.strictEqual(fetchCalls[0].options.signal, controller.signal);
});

// ---- Request body construction -------------------------------------------

test("analyseJourney sends snake_case keys and a numeric facility_radius_km", async () => {
  stubFetch(jsonResponse(200, {}));
  await api.analyseJourney({
    origin: "Chandigarh",
    destination: "Ludhiana",
    facilityRadiusKm: 0.2,
    includeFacilities: true,
    includeAlerts: false,
  });
  const sent = JSON.parse(fetchCalls[0].options.body);
  assert.strictEqual(sent.facility_radius_km, 0.2);
  assert.strictEqual(typeof sent.facility_radius_km, "number");
  assert.strictEqual(sent.include_facilities, true);
  assert.strictEqual(sent.include_alerts, false);
  assert.strictEqual(sent.origin, "Chandigarh");
  assert.strictEqual(sent.destination, "Ludhiana");
  assert.strictEqual("origin_coordinates" in sent, false);
});

test("analyseJourney includes coordinates only when provided", async () => {
  stubFetch(jsonResponse(200, {}));
  await api.analyseJourney({
    origin: "A",
    destination: "B",
    originCoordinates: { lat: 1, lon: 2 },
  });
  const sent = JSON.parse(fetchCalls[0].options.body);
  assert.deepStrictEqual(sent.origin_coordinates, { lat: 1, lon: 2 });
  assert.strictEqual("destination_coordinates" in sent, false);
});

// ---- Auth header injection -------------------------------------------

test("request includes no Authorization header when there is no session", async () => {
  mockSession = null;
  stubFetch(jsonResponse(200, {}));
  await api.checkHealth();
  assert.strictEqual("Authorization" in fetchCalls[0].options.headers, false);
});

test("request includes a Bearer Authorization header when a session exists", async () => {
  mockSession = { access_token: "test-access-token" };
  stubFetch(jsonResponse(200, {}));
  await api.listSavedJourneys();
  assert.strictEqual(
    fetchCalls[0].options.headers.Authorization,
    "Bearer test-access-token"
  );
});

// ---- Error handling -------------------------------------------

test("a non-2xx JSON error envelope becomes an ApiError with code/status/details", async () => {
  stubFetch(
    jsonResponse(422, {
      error: { code: "VALIDATION_ERROR", message: "radius too small", details: { field: "radius_km" } },
    })
  );
  await assert.rejects(
    () => api.fetchNearbyFacilities({ lat: 1, lon: 2, radiusKm: 0.001 }),
    (err) => {
      assert.strictEqual(err.name, "ApiError");
      assert.strictEqual(err.code, "VALIDATION_ERROR");
      assert.strictEqual(err.status, 422);
      assert.strictEqual(err.message, "radius too small");
      assert.deepStrictEqual(err.details, { field: "radius_km" });
      return true;
    }
  );
});

test("a non-2xx response with a non-JSON body still produces a generic ApiError", async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 502,
    json: async () => { throw new SyntaxError("Unexpected token <"); },
  });
  await assert.rejects(
    () => api.checkHealth(),
    (err) => {
      assert.strictEqual(err.name, "ApiError");
      assert.strictEqual(err.status, 502);
      assert.strictEqual(err.code, "HTTP_ERROR");
      assert.strictEqual(err.message, "Request failed (502).");
      return true;
    }
  );
});

test("a network failure (fetch rejects) becomes a NETWORK_ERROR ApiError, not an uncaught rejection", async () => {
  globalThis.fetch = async () => { throw new TypeError("Failed to fetch"); };
  await assert.rejects(
    () => api.checkHealth(),
    (err) => {
      assert.strictEqual(err.name, "ApiError");
      assert.strictEqual(err.code, "NETWORK_ERROR");
      return true;
    }
  );
});

test("a successful response returns the parsed JSON body", async () => {
  stubFetch(jsonResponse(200, { status: "ok", service: "wayfinder-api" }));
  const result = await api.checkHealth();
  assert.deepStrictEqual(result, { status: "ok", service: "wayfinder-api" });
});

// ---- Misc exports -------------------------------------------

test("FACILITY_CATEGORIES is a non-empty array of strings", () => {
  assert.ok(Array.isArray(api.FACILITY_CATEGORIES));
  assert.ok(api.FACILITY_CATEGORIES.length > 0);
  for (const c of api.FACILITY_CATEGORIES) assert.strictEqual(typeof c, "string");
});
