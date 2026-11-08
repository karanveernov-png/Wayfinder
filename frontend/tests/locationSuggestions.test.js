/**
 * Lightweight, dependency-free tests for the location-autocomplete
 * helpers (no React, no DOM, no network - see src/lib/locationSuggestions.js).
 *
 * Run with:  node --test tests/locationSuggestions.test.js
 */
import assert from "node:assert";
import { test } from "node:test";
import {
  formatSuggestionLabel,
  formatSuggestionDetail,
  isValidCoordinates,
  nextActiveIndex,
  MIN_QUERY_LENGTH,
} from "../src/lib/locationSuggestions.js";

// ---- formatSuggestionLabel ------------------------------------------
test("formatSuggestionLabel joins name, region, country", () => {
  const label = formatSuggestionLabel({
    name: "Chandigarh",
    region: "Chandigarh",
    country: "India",
    display_name: "Chandigarh, India",
  });
  assert.strictEqual(label, "Chandigarh, Chandigarh, India");
});

test("formatSuggestionLabel skips missing parts", () => {
  const label = formatSuggestionLabel({
    name: "Chandigarh",
    region: null,
    country: "India",
    display_name: "Chandigarh, India",
  });
  assert.strictEqual(label, "Chandigarh, India");
});

test("formatSuggestionLabel falls back to display_name when all parts missing", () => {
  const label = formatSuggestionLabel({
    name: "",
    region: null,
    country: null,
    display_name: "Somewhere, Nowhere",
  });
  assert.strictEqual(label, "Somewhere, Nowhere");
});

test("formatSuggestionLabel handles null/undefined input", () => {
  assert.strictEqual(formatSuggestionLabel(null), "");
  assert.strictEqual(formatSuggestionLabel(undefined), "");
});

// ---- formatSuggestionDetail ------------------------------------------
test("formatSuggestionDetail title-cases place_type and appends country", () => {
  const detail = formatSuggestionDetail({
    place_type: "administrative",
    country: "India",
  });
  assert.strictEqual(detail, "Administrative · India");
});

test("formatSuggestionDetail handles underscores in place_type", () => {
  const detail = formatSuggestionDetail({
    place_type: "rest_stop",
    country: null,
  });
  assert.strictEqual(detail, "Rest Stop");
});

test("formatSuggestionDetail returns empty string with nothing to show", () => {
  assert.strictEqual(formatSuggestionDetail({}), "");
  assert.strictEqual(formatSuggestionDetail(null), "");
});

// ---- isValidCoordinates ------------------------------------------------
test("isValidCoordinates accepts a plausible lat/lon pair", () => {
  assert.strictEqual(isValidCoordinates({ lat: 30.7333, lon: 76.7794 }), true);
});

test("isValidCoordinates rejects out-of-range values", () => {
  assert.strictEqual(isValidCoordinates({ lat: 999, lon: 76.7794 }), false);
  assert.strictEqual(isValidCoordinates({ lat: 30.7333, lon: -200 }), false);
});

test("isValidCoordinates rejects non-numeric, missing, or malformed values", () => {
  assert.strictEqual(isValidCoordinates(null), false);
  assert.strictEqual(isValidCoordinates(undefined), false);
  assert.strictEqual(isValidCoordinates({}), false);
  assert.strictEqual(isValidCoordinates({ lat: "30.7", lon: 76.7 }), false);
  assert.strictEqual(isValidCoordinates({ lat: NaN, lon: 76.7 }), false);
});

// ---- nextActiveIndex (keyboard navigation) -----------------------------
test("nextActiveIndex moves down from nothing selected", () => {
  assert.strictEqual(nextActiveIndex(null, 3, "ArrowDown"), 0);
});

test("nextActiveIndex moves down and wraps at the end", () => {
  assert.strictEqual(nextActiveIndex(0, 3, "ArrowDown"), 1);
  assert.strictEqual(nextActiveIndex(2, 3, "ArrowDown"), 0);
});

test("nextActiveIndex moves up and wraps at the start", () => {
  assert.strictEqual(nextActiveIndex(1, 3, "ArrowUp"), 0);
  assert.strictEqual(nextActiveIndex(0, 3, "ArrowUp"), 2);
  assert.strictEqual(nextActiveIndex(null, 3, "ArrowUp"), 2);
});

test("nextActiveIndex returns null when there are no suggestions", () => {
  assert.strictEqual(nextActiveIndex(0, 0, "ArrowDown"), null);
  assert.strictEqual(nextActiveIndex(null, 0, "ArrowUp"), null);
});

test("nextActiveIndex leaves the index unchanged for an unrelated key", () => {
  assert.strictEqual(nextActiveIndex(1, 3, "Enter"), 1);
});

// ---- MIN_QUERY_LENGTH ---------------------------------------------------
test("MIN_QUERY_LENGTH matches the backend's short-query short-circuit", () => {
  assert.strictEqual(MIN_QUERY_LENGTH, 2);
});
