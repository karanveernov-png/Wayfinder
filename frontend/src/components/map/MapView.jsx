import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  Circle,
  ScaleControl,
  useMap,
  useMapEvents,
} from "react-leaflet";
import { useCallback, useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import { LocateFixed, Target } from "lucide-react";
import {
  geometryToLatLngs,
  coordToLatLng,
  formatDistance,
  facilityVerificationLabel,
  isFacilityVerified,
  FACILITY_CATEGORY_LABELS,
  isDemoAlert,
} from "../../lib/format.js";
import { facilityIcon, alertIcon, endpointIcon } from "../../lib/mapIcons.js";
import { isValidLatLng, isValidPoint } from "../../lib/geo.js";

const DEFAULT_CENTER = [31.1471, 75.3412]; // Punjab, India — matches the backend's demo corridor region
const DEFAULT_ZOOM = 8;

// Per https://operations.osmfoundation.org/policies/tiles/ — use exactly this
// host. The legacy {s}.tile.openstreetmap.org subdomain form is not part of
// the published policy and "may be slower or withdrawn without notice".
const OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

/**
 * Fits the map to the route + markers. Only re-fits when the *content*
 * actually changes — a deep signature comparison avoids re-fitting on
 * every unrelated render (state updates elsewhere in the app, parent
 * re-renders, etc.), which would yank the user's viewport away from where
 * they just panned/zoomed.
 */
function FitToContent({ bounds }) {
  const map = useMap();
  const lastSignatureRef = useRef(null);

  const signature = useMemo(
    () => bounds.map((p) => `${p[0].toFixed(5)},${p[1].toFixed(5)}`).join("|"),
    [bounds]
  );
  const count = bounds.length;

  useEffect(() => {
    if (count === 0) return;
    if (lastSignatureRef.current === signature) return;
    lastSignatureRef.current = signature;
    if (count === 1) {
      map.setView(bounds[0], 12, { animate: true });
      return;
    }
    map.fitBounds(L.latLngBounds(bounds), { padding: [40, 40] });
  }, [map, signature, count, bounds]);

  return null;
}

/** Applies an explicit center/zoom whenever either changes, without fitting to markers. */
function SetViewTo({ center, zoom }) {
  const map = useMap();
  const lastSignatureRef = useRef(null);
  const signature = center
    ? `${center[0].toFixed(5)},${center[1].toFixed(5)},${zoom}`
    : null;

  useEffect(() => {
    if (!center) return;
    if (lastSignatureRef.current === signature) return;
    lastSignatureRef.current = signature;
    map.setView(center, zoom, { animate: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, signature]);
  return null;
}

/** Pans/zooms to a one-off target (e.g. a facility picked from the list) without changing the base view. */
function FocusHandler({ target }) {
  const map = useMap();
  useEffect(() => {
    if (!target || !isValidLatLng(target.lat, target.lon)) return;
    map.setView([target.lat, target.lon], target.zoom ?? Math.max(map.getZoom(), 16), { animate: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, target?.lat, target?.lon, target?.zoom, target?.token]);
  return null;
}

/** Keeps the map correctly sized when its container is resized by a layout change (not just the window). */
function ResizeHandler() {
  const map = useMap();
  useEffect(() => {
    const container = map.getContainer();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(container);
    return () => observer.disconnect();
  }, [map]);
  return null;
}

/**
 * Small overlay button that restores the map's intended view. In "route" mode
 * that means re-fitting to the route/marker bounds (matching FitToContent) —
 * not a fixed center/zoom, which would undo the whole-route fit and strand
 * the view at an arbitrary fallback zoom. In "point" mode it means returning
 * to the resolved search center/zoom (matching SetViewTo).
 */
function RecenterControl({ fitMode, bounds, center, zoom }) {
  const map = useMap();
  const hasTarget = fitMode === "route" ? bounds.length > 0 : !!center;
  if (!hasTarget) return null;

  function handleClick() {
    if (fitMode === "route") {
      if (bounds.length === 1) {
        map.setView(bounds[0], 12, { animate: true });
      } else {
        map.fitBounds(L.latLngBounds(bounds), { padding: [36, 36] });
      }
    } else {
      map.setView(center, zoom, { animate: true });
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      title="Recenter map"
      aria-label="Recenter map"
      className="absolute right-2.5 top-2.5 z-[1000] flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:bg-slate-50"
    >
      <LocateFixed size={17} />
    </button>
  );
}

/**
 * "Show whole search area" — fits the map to the search-radius circle so the
 * user can see everything the query covered, not just the markers that
 * happened to land inside it. Only meaningful in "point" mode.
 */
function FitRadiusControl({ searchCenter, searchRadiusMeters }) {
  const map = useMap();
  if (!searchCenter || !Number.isFinite(searchRadiusMeters) || searchRadiusMeters <= 0) {
    return null;
  }

  function handleClick() {
    const latLng = L.latLng(searchCenter.lat, searchCenter.lon);
    // Leaflet's circle bounds are the bounding box of the circle, which is
    // exactly what we want to fit to.
    const circle = L.circle(latLng, { radius: searchRadiusMeters });
    map.fitBounds(circle.getBounds(), { padding: [48, 48] });
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      title="Show whole search area"
      aria-label="Show whole search area"
      className="absolute right-2.5 bottom-4 z-[1000] flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:bg-slate-50"
    >
      <Target size={17} />
    </button>
  );
}

/** Internal component to handle map clicks for coordinate picking. */
function MapClickHandler({ enabled, onPick }) {
  useMapEvents({
    click(e) {
      if (!enabled) return;
      if (e.originalEvent?.target?.closest?.(".leaflet-marker-icon, .leaflet-interactive")) return;
      onPick(e.latlng);
    },
  });
  return null;
}

/**
 * Reports the map's center after every pan/zoom settles — opt-in (only
 * mounted when a page passes onViewportIdle) so this has zero effect on
 * Trip Planner/Overview, which don't use it. Nearby Places uses this to
 * offer a "Search this area" affordance once the map has been dragged
 * away from the active search center, the same pattern Google/Apple Maps
 * use instead of silently re-searching on every tiny nudge.
 */
function ViewportIdleReporter({ onViewportIdle }) {
  const map = useMapEvents({
    moveend() {
      if (!onViewportIdle) return;
      const center = map.getCenter();
      onViewportIdle({ lat: center.lat, lon: center.lng });
    },
  });
  return null;
}

/**
 * General-purpose map used across Trip Planner, Nearby Places and the
 * Overview preview. Everything it draws comes straight from the backend
 * response shape (Coordinates / Facility / Alert / RouteGeometry) — no
 * client-side routing or geocoding happens here.
 */
export default function MapView({
  origin = null, // { lat, lon, label }
  originTitle = "Start",
  destination = null, // { lat, lon, label }
  routeGeometry = null, // GeoJSON LineString from journey.geometry
  facilities = [],
  alerts = [],
  center,
  zoom,
  // "route" (default): fit to route/marker bounds, as Trip Planner and Overview need.
  // "point": always use the given center/zoom and ignore marker bounds, so a Nearby
  // Places search around one point isn't zoomed out by a few distant results.
  fitMode = "route",
  searchCenter = null, // { lat, lon } — center of a radius search
  searchRadiusMeters = null,
  accuracyCenter = null, // { lat, lon } — device geolocation fix
  accuracyRadiusMeters = null, // device-reported GPS accuracy, kept visually distinct from the search radius
  selectedFacilityId = null,
  onSelectFacility,
  focusTarget = null, // { lat, lon, zoom, token }
  heightClassName = "h-[420px]",
  // Interactive picking props
  isPicking = false,
  onPointPick = null, // (latlng, type: 'origin' | 'destination') => void
  onMarkerDrag = null, // (latlng, type: 'origin' | 'destination') => void
  onViewportIdle = null, // ({ lat, lon }) => void — fires after pan/zoom settles; see ViewportIdleReporter
}) {
  const routeLatLngs = useMemo(() => geometryToLatLngs(routeGeometry), [routeGeometry]);
  const fitBounds = useMemo(() => {
    if (fitMode !== "route") return [];
    const pts = [];
    if (routeLatLngs.length > 0) pts.push(...routeLatLngs);
    if (isValidPoint(origin)) pts.push([origin.lat, origin.lon]);
    if (isValidPoint(destination)) pts.push([destination.lat, destination.lon]);
    facilities.forEach((f) => {
      const pos = coordToLatLng(f.coordinates);
      if (pos && isValidLatLng(pos[0], pos[1])) pts.push(pos);
    });
    return pts;
  }, [fitMode, routeLatLngs, origin, destination, facilities]);

  const resolvedCenter = center || fitBounds[0] || DEFAULT_CENTER;
  const resolvedZoom = zoom || DEFAULT_ZOOM;

  const handleMapPick = useCallback((latlng) => {
    if (!isPicking || !onPointPick) return;
    const type = !isValidPoint(origin)
      ? "origin"
      : !isValidPoint(destination)
        ? "destination"
        : "origin";
    onPointPick(latlng, type);
  }, [isPicking, onPointPick, origin, destination]);

  return (
    <div className={`relative w-full overflow-hidden rounded-2xl border border-slate-200 ${heightClassName}`}>
      <MapContainer
        center={resolvedCenter}
        zoom={resolvedZoom}
        scrollWheelZoom
        className={`h-full w-full ${isPicking ? "cursor-crosshair" : ""}`}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url={OSM_TILE_URL}
        />

        <ScaleControl position="bottomleft" imperial={false} />
        <ResizeHandler />
        <MapClickHandler enabled={isPicking && !!onPointPick} onPick={handleMapPick} />
        {onViewportIdle && <ViewportIdleReporter onViewportIdle={onViewportIdle} />}

        {fitMode === "route" ? (
          <FitToContent bounds={fitBounds} />
        ) : (
          <SetViewTo center={center || null} zoom={zoom} />
        )}
        <FocusHandler target={focusTarget} />
        <FitRadiusControl searchCenter={searchCenter} searchRadiusMeters={searchRadiusMeters} />

        {routeLatLngs.length > 1 && (
          <Polyline
            positions={routeLatLngs}
            pathOptions={{
              color: "#203C5A",
              weight: 7,
              opacity: 0.9,
              // A high-contrast casing keeps the route legible over tile labels
              // and at low zoom levels where a thin line would disappear.
            }}
          />
        )}
        {routeLatLngs.length > 1 && (
          <Polyline
            positions={routeLatLngs}
            pathOptions={{ color: "#f7f8fa", weight: 3, opacity: 0.85, dashArray: "1 9" }}
          />
        )}

        {isValidPoint(searchCenter) && Number.isFinite(searchRadiusMeters) && searchRadiusMeters > 0 && (
          <Circle
            center={[searchCenter.lat, searchCenter.lon]}
            radius={searchRadiusMeters}
            pathOptions={{
              color: "#203C5A",
              weight: 2.5,
              fillColor: "#203C5A",
              fillOpacity: 0.06,
              dashArray: "4 6",
            }}
          />
        )}

        {isValidPoint(accuracyCenter) && Number.isFinite(accuracyRadiusMeters) && accuracyRadiusMeters > 0 && (
          <Circle
            center={[accuracyCenter.lat, accuracyCenter.lon]}
            radius={accuracyRadiusMeters}
            pathOptions={{ color: "#2563EB", weight: 1.5, fillColor: "#2563EB", fillOpacity: 0.12, dashArray: "2 4" }}
          />
        )}

        {isValidPoint(origin) && (
          <Marker
            position={[origin.lat, origin.lon]}
            icon={endpointIcon("origin")}
            draggable={isPicking && !!onMarkerDrag}
            eventHandlers={onMarkerDrag ? {
              dragend: (e) => onMarkerDrag(e.target.getLatLng(), 'origin')
            } : undefined}
          >
            <Popup>
              <strong>{originTitle}</strong>
              <br />
              {origin.label}
            </Popup>
          </Marker>
        )}

        {isValidPoint(destination) && (
          <Marker
            position={[destination.lat, destination.lon]}
            icon={endpointIcon("destination")}
            draggable={isPicking && !!onMarkerDrag}
            eventHandlers={onMarkerDrag ? {
              dragend: (e) => onMarkerDrag(e.target.getLatLng(), 'destination')
            } : undefined}
          >
            <Popup>
              <strong>Destination</strong>
              <br />
              {destination.label}
            </Popup>
          </Marker>
        )}

        {facilities.map((facility, idx) => {
          const pos = coordToLatLng(facility.coordinates);
          if (!pos || !isValidLatLng(pos[0], pos[1])) return null;
          const facilityId = facility.id || `facility-${idx}`;
          const selected = selectedFacilityId != null && facilityId === selectedFacilityId;
          return (
            <Marker
              key={facilityId}
              position={pos}
              icon={facilityIcon(facility.category, isFacilityVerified(facility), selected)}
              eventHandlers={onSelectFacility ? { click: () => onSelectFacility(facilityId) } : undefined}
            >
              <Popup>
                <strong>{facility.name || "Unnamed facility"}</strong>
                <br />
                {FACILITY_CATEGORY_LABELS[facility.category] || facility.category}
                {facility.distance_km !== null && facility.distance_km !== undefined && (
                  <> · {formatDistance(facility.distance_km)}</>
                )}
                <br />
                <span className={isFacilityVerified(facility) ? "text-emerald-700" : "text-amber-700"}>
                  {facilityVerificationLabel(facility.verification_status)}
                </span>
                {facility.address && (
                  <>
                    <br />
                    <span className="text-slate-500">{facility.address}</span>
                  </>
                )}
              </Popup>
            </Marker>
          );
        })}

        {alerts.map((alert, idx) => {
          const pos = coordToLatLng(alert.location);
          if (!pos || !isValidLatLng(pos[0], pos[1])) return null;
          return (
            <Marker key={alert.id || `alert-${idx}`} position={pos} icon={alertIcon(alert.severity)}>
              <Popup>
                {isDemoAlert(alert) && (
                  <p className="mb-1 font-semibold text-amber-700">Demo data — not a real incident</p>
                )}
                <p>{alert.description}</p>
              </Popup>
            </Marker>
          );
        })}

        <RecenterControl fitMode={fitMode} bounds={fitBounds} center={center || null} zoom={zoom} />
      </MapContainer>
    </div>
  );
}
