// frontend/src/hooks/useElevationProfile.js
//
// State management for the Elevation Profile feature: samples the
// drawn route at a fixed number of evenly-spaced points (independent of
// however many raw vertices Bhuvan/OSRM returned, so a dense GeoJSON
// LineString doesn't translate into a dense, jittery chart), hands those
// points to elevationWorker.js, and exposes a plain { data, loading,
// error, totalAscentM, totalDescentM } shape to the chart component.
//
// Reuses the same two staleness guards as useAbortableRequest.js
// (request-id check + worker lifecycle tied to this hook's own effect
// cleanup) applied to a worker round-trip instead of a fetch — if the
// route changes again while a profile is mid-calculation, the stale
// response is discarded instead of flashing an outdated chart.

import { useEffect, useMemo, useRef, useState } from "react";

const SAMPLE_COUNT = 150;
const EARTH_RADIUS_M = 6371008.8; // matches geo.js's constant

function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return (2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a))) / 1000;
}

/** Evenly re-samples a GeoJSON LineString (lon/lat pairs) by cumulative distance. */
function sampleRouteEvenly(coordinates, count) {
  if (!Array.isArray(coordinates) || coordinates.length < 2) return [];

  const cumulative = [0];
  for (let i = 1; i < coordinates.length; i++) {
    const [lon1, lat1] = coordinates[i - 1];
    const [lon2, lat2] = coordinates[i];
    cumulative.push(cumulative[i - 1] + haversineKm(lat1, lon1, lat2, lon2));
  }
  const totalKm = cumulative[cumulative.length - 1];
  if (totalKm === 0) return [];

  const samples = [];
  let segment = 0;
  for (let s = 0; s < count; s++) {
    const targetKm = (totalKm * s) / (count - 1);
    while (segment < cumulative.length - 2 && cumulative[segment + 1] < targetKm) segment++;
    const segStart = cumulative[segment];
    const segEnd = cumulative[segment + 1];
    const t = segEnd > segStart ? (targetKm - segStart) / (segEnd - segStart) : 0;
    const [lon1, lat1] = coordinates[segment];
    const [lon2, lat2] = coordinates[segment + 1];
    samples.push({
      lat: lat1 + (lat2 - lat1) * t,
      lon: lon1 + (lon2 - lon1) * t,
      distanceKm: targetKm,
    });
  }
  return samples;
}

export function useElevationProfile(routeGeometry) {
  const workerRef = useRef(null);
  const requestIdRef = useRef(0);
  const [state, setState] = useState({ data: [], loading: false, error: "" });

  const sampledPoints = useMemo(() => {
    if (!routeGeometry || routeGeometry.type !== "LineString") return [];
    return sampleRouteEvenly(routeGeometry.coordinates, SAMPLE_COUNT);
  }, [routeGeometry]);

  // One worker for the component's lifetime; terminated on unmount.
  useEffect(() => {
    const worker = new Worker(new URL("../workers/elevationWorker.js", import.meta.url), {
      type: "module",
    });
    workerRef.current = worker;
    return () => {
      worker.terminate();
      workerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const worker = workerRef.current;
    if (!worker || sampledPoints.length === 0) {
      setState({ data: [], loading: false, error: "" });
      return undefined;
    }

    const requestId = ++requestIdRef.current;
    setState((current) => ({ ...current, loading: true, error: "" }));

    const handleMessage = (event) => {
      if (event.data.requestId !== requestId) return; // stale — a newer route superseded this one
      if (event.data.type === "profile") {
        setState({ data: event.data.samples, loading: false, error: "" });
      } else if (event.data.type === "error") {
        setState((current) => ({ ...current, loading: false, error: event.data.message }));
      }
    };

    worker.addEventListener("message", handleMessage);
    worker.postMessage({ type: "profile", requestId, points: sampledPoints });

    return () => worker.removeEventListener("message", handleMessage);
  }, [sampledPoints]);

  const { totalAscentM, totalDescentM } = useMemo(() => {
    let up = 0;
    let down = 0;
    for (let i = 1; i < state.data.length; i++) {
      const delta = state.data[i].elevationM - state.data[i - 1].elevationM;
      if (delta > 0) up += delta;
      else down -= delta;
    }
    return { totalAscentM: Math.round(up), totalDescentM: Math.round(down) };
  }, [state.data]);

  return { ...state, totalAscentM, totalDescentM };
}
