import { useEffect, useMemo, useRef, useState } from "react";
// maplibre-gl's ESM build ships only named exports (no default export), so
// this must be a namespace import — `import maplibregl from "maplibre-gl"`
// builds fine under Vite's dev server but fails a production build with a
// "default is not exported" error.
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Globe2, AlertTriangle, Loader2 } from "lucide-react";
import { circlePolygonCoords, zoomForRadiusMeters, isValidPoint } from "../../lib/geo.js";
import { CATEGORY_COLOR } from "../../lib/mapIcons.js";
import { isFacilityVerified } from "../../lib/format.js";

/**
 * GlobeMapView — a photorealistic 3D Earth globe projection for wide-radius
 * (>20km, up to 70km) Nearby Places searches, built on MapLibre GL JS.
 *
 * Combines keyless high-resolution global satellite imagery (Esri World
 * Imagery), 3D surface elevation via AWS Terrarium DEM tiles, viewport-anchored
 * directional lighting, and a deep-space atmospheric backdrop while keeping
 * all facility clustering, geodesic radius rendering, and selection contracts.
 */

const SATELLITE_TILE_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const SATELLITE_ATTRIBUTION =
  'Tiles &copy; <a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a> &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community';

const TERRAIN_DEM_URL =
  "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const TERRAIN_DEM_SOURCE_ID = "terrain-dem";

const SPACE_BACKGROUND_COLOR = "#050811";

// Zoom band the projection crossfades over, via MapLibre's own
// interpolate-expression support for the style's `projection` property.
// Chosen to match the radius thresholds in geo.js: a >20km search resolves
// (via zoomForRadiusMeters) to roughly zoom 8-10, i.e. already inside this
// band, so the globe is fully formed on mount; zooming in further within
// this view fades smoothly to a flat mercator map.
const PROJECTION_GLOBE_ZOOM = 8;
const PROJECTION_MERCATOR_ZOOM = 10;

const SEARCH_RADIUS_SOURCE_ID = "search-radius";
const FACILITIES_SOURCE_ID = "facilities";

function buildStyle() {
  return {
    version: 8,
    projection: {
      type: [
        "interpolate",
        ["linear"],
        ["zoom"],
        PROJECTION_GLOBE_ZOOM,
        "vertical-perspective",
        PROJECTION_MERCATOR_ZOOM,
        "mercator",
      ],
    },
    light: {
      anchor: "viewport",
      color: "#ffffff",
      intensity: 0.35,
      position: [1.15, 210, 30],
    },
    sources: {
      "satellite-raster": {
        type: "raster",
        tiles: [SATELLITE_TILE_URL],
        tileSize: 256,
        attribution: SATELLITE_ATTRIBUTION,
        maxzoom: 19,
      },
      [TERRAIN_DEM_SOURCE_ID]: {
        type: "raster-dem",
        tiles: [TERRAIN_DEM_URL],
        tileSize: 256,
        encoding: "terrarium",
        maxzoom: 15,
      },
    },
    layers: [
      {
        id: "space-background",
        type: "background",
        paint: {
          "background-color": SPACE_BACKGROUND_COLOR,
        },
      },
      {
        id: "satellite-raster-layer",
        type: "raster",
        source: "satellite-raster",
      },
    ],
  };
}

function searchRadiusGeoJSON(searchCenter, searchRadiusMeters) {
  if (!isValidPoint(searchCenter) || !Number.isFinite(searchRadiusMeters) || searchRadiusMeters <= 0) {
    return { type: "FeatureCollection", features: [] };
  }
  const ring = circlePolygonCoords(searchCenter.lat, searchCenter.lon, searchRadiusMeters);
  if (ring.length < 4) return { type: "FeatureCollection", features: [] };
  return {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } }],
  };
}

function facilitiesGeoJSON(facilities, selectedFacilityId) {
  const features = [];
  facilities.forEach((f, idx) => {
    if (!isValidPoint(f.coordinates)) return; // skip rather than guess, matching the Leaflet view
    const id = f.id || `facility-${idx}`;
    features.push({
      type: "Feature",
      id: idx, // numeric feature id required for MapLibre clustering internals
      geometry: { type: "Point", coordinates: [f.coordinates.lon, f.coordinates.lat] },
      properties: {
        facilityId: id,
        category: f.category,
        name: f.name || "Unnamed facility",
        verified: isFacilityVerified(f),
        selected: selectedFacilityId != null && id === selectedFacilityId,
      },
    });
  });
  return { type: "FeatureCollection", features };
}

const CATEGORY_COLOR_MATCH = [
  "match",
  ["get", "category"],
  "hospital",
  CATEGORY_COLOR.hospital,
  "fuel",
  CATEGORY_COLOR.fuel,
  "restaurant",
  CATEGORY_COLOR.restaurant,
  "rest_stop",
  CATEGORY_COLOR.rest_stop,
  "pharmacy",
  CATEGORY_COLOR.pharmacy,
  "lodging",
  CATEGORY_COLOR.lodging,
  "#475569",
];

export default function GlobeMapView({
  searchCenter = null, // { lat, lon, label }
  searchRadiusMeters = null,
  facilities = [],
  selectedFacilityId = null,
  onSelectFacility,
  onReturnToFlatView,
  heightClassName = "h-full",
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const lastViewSignatureRef = useRef(null);
  // Kept current via an effect (not assigned during render) so the
  // "load"-time click handler below — which closes over this ref once and
  // never needs to be re-registered — always calls the latest callback.
  const onSelectFacilityRef = useRef(onSelectFacility);
  useEffect(() => {
    onSelectFacilityRef.current = onSelectFacility;
  }, [onSelectFacility]);

  const [mapReady, setMapReady] = useState(false);
  const [tileError, setTileError] = useState(false);

  // Resolved once per mount for the initial camera; kept stable even if the
  // caller's object identity changes on every render.
  const initialCenter = useMemo(() => {
    if (!isValidPoint(searchCenter)) return [0, 20];
    return [searchCenter.lon, searchCenter.lat];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const initialZoom = useMemo(() => {
    if (!isValidPoint(searchCenter)) return 2;
    return zoomForRadiusMeters(searchRadiusMeters, searchCenter.lat);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // maplibre-gl 6.x requires WebGL2 unconditionally (no WebGL1 fallback) and
  // no longer ships a `maplibregl.supported()` helper to check that, so this
  // does the equivalent check directly.
  const supported = useMemo(() => {
    try {
      const canvas = document.createElement("canvas");
      return !!(window.WebGL2RenderingContext && canvas.getContext("webgl2"));
    } catch {
      return false;
    }
  }, []);

  // --- Create the map once on mount; tear it down on unmount. ------------
  useEffect(() => {
    if (!supported || !containerRef.current) return undefined;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildStyle(),
      center: initialCenter,
      zoom: initialZoom,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");

    map.on("load", () => {
      map.setTerrain({ source: TERRAIN_DEM_SOURCE_ID, exaggeration: 1.5 });
      map.setLight({
        anchor: "viewport",
        color: "#ffffff",
        intensity: 0.35,
        position: [1.15, 210, 30],
      });

      map.addSource(SEARCH_RADIUS_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "search-radius-fill",
        type: "fill",
        source: SEARCH_RADIUS_SOURCE_ID,
        paint: { "fill-color": "#203C5A", "fill-opacity": 0.06 },
      });
      map.addLayer({
        id: "search-radius-line",
        type: "line",
        source: SEARCH_RADIUS_SOURCE_ID,
        paint: { "line-color": "#203C5A", "line-width": 2.5, "line-dasharray": [2, 2] },
      });

      map.addSource(FACILITIES_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        cluster: true,
        clusterRadius: 45,
        clusterMaxZoom: 11,
      });
      map.addLayer({
        id: "facility-clusters",
        type: "circle",
        source: FACILITIES_SOURCE_ID,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#203C5A",
          "circle-opacity": 0.85,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-radius": ["step", ["get", "point_count"], 14, 10, 18, 50, 24],
        },
      });
      map.addLayer({
        id: "facility-cluster-count",
        type: "symbol",
        source: FACILITIES_SOURCE_ID,
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-font": ["Noto Sans Bold"],
          "text-size": 12,
        },
        paint: { "text-color": "#ffffff" },
      });
      map.addLayer({
        id: "facility-points",
        type: "circle",
        source: FACILITIES_SOURCE_ID,
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": CATEGORY_COLOR_MATCH,
          "circle-radius": ["case", ["get", "selected"], 10, 7],
          "circle-opacity": ["case", ["get", "verified"], 1, 0.55],
          "circle-stroke-width": ["case", ["get", "selected"], 3, 1.5],
          "circle-stroke-color": "#ffffff",
        },
      });

      map.on("click", "facility-clusters", (e) => {
        const [feature] = map.queryRenderedFeatures(e.point, { layers: ["facility-clusters"] });
        const clusterId = feature?.properties?.cluster_id;
        const source = map.getSource(FACILITIES_SOURCE_ID);
        if (clusterId == null || !source) return;
        source.getClusterExpansionZoom(clusterId, (err, zoom) => {
          if (err) return;
          map.easeTo({ center: feature.geometry.coordinates, zoom, duration: 400 });
        });
      });

      map.on("click", "facility-points", (e) => {
        const feature = e.features?.[0];
        const facilityId = feature?.properties?.facilityId;
        if (facilityId != null) onSelectFacilityRef.current?.(facilityId);

        if (feature) {
          const { name, category } = feature.properties;
          new maplibregl.Popup({ closeButton: true, offset: 12 })
            .setLngLat(feature.geometry.coordinates)
            .setHTML(
              `<strong>${escapeHtml(name)}</strong><br/><span style="color:#5b6778">${escapeHtml(category)}</span>`
            )
            .addTo(map);
        }
      });

      ["facility-clusters", "facility-points"].forEach((layerId) => {
        map.on("mouseenter", layerId, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = "";
        });
      });

      setMapReady(true);
    });

    // Tile/style errors (network failure, provider outage, etc.) — surfaced
    // as a dismissable banner rather than left as a silently blank map.
    map.on("error", () => setTileError(true));

    const resizeObserver =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => map.resize()) : null;
    resizeObserver?.observe(containerRef.current);

    return () => {
      resizeObserver?.disconnect();
      markerRef.current?.remove();
      map.remove();
      mapRef.current = null;
    };
    // Intentionally mount-only: the map instance is created once and
    // updated imperatively below, matching the Leaflet MapView's own
    // pattern of dedicated effects per concern instead of recreating the
    // map on every prop change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supported]);

  // --- Keep the search-center marker, radius circle and camera in sync. --
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    if (!markerRef.current) {
      const el = document.createElement("div");
      el.style.cssText =
        "width:16px;height:16px;border-radius:9999px;background:#16A34A;border:3px solid #ffffff;box-shadow:0 1px 4px rgba(0,0,0,0.5);";
      markerRef.current = new maplibregl.Marker({ element: el });
    }

    if (isValidPoint(searchCenter)) {
      markerRef.current.setLngLat([searchCenter.lon, searchCenter.lat]).addTo(map);
    } else {
      markerRef.current.remove();
    }

    map.getSource(SEARCH_RADIUS_SOURCE_ID)?.setData(searchRadiusGeoJSON(searchCenter, searchRadiusMeters));

    // Only recenter when the search point/radius actually changed — never
    // on every unrelated re-render — so a user who has manually panned or
    // rotated the globe doesn't get yanked back. Mirrors FitToContent /
    // SetViewTo's signature-dedup pattern in the Leaflet MapView.
    const signature = isValidPoint(searchCenter)
      ? `${searchCenter.lat.toFixed(5)},${searchCenter.lon.toFixed(5)},${searchRadiusMeters}`
      : null;
    if (signature && signature !== lastViewSignatureRef.current) {
      lastViewSignatureRef.current = signature;
      map.easeTo({
        center: [searchCenter.lon, searchCenter.lat],
        zoom: zoomForRadiusMeters(searchRadiusMeters, searchCenter.lat),
        duration: 600,
      });
    }
  }, [mapReady, searchCenter, searchRadiusMeters]);

  // --- Keep facility markers in sync with search results/selection. ------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    map.getSource(FACILITIES_SOURCE_ID)?.setData(facilitiesGeoJSON(facilities, selectedFacilityId));
  }, [mapReady, facilities, selectedFacilityId]);

  if (!supported) {
    return (
      <div className={`flex ${heightClassName} w-full flex-col items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-600`}>
        <AlertTriangle size={20} className="text-amber-600" />
        <p>This browser can&apos;t display the 3D globe view (it needs WebGL2 support).</p>
        {onReturnToFlatView && (
          <button type="button" onClick={onReturnToFlatView} className="btn-ghost mt-1">
            Switch to regional view
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className={`relative w-full overflow-hidden rounded-2xl border border-slate-800 bg-[#050811] ${heightClassName}`}
      style={{
        backgroundColor: SPACE_BACKGROUND_COLOR,
        backgroundImage:
          "radial-gradient(circle at 50% 50%, rgba(56, 189, 248, 0.18) 0%, rgba(14, 116, 144, 0.08) 45%, rgba(5, 8, 17, 0.96) 75%, #050811 100%)",
        boxShadow: "inset 0 0 60px rgba(56, 189, 248, 0.12)",
      }}
    >
      <div
        ref={containerRef}
        className="h-full w-full bg-[#050811]"
        style={{
          backgroundColor: SPACE_BACKGROUND_COLOR,
          backgroundImage:
            "radial-gradient(circle at 50% 50%, rgba(30, 64, 175, 0.22) 0%, rgba(14, 165, 233, 0.08) 42%, #050811 72%)",
        }}
        role="application"
        aria-label="3D globe map of the search area"
      />

      {!mapReady && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 bg-[#050811]/90 text-sm text-slate-300">
          <Loader2 size={16} className="animate-spin" /> Loading globe…
        </div>
      )}

      {tileError && (
        <div className="absolute left-2.5 top-2.5 z-10 flex max-w-[calc(100%-5rem)] items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 shadow-sm">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>Map tiles are having trouble loading. The globe may look incomplete until they recover.</span>
        </div>
      )}

      {onReturnToFlatView && (
        <button
          type="button"
          onClick={onReturnToFlatView}
          title="Return to street/regional view"
          aria-label="Return to street/regional view"
          className="absolute bottom-4 left-2.5 z-10 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
        >
          <Globe2 size={14} /> Back to regional view
        </button>
      )}
    </div>
  );
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}