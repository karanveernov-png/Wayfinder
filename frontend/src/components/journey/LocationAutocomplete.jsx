import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { useAbortableRequest } from "../../hooks/useAbortableRequest.js";
import { suggestLocations } from "../../lib/api.js";
import {
  formatSuggestionLabel,
  formatSuggestionDetail,
  isValidCoordinates,
  nextActiveIndex,
  MIN_QUERY_LENGTH,
  SUGGESTION_DEBOUNCE_MS,
} from "../../lib/locationSuggestions.js";

/**
 * Reusable origin/destination text input backed by location suggestions
 * (autocomplete, misspelling fallback, and same-name disambiguation - see
 * docs/LOCATION_AUTOCOMPLETE_GUIDE.md and GET /locations/suggest).
 *
 * A drop-in replacement for the plain `<input>` fields this project used
 * before: same controlled `value`/`onChange(text)` contract, same wrapper
 * markup/classes, so it preserves existing styling and layout.
 *
 * Selecting a suggestion (mouse or keyboard) calls `onSelect(suggestion)`
 * with the backend's LocationSuggestion shape (place_id, display_name,
 * name, region, country, place_type, coordinates, match_confidence,
 * is_fallback_match - see backend/app/schemas/location.py). The caller
 * owns updating its own text value AND coordinates state together from
 * that one callback (see TripPlannerPage.jsx's handleOriginSelect) -
 * this component never decides on the caller's behalf what the
 * "selected" state means, it only ever reports a real, user-chosen
 * suggestion.
 *
 * Does NOT auto-select anything and does NOT replace the user's typed
 * text on their behalf - every suggestion shown here came back from a
 * real geocoding-provider response (see RoutingService.suggest_locations
 * on the backend); the user always makes the final choice.
 */
const DEFAULT_WRAPPER_CLASS = "flex items-center gap-3 rounded-xl border border-slate-200 px-4";
const DEFAULT_INPUT_CLASS = "w-full py-3 outline-none disabled:text-slate-400";
const DEFAULT_ICON_CLASS = "shrink-0 text-slate-400";

export default function LocationAutocomplete({
  id,
  value,
  onChange,
  onSelect,
  placeholder,
  disabled = false,
  required = false,
  icon: Icon,
  // Each page that used a plain <input> before had its own wrapper/input
  // styling (TripPlannerPage vs OverviewPage) - these let this component
  // be a drop-in replacement for either rather than forcing one look.
  wrapperClassName = DEFAULT_WRAPPER_CLASS,
  inputClassName = DEFAULT_INPUT_CLASS,
  iconClassName = DEFAULT_ICON_CLASS,
}) {
  const run = useAbortableRequest();
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(null);
  const [usedFallback, setUsedFallback] = useState(false);
  const [providerDegraded, setProviderDegraded] = useState(false);
  const justSelectedRef = useRef(false);
  const containerRef = useRef(null);
  const listboxId = `${id}-suggestions`;

  useEffect(() => {
    if (justSelectedRef.current) {
      // This value change is the component's own post-selection update,
      // not new user input - searching for it again would just show the
      // place the user already picked as a "suggestion" of itself.
      justSelectedRef.current = false;
      return;
    }

    // Everything below runs inside a callback - this queued microtask, or
    // the fetch's own .then()/.catch() - rather than synchronously in the
    // effect body (react-hooks/set-state-in-effect). Timing is unaffected
    // (microtasks flush before the next paint), and it's run()'s own
    // request-id/AbortController bookkeeping (useAbortableRequest.js),
    // not when within this tick run() is called, that guarantees only the
    // latest request's result ever lands.
    queueMicrotask(() => {
      const query = (value || "").trim();
      if (query.length < MIN_QUERY_LENGTH) {
        setSuggestions([]);
        setOpen(false);
        setLoading(false);
        setUsedFallback(false);
        setProviderDegraded(false);
        return;
      }

      setLoading(true);
      run((signal) => suggestLocations({ query, signal }), {
        debounceMs: SUGGESTION_DEBOUNCE_MS,
      })
        .then((result) => {
          if (result.aborted) return; // superseded by a newer keystroke, or unmounted
          const body = result.value;
          setSuggestions(Array.isArray(body?.suggestions) ? body.suggestions : []);
          setUsedFallback(Boolean(body?.used_fallback));
          setProviderDegraded(body?.data_status?.mode === "degraded");
          setActiveIndex(null);
          setOpen(true);
          setLoading(false);
        })
        .catch(() => {
          setSuggestions([]);
          setUsedFallback(false);
          setProviderDegraded(true);
          setOpen(true);
          setLoading(false);
        });
    });
  }, [value, run]);

  // Close on a click outside the field + dropdown (the dropdown itself is
  // inside containerRef, so selecting a suggestion never counts as
  // "outside").
  useEffect(() => {
    function handlePointerDown(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  function selectSuggestion(suggestion) {
    if (!suggestion || !isValidCoordinates(suggestion.coordinates)) return;
    justSelectedRef.current = true;
    setOpen(false);
    setActiveIndex(null);
    setSuggestions([]);
    onSelect(suggestion);
  }

  function handleKeyDown(event) {
    if (!open) {
      if ((event.key === "ArrowDown" || event.key === "ArrowUp") && suggestions.length > 0) {
        setOpen(true);
      }
      return;
    }

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => nextActiveIndex(current, suggestions.length, event.key));
    } else if (event.key === "Enter") {
      if (activeIndex !== null && suggestions[activeIndex]) {
        event.preventDefault();
        selectSuggestion(suggestions[activeIndex]);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
      setActiveIndex(null);
    }
  }

  const query = (value || "").trim();
  const showNoResults =
    open && !loading && !providerDegraded && query.length >= MIN_QUERY_LENGTH && suggestions.length === 0;
  const showDropdown = open && !disabled && (suggestions.length > 0 || showNoResults || providerDegraded);

  return (
    <div ref={containerRef} className="relative">
      <div className={wrapperClassName}>
        {Icon && <Icon size={18} className={iconClassName} />}
        <input
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={
            activeIndex !== null && suggestions[activeIndex] ? `${listboxId}-${activeIndex}` : undefined
          }
          autoComplete="off"
          required={required}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (suggestions.length > 0) setOpen(true);
          }}
          placeholder={placeholder}
          disabled={disabled}
          className={inputClassName}
        />
        {loading && <Loader2 size={16} className="shrink-0 animate-spin text-slate-400" aria-hidden="true" />}
      </div>

      {showDropdown && (
        <ul
          id={listboxId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white py-1 shadow-lg"
        >
          {suggestions.map((suggestion, index) => (
            <li
              key={suggestion.place_id}
              id={`${listboxId}-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              onMouseDown={(event) => {
                // mousedown (not click) so this commits before the
                // document-level outside-pointer handler above could run.
                event.preventDefault();
                selectSuggestion(suggestion);
              }}
              onMouseEnter={() => setActiveIndex(index)}
              className={`cursor-pointer px-4 py-2.5 text-sm ${
                index === activeIndex ? "bg-[#203C5A]/8" : "hover:bg-slate-50"
              }`}
            >
              <p className="font-medium text-slate-800">{formatSuggestionLabel(suggestion)}</p>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                {suggestion.is_fallback_match && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-700">
                    Did you mean?
                  </span>
                )}
                {formatSuggestionDetail(suggestion) && <span>{formatSuggestionDetail(suggestion)}</span>}
              </div>
            </li>
          ))}

          {showNoResults && (
            <li className="px-4 py-3 text-sm text-slate-500">
              No matches for “{query}”. Check the spelling, or try a nearby larger town.
            </li>
          )}

          {providerDegraded && (
            <li className="px-4 py-3 text-sm text-amber-700">
              Couldn't reach the location search service. You can still type the full place name
              and continue.
            </li>
          )}
        </ul>
      )}

      {usedFallback && suggestions.length > 0 && (
        <p className="mt-1 text-xs text-amber-700">
          No exact match for “{query}” — showing the closest matches.
        </p>
      )}
    </div>
  );
}
