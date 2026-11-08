import { useState } from "react";
import { Sparkles, Send, Loader2, MapPin, Flag, ArrowRight } from "lucide-react";
import { planTripFromText, ApiError } from "../../lib/api.js";
import { useJourney } from "../../context/JourneyContext.jsx";
import LocationAutocomplete from "./LocationAutocomplete.jsx";
import { formatSuggestionLabel } from "../../lib/locationSuggestions.js";

const EXAMPLE_PROMPT =
  "Plan a trip from Delhi to Shimla. Prefer a reasonably short and easy route. Show hospitals and pharmacies along the way.";

/**
 * Minimal natural-language front door to the Trip Planner: one textarea,
 * one button. Submits to POST /trip-intent/plan (Groq interprets the
 * sentence into the same fields the form below sends), then hands the
 * result's `journey` straight to JourneyContext so every existing display
 * below (map, risk panel, facilities, alerts, weather, elevation) renders
 * it exactly as it would a journey planned through the regular form.
 */
export default function TripIntentForm() {
  const { applyJourneyResult, runAnalysis } = useJourney();
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState(null); // { kind: "clarification" | "error" | "info", text }

  // Populated only when POST /trip-intent/plan comes back with
  // status === "needs_clarification" - either Groq itself flagged the
  // origin/destination as uncertain, or one/both were missing entirely
  // (see ParsedTripIntent.needs_clarification,
  // backend/app/api/routes/trip_intent.py). Lets the user resolve a real
  // location through the same LocationAutocomplete the manual form uses,
  // instead of the app guessing or silently geocoding Groq's raw text
  // (Scenario E: an ambiguous Groq location is never auto-resolved).
  const [clarifyIntent, setClarifyIntent] = useState(null);
  const [clarifyOrigin, setClarifyOrigin] = useState("");
  const [clarifyDestination, setClarifyDestination] = useState("");
  const [clarifySelectedOrigin, setClarifySelectedOrigin] = useState(null);
  const [clarifySelectedDestination, setClarifySelectedDestination] = useState(null);
  const [clarifyLoading, setClarifyLoading] = useState(false);
  const [clarifyError, setClarifyError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed) {
      setNotice({ kind: "error", text: "Describe your trip first - for example, the placeholder text above." });
      return;
    }

    setLoading(true);
    setNotice(null);
    setClarifyIntent(null); // a fresh request supersedes any earlier unresolved clarification
    try {
      const result = await planTripFromText({ message: trimmed });
      if (result.status === "ok") {
        applyJourneyResult(result.journey, {
          origin: result.intent.origin,
          destination: result.intent.destination,
          travelMode: result.intent.travel_mode,
          demo: false,
        });
        setNotice(result.message ? { kind: "info", text: result.message } : null);
      } else if (result.status === "needs_clarification") {
        setNotice({ kind: "clarification", text: result.message || "Please confirm the locations below." });
        setClarifyIntent(result.intent || {});
        setClarifyOrigin(result.intent?.origin || "");
        setClarifyDestination(result.intent?.destination || "");
        setClarifySelectedOrigin(null);
        setClarifySelectedDestination(null);
        setClarifyError("");
      } else {
        setNotice({ kind: "error", text: result.message || "Please try rephrasing your request." });
      }
    } catch (err) {
      setNotice({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Something went wrong while planning that trip.",
      });
    } finally {
      setLoading(false);
    }
  }

  function handleClarifyOriginChange(value) {
    setClarifyOrigin(value);
    setClarifySelectedOrigin(null);
  }

  function handleClarifyDestinationChange(value) {
    setClarifyDestination(value);
    setClarifySelectedDestination(null);
  }

  function handleClarifyOriginSelect(suggestion) {
    setClarifyOrigin(formatSuggestionLabel(suggestion));
    setClarifySelectedOrigin(suggestion.coordinates);
  }

  function handleClarifyDestinationSelect(suggestion) {
    setClarifyDestination(formatSuggestionLabel(suggestion));
    setClarifySelectedDestination(suggestion.coordinates);
  }

  async function handleClarifySubmit(event) {
    event.preventDefault();
    const origin = clarifyOrigin.trim();
    const destination = clarifyDestination.trim();
    if (!origin || !destination) {
      setClarifyError("Please provide both a starting point and a destination.");
      return;
    }
    if (origin.toLowerCase() === destination.toLowerCase()) {
      setClarifyError("Your starting point and destination must be different.");
      return;
    }

    setClarifyError("");
    setClarifyLoading(true);
    try {
      // Bypasses Groq entirely for this resolved request - same pipeline
      // (and same trusted-coordinate contract) the manual form below
      // uses, see TripPlannerPage.jsx handleSubmit.
      await runAnalysis({
        origin,
        destination,
        originCoordinates: clarifySelectedOrigin,
        destinationCoordinates: clarifySelectedDestination,
        travelMode: clarifyIntent?.travel_mode || "driving",
        facilityCategories: clarifyIntent?.facilities?.length ? clarifyIntent.facilities : undefined,
      });
      setClarifyIntent(null);
      setNotice(null);
    } catch {
      // error is already surfaced via context.error (rendered further
      // down this same page - see TripPlannerPage.jsx)
    } finally {
      setClarifyLoading(false);
    }
  }

  const noticeClassName =
    notice?.kind === "error"
      ? "text-red-600"
      : notice?.kind === "clarification"
        ? "text-amber-700"
        : "text-slate-500";

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
      <div className="flex items-center gap-2">
        <Sparkles size={18} className="text-[#203C5A]" />
        <h2 className="text-lg font-semibold">Plan with a sentence</h2>
      </div>
      <p className="mt-2 text-sm text-slate-500">
        Describe your trip in plain English and an AI assistant (Groq) will fill in the details below
        using the same live routing and facility search as the form - it never invents routes, places,
        or distances itself.
      </p>

      <form onSubmit={handleSubmit} className="mt-4 space-y-3">
        <label htmlFor="trip-intent-message" className="sr-only">
          Describe your trip
        </label>
        <textarea
          id="trip-intent-message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={EXAMPLE_PROMPT}
          rows={3}
          maxLength={500}
          disabled={loading}
          className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-[#203C5A] disabled:bg-slate-50 disabled:text-slate-400"
        />
        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#203C5A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#172E46] disabled:opacity-60"
        >
          {loading ? (
            <>
              <Loader2 size={16} className="animate-spin" /> Thinking…
            </>
          ) : (
            <>
              <Send size={16} /> Plan with AI
            </>
          )}
        </button>
      </form>

      {notice && (
        <p role={notice.kind === "error" ? "alert" : "status"} className={`mt-3 text-sm ${noticeClassName}`}>
          {notice.text}
        </p>
      )}

      {clarifyIntent && (
        <form
          onSubmit={handleClarifySubmit}
          className="mt-4 space-y-4 rounded-xl border border-amber-200 bg-amber-50/40 p-4"
        >
          <p className="text-sm font-medium text-slate-700">
            Pick the exact starting point and destination to continue.
          </p>

          <div>
            <label
              htmlFor="trip-intent-clarify-origin"
              className="mb-1.5 block text-xs font-medium text-slate-600"
            >
              Starting point
            </label>
            <LocationAutocomplete
              id="trip-intent-clarify-origin"
              icon={MapPin}
              value={clarifyOrigin}
              onChange={handleClarifyOriginChange}
              onSelect={handleClarifyOriginSelect}
              placeholder="e.g. Delhi, India"
            />
          </div>

          <div>
            <label
              htmlFor="trip-intent-clarify-destination"
              className="mb-1.5 block text-xs font-medium text-slate-600"
            >
              Destination
            </label>
            <LocationAutocomplete
              id="trip-intent-clarify-destination"
              icon={Flag}
              value={clarifyDestination}
              onChange={handleClarifyDestinationChange}
              onSelect={handleClarifyDestinationSelect}
              placeholder="e.g. Shimla, Himachal Pradesh"
            />
          </div>

          {clarifyError && (
            <p role="alert" className="text-sm text-red-600">
              {clarifyError}
            </p>
          )}

          <button
            type="submit"
            disabled={clarifyLoading}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#203C5A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#172E46] disabled:opacity-60"
          >
            {clarifyLoading ? (
              <>
                <Loader2 size={16} className="animate-spin" /> Analysing…
              </>
            ) : (
              <>
                Continue <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>
      )}
    </section>
  );
}
