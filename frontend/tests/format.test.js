/**
 * Lightweight tests for the format.js helpers.
 *
 * (This file was previously named api.test.js despite only testing
 * format.js -- renamed during the audit; see the new api.test.js for
 * actual src/lib/api.js coverage, which this misnamed file had displaced.)
 * These verify the data-status and risk-level styling functions match the contract.
 *
 * Run with:  node --test tests/format.test.js
 */
import assert from "node:assert";
import { test } from "node:test";
import {
  dataStatusStyle,
  riskStyle,
  facilityVerificationLabel,
  weatherCodeLabel,
  formatDistance,
  formatDuration,
  isFacilityVerified,
  isDemoAlert,
  SEVERITY_STYLES,
  journeyShareText,
} from "../src/lib/format.js";

// ---- dataStatusStyle ------------------------------------------------
test("dataStatusStyle returns correct label and class for each mode", () => {
  const live = dataStatusStyle("live");
  assert.strictEqual(live.label, "Live data");
  assert.ok(live.className.includes("emerald-50"));
  assert.ok(live.className.includes("emerald-700"));

  const partial = dataStatusStyle("partial");
  assert.strictEqual(partial.label, "Partial data");
  assert.ok(partial.className.includes("amber-50"));
  assert.ok(partial.className.includes("amber-700"));

  const degraded = dataStatusStyle("degraded");
  assert.strictEqual(degraded.label, "Degraded");
  assert.ok(degraded.className.includes("red-50"));
  assert.ok(degraded.className.includes("red-700"));

  const demo = dataStatusStyle("demo");
  assert.strictEqual(demo.label, "Demo data");
  assert.ok(demo.className.includes("amber-50"));
  assert.ok(demo.className.includes("amber-700"));

  const unknown = dataStatusStyle("unknown-mode");
  assert.strictEqual(unknown.label, "unknown-mode");
  assert.ok(unknown.className.includes("slate-100"));
  assert.ok(unknown.className.includes("slate-600"));
});

// ---- riskStyle ------------------------------------------------------
test("riskStyle returns correct label and class for each level", () => {
  const low = riskStyle("low");
  assert.strictEqual(low.label, "Low risk");
  assert.ok(low.className.includes("emerald-50"));
  assert.ok(low.className.includes("emerald-700"));
  assert.ok(low.className.includes("emerald-200"));

  const moderate = riskStyle("moderate");
  assert.strictEqual(moderate.label, "Moderate risk");
  assert.ok(moderate.className.includes("amber-50"));
  assert.ok(moderate.className.includes("amber-700"));
  assert.ok(moderate.className.includes("amber-200"));

  const high = riskStyle("high");
  assert.strictEqual(high.label, "High risk");
  assert.ok(high.className.includes("red-50"));
  assert.ok(high.className.includes("red-700"));
  assert.ok(high.className.includes("red-200"));

  const unknown = riskStyle("unknown");
  assert.strictEqual(unknown.label, "Risk unknown");
  assert.ok(unknown.className.includes("slate-100"));
  assert.ok(unknown.className.includes("slate-600"));
  assert.ok(unknown.className.includes("slate-200"));
});

// ---- facilityVerificationLabel --------------------------------------
test("facilityVerificationLabel covers all verification statuses", () => {
  assert.strictEqual(facilityVerificationLabel("verified"), "Verified location");
  assert.strictEqual(facilityVerificationLabel("address_matched"), "Address-matched (not cross-checked)");
  assert.strictEqual(facilityVerificationLabel("unverified_coordinates"), "Approximate — unverified coordinates");
  assert.strictEqual(facilityVerificationLabel("unavailable"), "Location unavailable");
  assert.strictEqual(facilityVerificationLabel("something-else"), "Unverified");
});

// ---- weatherCodeLabel -----------------------------------------------
test("weatherCodeLabel maps known WMO codes and handles unknowns", () => {
  assert.strictEqual(weatherCodeLabel(0), "Clear sky");
  assert.strictEqual(weatherCodeLabel(95), "Thunderstorm");
  assert.strictEqual(weatherCodeLabel(999), "Weather code 999");
  assert.strictEqual(weatherCodeLabel(null), "Unknown conditions");
  assert.strictEqual(weatherCodeLabel(undefined), "Unknown conditions");
});

// ---- formatDistance / formatDuration --------------------------------
test("formatDistance renders metres and kilometres with correct precision", () => {
  assert.strictEqual(formatDistance(0.15), "150 m");
  assert.strictEqual(formatDistance(1), "1.0 km");
  assert.strictEqual(formatDistance(35.6), "35.6 km");
  assert.strictEqual(formatDistance(null), "—");
  assert.strictEqual(formatDistance(undefined), "—");
});

test("formatDuration renders minutes and hours correctly", () => {
  assert.strictEqual(formatDuration(5), "5 min");
  assert.strictEqual(formatDuration(45), "45 min");
  assert.strictEqual(formatDuration(60), "1 h 0 min");
  assert.strictEqual(formatDuration(125), "2 h 5 min");
  assert.strictEqual(formatDuration(null), "—");
  assert.strictEqual(formatDuration(undefined), "—");
});

// ---- isFacilityVerified ---------------------------------------------
test("isFacilityVerified only returns true for 'verified' status", () => {
  assert.strictEqual(isFacilityVerified({ verification_status: "verified" }), true);
  assert.strictEqual(isFacilityVerified({ verification_status: "address_matched" }), false);
  assert.strictEqual(isFacilityVerified({ verification_status: "unverified_coordinates" }), false);
  assert.strictEqual(isFacilityVerified({ verification_status: "unavailable" }), false);
  assert.strictEqual(isFacilityVerified(null), false);
  assert.strictEqual(isFacilityVerified(undefined), false);
});

// ---- isDemoAlert ----------------------------------------------------
test("isDemoAlert detects demo alerts by source and description prefix", () => {
  assert.strictEqual(isDemoAlert({ source: "demo-data" }), true);
  assert.strictEqual(isDemoAlert({ description: "[SIMULATED DEMO DATA — NOT a real incident report]" }), true);
  assert.strictEqual(isDemoAlert({ source: "real", description: "Real alert" }), false);
  assert.strictEqual(isDemoAlert(null), false);
  assert.strictEqual(isDemoAlert(undefined), false);
});

// ---- SEVERITY_STYLES ------------------------------------------------
test("SEVERITY_STYLES has expected keys and shape", () => {
  assert.ok("low" in SEVERITY_STYLES);
  assert.ok("moderate" in SEVERITY_STYLES);
  assert.ok("high" in SEVERITY_STYLES);
  assert.ok("unknown" in SEVERITY_STYLES);
  assert.ok(SEVERITY_STYLES.low.includes("slate"));
  assert.ok(SEVERITY_STYLES.moderate.includes("amber"));
  assert.ok(SEVERITY_STYLES.high.includes("red"));
});
// ---- journeyShareText -------------------------------------------------
// journeyShareText() is used by ShareJourneyButton from two different call
// sites with two different journey shapes. These tests also double as the
// regression test for a real bug found during this audit: SavedJourneysPage
// was reading entry.distanceKm/durationMinutes/riskLevel/savedAt (camelCase)
// from a backend response that actually uses distance_km/duration_minutes/
// risk_level/created_at (snake_case, confirmed against
// backend/app/api/routes/saved_journeys.py's SavedJourneyResponse) - so
// every saved journey silently showed "—" for distance/duration, "Risk
// unknown", and the literal string "Invalid Date". Fixed in
// SavedJourneysPage.jsx; journeyShareText is exercised here with that same
// real response shape to lock in the correct field names going forward.

test("journeyShareText: live JourneyAnalyseResponse shape (nested origin/destination objects)", () => {
  const journey = {
    origin: { display_name: "Chandigarh, India", query: "Chandigarh" },
    destination: { display_name: "Ludhiana, Punjab, India", query: "Ludhiana" },
    distance_km: 98.4,
    duration_minutes: 125,
    risk_assessment: { level: "moderate" },
  };
  const text = journeyShareText(journey);
  assert.ok(text.includes("Chandigarh, India → Ludhiana, Punjab, India"));
  assert.ok(text.includes("98.4 km"));
  assert.ok(text.includes("Moderate risk"));
});

test("journeyShareText: saved-journey row shape (flat string origin/destination, flat risk_level)", () => {
  // Exactly the shape GET /saved-journeys returns (see
  // SavedJourneyResponse) and what SavedJourneysPage passes to
  // ShareJourneyButton for each entry.
  const entry = {
    id: "abc-123",
    origin: "Chandigarh, India",
    destination: "Ludhiana, Punjab, India",
    distance_km: 98.4,
    duration_minutes: 125,
    risk_level: "moderate",
    data_status_mode: "live",
    created_at: "2026-01-01T00:00:00Z",
  };
  const text = journeyShareText(entry);
  assert.ok(text.includes("Chandigarh, India → Ludhiana, Punjab, India"));
  assert.ok(text.includes("98.4 km"));
  assert.ok(text.includes("Moderate risk"));
});

test("journeyShareText: missing optional fields produce no literal 'undefined'", () => {
  const text = journeyShareText({ origin: "A", destination: "B" });
  assert.ok(!text.includes("undefined"));
  assert.strictEqual(text, "Waymark journey: A → B");
});

test("journeyShareText: null/undefined journey returns an empty string", () => {
  assert.strictEqual(journeyShareText(null), "");
  assert.strictEqual(journeyShareText(undefined), "");
});
