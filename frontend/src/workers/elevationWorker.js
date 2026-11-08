// frontend/src/workers/elevationWorker.js
//
// Deliberately uses the exact same keyless AWS Terrarium DEM tile source
// GlobeMapView.jsx already loads for 3D terrain (TERRAIN_DEM_URL /
// TERRAIN_DEM_SOURCE_ID) — so this feature needs no new backend endpoint,
// no new API key, and no new provider to manage in config.py. It's the
// same public tiles, just decoded for their elevation value instead of
// rendered as a mesh.
//
// Terrarium PNG encoding (per the format's spec):
//   elevation_meters = (R * 256 + G + B / 256) - 32768
//
// Protocol:
//   -> { type: "profile", requestId, points: [{ lat, lon, distanceKm }] }
//   <- { type: "profile", requestId, samples: [{ lat, lon, distanceKm, elevationM }] }
//   <- { type: "error", requestId, message }

const TERRAIN_DEM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const TILE_SIZE = 256;
const ZOOM = 11; // ~40-75m/px depending on latitude — plenty for a route profile; raise if you need sharper local detail

// Decoded tiles are cached for the lifetime of the worker (keyed by
// "z/x/y") so a route that loops back near itself, or a re-sampled
// profile after a minor route tweak, doesn't re-fetch tiles it already
// decoded.
const tileCache = new Map();

function lonLatToTileFraction(lon, lat, zoom) {
  const n = 2 ** zoom;
  const x = ((lon + 180) / 360) * n;
  const latRad = (lat * Math.PI) / 180;
  const y = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
  return { x, y };
}

async function loadTile(z, x, y) {
  const key = `${z}/${x}/${y}`;
  if (tileCache.has(key)) return tileCache.get(key);

  const promise = (async () => {
    const url = TERRAIN_DEM_URL.replace("{z}", z).replace("{x}", x).replace("{y}", y);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`DEM tile ${key} failed (${res.status})`);
    const blob = await res.blob();
    const bitmap = await createImageBitmap(blob);
    const canvas = new OffscreenCanvas(TILE_SIZE, TILE_SIZE);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(bitmap, 0, 0);
    const { data } = ctx.getImageData(0, 0, TILE_SIZE, TILE_SIZE);
    return data; // Uint8ClampedArray, RGBA, row-major
  })();

  tileCache.set(key, promise);
  return promise;
}

function elevationFromPixel(data, px, py) {
  const i = (py * TILE_SIZE + px) * 4;
  const r = data[i];
  const g = data[i + 1];
  const b = data[i + 2];
  return r * 256 + g + b / 256 - 32768;
}

async function elevationAt(lat, lon) {
  const { x, y } = lonLatToTileFraction(lon, lat, ZOOM);
  const tileX = Math.floor(x);
  const tileY = Math.floor(y);
  const data = await loadTile(ZOOM, tileX, tileY);

  // Bilinear interpolation across the pixel's fractional position so
  // adjacent route samples don't visibly "step" between whole-pixel
  // elevation values.
  const fx = (x - tileX) * TILE_SIZE;
  const fy = (y - tileY) * TILE_SIZE;
  const x0 = Math.min(TILE_SIZE - 1, Math.floor(fx));
  const y0 = Math.min(TILE_SIZE - 1, Math.floor(fy));
  const x1 = Math.min(TILE_SIZE - 1, x0 + 1);
  const y1 = Math.min(TILE_SIZE - 1, y0 + 1);
  const tx = fx - x0;
  const ty = fy - y0;

  const e00 = elevationFromPixel(data, x0, y0);
  const e10 = elevationFromPixel(data, x1, y0);
  const e01 = elevationFromPixel(data, x0, y1);
  const e11 = elevationFromPixel(data, x1, y1);

  const top = e00 + (e10 - e00) * tx;
  const bottom = e01 + (e11 - e01) * tx;
  return top + (bottom - top) * ty;
}

self.onmessage = async (event) => {
  const { type, requestId, points } = event.data;
  if (type !== "profile") return;

  try {
    // Dedupe + fetch each distinct tile once, then resolve every sample
    // point against the (now-cached) tile data — a ~5km route sampled at
    // 150 points might touch only a handful of distinct tiles at zoom 11.
    const samples = await Promise.all(
      points.map(async (p) => ({
        lat: p.lat,
        lon: p.lon,
        distanceKm: p.distanceKm,
        elevationM: Math.round(await elevationAt(p.lat, p.lon)),
      }))
    );
    self.postMessage({ type: "profile", requestId, samples });
  } catch (error) {
    self.postMessage({ type: "error", requestId, message: error?.message || "Elevation lookup failed." });
  }
};
