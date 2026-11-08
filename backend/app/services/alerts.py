"""
Travel alerts service.

Primary source: NASA's Earth Observatory Natural Event Tracker (EONET),
https://eonet.gsfc.nasa.gov/docs/v3 - a free, keyless, actively-maintained
feed of ongoing natural-hazard events (wildfires, severe storms, floods,
volcanoes, landslides, etc.), each with real coordinates and a last-observed
timestamp. It is NOT a traffic/road-closure feed (no such free, keyless,
sufficiently-current source was found for this project - see README "Known
Limitations"), but it is a genuine, verifiable, currently-documented API
whose response shape has actually been inspected (see `_normalize_event`
below) - consistent with this project's core rule: never guess a provider's
schema, never fabricate data.

This is the "NASA API" half of what this deployment can use out of the
box. (ISRO's Bhuvan platform was also evaluated - see README "Known
Limitations" for why it was not wired in the same way: its API portal
issues access tokens that expire after ~24h via an interactive login,
not a stable key suitable for a long-lived `.env` value, and its JSON
response shapes for the endpoints relevant here are not publicly
documented well enough to normalize without guessing - both of which
conflict with this project's no-guessing, no-silent-breakage rules. It
remains a reasonable follow-up once someone can maintain a refreshed
token.)
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import List, Optional, Dict

import httpx

from app.core.config import Settings
from app.schemas.alert import Alert, AlertSeverity
from app.schemas.common import Coordinates
from app.services.exceptions import ServiceResponseError, ServiceUnavailableError

logger = logging.getLogger("wayfinder.services.alerts")

# EONET category id -> severity for this app's driving-risk purposes. Not
# NASA's own severity (EONET doesn't publish one) - a conservative mapping
# we own, documented here the same way app/services/weather.py documents
# ADVERSE_WEATHER_CODES. Categories whose relevance to road travel is not
# clear-cut are mapped to "unknown" rather than guessed (per this project's
# rule: never assign an arbitrary severity) - they are still returned and
# listed, just not scored by the risk engine.
# Full category list: https://eonet.gsfc.nasa.gov/api/v3/categories
EONET_CATEGORY_SEVERITY: Dict[str, AlertSeverity] = {
    "floods": "high",  # washouts, impassable roads
    "landslides": "high",  # direct road-blocking hazard
    "volcanoes": "high",  # ashfall, evacuation-level hazard
    "wildfires": "moderate",  # smoke/visibility, possible closures
    "severeStorms": "moderate",
    "winterStorm": "moderate",
    "snow": "moderate",
    "dustHaze": "moderate",  # visibility hazard
    "earthquakes": "moderate",  # secondary road/bridge damage risk
    "tempExtremes": "low",  # health risk, not a direct driving hazard
    "drought": "low",
    "seaLakeIce": "unknown",  # not a road-travel hazard in general
    "waterColor": "unknown",  # not a road-travel hazard
    "manmade": "unknown",  # too varied to assign a severity without specifics
}

_EARTH_RADIUS_KM = 6371.0088


def _haversine_km(a: Coordinates, b: Coordinates) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [a.lat, a.lon, b.lat, b.lon])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _combined_bbox(points: List[Coordinates], pad_km: float) -> str:
    """EONET bbox query param: 'min_lon,max_lat,max_lon,min_lat' (per
    https://eonet.gsfc.nasa.gov/docs/v3), padded by `pad_km` so events just
    outside the point cluster aren't missed by the rectangle before the
    real haversine-distance filter runs."""
    lats = [p.lat for p in points]
    lons = [p.lon for p in points]
    ref_lat = sum(lats) / len(lats)
    dlat = pad_km / 111.32
    # Guard against the degenerate cos(90) case even though road trips
    # never approach the poles.
    dlon = pad_km / (111.32 * max(math.cos(math.radians(ref_lat)), 0.01))
    min_lon, max_lon = min(lons) - dlon, max(lons) + dlon
    min_lat, max_lat = min(lats) - dlat, max(lats) + dlat
    return f"{min_lon:.4f},{max_lat:.4f},{max_lon:.4f},{min_lat:.4f}"


def _nearest_point_distance_km(
    points: List[Coordinates], target: Coordinates
) -> float:
    return min(_haversine_km(target, p) for p in points)


class AlertService:
    def __init__(self, settings: Settings, client: Optional[httpx.AsyncClient] = None):
        self._settings = settings
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._settings.REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": self._settings.HTTP_USER_AGENT},
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def get_alerts(
        self, point: Coordinates, radius_km: float = 25.0
    ) -> List[Alert]:
        """Single-point lookup, used by GET /api/v1/alerts."""
        return await self.get_alerts_for_route([point], radius_km)

    async def get_alerts_for_route(
        self, points: List[Coordinates], radius_km: float = 25.0
    ) -> List[Alert]:
        """Alerts relevant to ANY of `points` (typically origin/midpoint/
        destination for a journey, or a single point for the standalone
        endpoint). One EONET request covers every point via a combined
        bounding box, rather than one request per point."""
        if not points:
            return []
        if not self._settings.alerts_configured:
            raise ServiceUnavailableError(
                "ALERT_PROVIDER_URL is not configured for this deployment.",
                provider="alerts",
                reason="not_configured",
            )

        client = await self._get_client()
        return await self._fetch_eonet(client, points, radius_km)

    # ---- NASA EONET ----

    async def _fetch_eonet(
        self, client: httpx.AsyncClient, points: List[Coordinates], radius_km: float
    ) -> List[Alert]:
        base = self._settings.ALERT_PROVIDER_URL.rstrip("/")
        url = f"{base}/events" if not base.endswith("/events") else base
        params = {
            "status": "open",
            "days": self._settings.ALERT_DAYS_LOOKBACK,
            "bbox": _combined_bbox(points, radius_km),
            "limit": 100,
        }
        headers = {}
        if self._settings.ALERT_PROVIDER_KEY:
            # EONET itself is keyless; this is only sent in case
            # ALERT_PROVIDER_URL has been pointed at a different,
            # key-requiring provider with a compatible contract.
            headers["Authorization"] = f"Bearer {self._settings.ALERT_PROVIDER_KEY}"

        try:
            resp = await client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise ServiceUnavailableError(
                f"Alerts request timed out: {exc}", provider="alerts"
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                f"Alerts request failed: {exc}", provider="alerts"
            ) from exc

        if resp.status_code == 429:
            raise ServiceUnavailableError(
                "Alerts provider rate-limited the request",
                provider="alerts",
                reason="rate_limited",
            )
        if resp.status_code >= 500:
            raise ServiceUnavailableError(
                f"Alerts provider returned server error {resp.status_code}",
                provider="alerts",
            )
        if resp.status_code >= 400:
            raise ServiceResponseError(
                f"Alerts provider returned client error {resp.status_code}",
                provider="alerts",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise ServiceResponseError(
                "Alerts provider returned invalid JSON", provider="alerts"
            ) from exc

        events = data.get("events")
        if events is None:
            raise ServiceResponseError(
                "Alerts provider response missing 'events'", provider="alerts"
            )

        alerts: List[Alert] = []
        for event in events:
            alert = self._normalize_event(event, points, radius_km)
            if alert is not None:
                alerts.append(alert)
        return alerts

    def _normalize_event(
        self, event: dict, points: List[Coordinates], radius_km: float
    ) -> Optional[Alert]:
        """Per https://eonet.gsfc.nasa.gov/docs/v3: each event has `id`,
        `title`, `categories` (list of {id, title}), and `geometry` (list
        of {date, type, coordinates: [lon, lat]} - storms have many
        time-stamped points, most other categories have one). We use the
        MOST RECENT geometry point as the event's current location."""
        geometry = event.get("geometry") or []
        if not geometry:
            return None
        latest = geometry[-1]
        coords = latest.get("coordinates")
        if (
            not isinstance(coords, list)
            or len(coords) != 2
            or latest.get("type") != "Point"
        ):
            # Polygon/other geometry types exist for a few EONET categories;
            # skip rather than guess a representative point for them.
            return None
        try:
            lon, lat = float(coords[0]), float(coords[1])
            location = Coordinates(lat=lat, lon=lon)
        except (TypeError, ValueError):
            return None

        distance_km = _nearest_point_distance_km(points, location)
        if distance_km > radius_km:
            # The bbox is a rectangle padded by radius_km around the whole
            # point cluster, so it can admit events in its corners that are
            # genuinely farther than radius_km from every actual point.
            return None

        categories = event.get("categories") or []
        category_id = categories[0].get("id") if categories else None
        category_title = categories[0].get("title") if categories else None
        severity = EONET_CATEGORY_SEVERITY.get(category_id, "unknown")

        retrieved_at = None
        raw_date = latest.get("date")
        if raw_date:
            try:
                retrieved_at = datetime.fromisoformat(
                    raw_date.replace("Z", "+00:00")
                ).astimezone(timezone.utc)
            except ValueError:
                retrieved_at = None

        sources = event.get("sources") or []
        source_names = ", ".join(s.get("id", "") for s in sources if s.get("id")) or None

        return Alert(
            id=event.get("id"),
            description=event.get("title") or "Untitled natural-hazard event",
            category=category_title or category_id,
            severity=severity,
            location=location,
            source="nasa-eonet" + (f" ({source_names})" if source_names else ""),
            retrieved_at=retrieved_at,
            verified=None,  # EONET aggregates from multiple agencies; it
            # does not itself mark an individual event as independently
            # verified, so this is honestly "unknown" rather than assumed.
            relevance=f"{distance_km:.1f} km from the nearest checked route point "
            f"(within the {radius_km:.0f} km search radius).",
        )

    # ---- NASA EONET ----
