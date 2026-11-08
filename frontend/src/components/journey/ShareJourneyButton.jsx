import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Share2, Check, Link as LinkIcon, ExternalLink } from "lucide-react";
import { journeyShareText, journeyShareUrl, extractJourneyEndpoints } from "../../lib/format.js";

function copyToClipboard(text) {
  return navigator.clipboard.writeText(text);
}

/**
 * Copy a URL to the clipboard. If the platform's native Web Share API is
 * available and the browser supports opening URLs (most mobile browsers
 * will fire a "share via map app" intent for maps.google.com links),
 * fall back to that instead.
 */
async function shareViaWebShare(url) {
  if (navigator.share) {
    await navigator.share({ title: "Waymark journey directions", url });
    return "shared";
  }
  await copyToClipboard(url);
  return "copied";
}

export default function ShareJourneyButton({
  journey,
  travelMode,
  /** When true, always show the card layout regardless of whether coords exist. */
  className = "",
}) {
  const [status, setStatus] = useState("idle"); // idle | copied | shared | error
  const resetTimeoutRef = useRef(null);

  useEffect(() => () => clearTimeout(resetTimeoutRef.current), []);

  function flashStatus(next) {
    setStatus(next);
    clearTimeout(resetTimeoutRef.current);
    resetTimeoutRef.current = setTimeout(() => setStatus("idle"), 2200);
  }

  const url = useMemo(
    () => journeyShareUrl(journey, travelMode),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [journey, travelMode]
  );

  const { originCoord, destCoord } = extractJourneyEndpoints(journey);

  const canUseGoogleMaps = useMemo(
    () => !!(url && originCoord?.lat && originCoord?.lon && destCoord?.lat && destCoord?.lon),
    [url, originCoord, destCoord]
  );

  const hasAnyJourneyData = Boolean(journey?.distance_km || journey?.origin || journey?.destination);

  // Text-only share is always available (no coords needed).
  const handlePlainTextShare = useCallback(async () => {
    const text = journeyShareText(journey);
    if (!text) return;
    try {
      if (navigator.share) {
        await navigator.share({ title: "Waymark journey", text });
        flashStatus("shared");
      } else {
        await copyToClipboard(text);
        flashStatus("copied");
      }
    } catch (err) {
      if (err?.name !== "AbortError") flashStatus("error");
    }
  }, [journey, flashStatus]);

  // Link-style share: try Google Maps URL first, degrade gracefully.
  const handleUrlShare = useCallback(async () => {
    if (!url) return;
    try {
      const result = await shareViaWebShare(url);
      flashStatus(result);
    } catch {
      flashStatus("error");
    }
  }, [url, flashStatus]);

  if (!hasAnyJourneyData) return null;

  return (
    <div className={`inline-flex flex-col sm:flex-row gap-2 ${className}`}>
      {/* Primary action: open or copy the Google Maps link when coords exist */}
      {canUseGoogleMaps ? (
        <>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-xl border border-[#EAF0F6] bg-gradient-to-r from-[#EAF0F6] to-[#F4F6F9] px-4 py-2 text-sm font-medium text-[#203C5A] shadow-sm transition hover:from-[#203C5A]/10 hover:to-[#203C5A]/5"
            aria-label="Open route in Google Maps (opens in a new tab)"
          >
            <ExternalLink size={15} />
            Open in Google Maps
          </a>
          <button
            type="button"
            onClick={handleUrlShare}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
            aria-label="Copy Google Maps link to clipboard"
          >
            {status === "copied" ? <Check size={16} className="text-emerald-600" /> : <LinkIcon size={16} />}
            {status === "copied" ? "Copied link" : "Copy link"}
          </button>
        </>
      ) : (
        /* No coords fallback: plain-text share only */
        <button
          type="button"
          onClick={handlePlainTextShare}
          className={`inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50`}
        >
          {status === "copied" || status === "shared" ? (
            <Check size={16} className="text-emerald-600" />
          ) : (
            <Share2 size={16} />
          )}
          {status === "copied"
            ? "Copied summary"
            : status === "shared"
            ? "Shared"
            : status === "error"
            ? "Couldn't share"
            : "Share"}
        </button>
      )}

      {/* Optional trailing hint when Google Maps link is shown */}
      {canUseGoogleMaps && (
        <span className="self-center text-xs text-slate-400">
          Tap · or copy to send to someone
        </span>
      )}
    </div>
  );
}
