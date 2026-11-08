/**
 * Pure helper functions for the location-autocomplete feature
 * (components/journey/LocationAutocomplete.jsx). Kept dependency-free and
 * side-effect-free on purpose so they're unit-testable with Node's test
 * runner (see tests/locationSuggestions.test.js) the same way format.js
 * and geo.js already are, without needing a browser/DOM or React.
 *
 * The backend (GET /locations/suggest, see
 * backend/app/schemas/location.py) already normalizes and deduplicates
 * results - these helpers are about presenting that data, and about
 * recognizing a stale/invalid value, not about re-implementing geocoding.
 */

/** A short, human-scannable label for one suggestion: "Name, Region, Country". */
export function formatSuggestionLabel(suggestion) {
  if (!suggestion) return "";
  const parts = [suggestion.name, suggestion.region, suggestion.country].filter(
    (part) => typeof part === "string" && part.trim().length > 0
  );
  return parts.length > 0 ? parts.join(", ") : suggestion.display_name || "";
}

/** A short secondary line for a suggestion row, e.g. "City · India". Omits
 * parts already implied by the primary label. */
export function formatSuggestionDetail(suggestion) {
  if (!suggestion) return "";
  const parts = [];
  if (suggestion.place_type) parts.push(toTitleCase(suggestion.place_type));
  if (suggestion.country) parts.push(suggestion.country);
  return parts.join(" · ");
}

function toTitleCase(value) {
  if (!value) return "";
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

/** True when `coords` is a plausible { lat, lon } pair the map/journey
 * pipeline can use. Mirrors the backend's Coordinates validation range so
 * the frontend never forwards an out-of-range value it received from
 * somewhere unexpected (e.g. a malformed saved journey). */
export function isValidCoordinates(coords) {
  if (!coords || typeof coords !== "object") return false;
  const { lat, lon } = coords;
  return (
    typeof lat === "number" &&
    typeof lon === "number" &&
    Number.isFinite(lat) &&
    Number.isFinite(lon) &&
    lat >= -90 &&
    lat <= 90 &&
    lon >= -180 &&
    lon <= 180
  );
}

/**
 * Keyboard navigation reducer for the suggestion list: given the current
 * active index, the number of suggestions, and a key name, returns the
 * next active index (or null). Pure so the component's keydown handler
 * stays a thin wrapper, and so the up/down/wrap-around behavior itself is
 * directly testable.
 */
export function nextActiveIndex(currentIndex, suggestionCount, key) {
  if (suggestionCount <= 0) return null;
  if (key === "ArrowDown") {
    if (currentIndex === null || currentIndex >= suggestionCount - 1) return 0;
    return currentIndex + 1;
  }
  if (key === "ArrowUp") {
    if (currentIndex === null || currentIndex <= 0) return suggestionCount - 1;
    return currentIndex - 1;
  }
  return currentIndex;
}

/** Minimum raw input length before an autocomplete request is worth
 * sending - mirrors RoutingService._MIN_QUERY_LENGTH on the backend, kept
 * here too so the frontend doesn't even start the debounce timer for a
 * query the backend would short-circuit anyway. */
export const MIN_QUERY_LENGTH = 2;

/** Debounce delay before a suggestions request fires, matching the
 * project's existing typeahead convention (see useAbortableRequest). */
export const SUGGESTION_DEBOUNCE_MS = 350;
