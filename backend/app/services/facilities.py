"""
Facility search service.

Uses the OpenStreetMap Overpass API to find mapped facilities near a
point. Overpass data is community-maintained: names, categories and
addresses may be missing or incomplete, which this module reflects
rather than papers over (fields are left null instead of guessed).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from app.core.config import Settings
from app.schemas.common import Coordinates
from app.schemas.facility import Facility, FacilityCategory
from app.services.exceptions import ServiceResponseError, ServiceUnavailableError


@dataclass
class FacilityNearbyResult:
    """Return type of FacilityService.search_nearby.

    `truncated`/`limit` carry the honest result-limiting signal required by
    the hybrid map-to-globe spec (section 7): a wide-radius search can hit
    the Overpass element cap before every real nearby facility is found, and
    the API must say so rather than silently returning a partial list as if
    it were exhaustive. See FacilityService._overpass_out_limit.
    """

    facilities: List[Facility]
    truncated: bool = False
    limit: Optional[int] = None

# Facilities "along the route" are approximated as the union of independent
# nearby-searches around a small, fixed number of sample points (never a
# true continuous corridor query - Overpass has no efficient primitive for
# that, and an unbounded number of samples would risk excessive requests
# against a shared public instance). This cap is deliberate - see
# docs/API_CONTRACT.md "Route-aware facilities/weather" for the full
# rationale and limitation.
MAX_ROUTE_SAMPLE_POINTS = 3

logger = logging.getLogger("wayfinder.services.facilities")

# Map our stable category names to OSM tag filters. Overpass QL fragments.
_CATEGORY_OSM_TAGS: Dict[str, List[str]] = {
    "hospital": ['["amenity"="hospital"]'],
    "fuel": ['["amenity"="fuel"]'],
    # Broadened to match what the frontend already labels this category as
    # ("Restaurants & cafés", see OverviewPage.jsx) - previously only
    # amenity=restaurant was queried, so a genuine nearby cafe or fast-food
    # stop was never detected despite the UI implying it would be.
    "restaurant": [
        '["amenity"="restaurant"]',
        '["amenity"="cafe"]',
        '["amenity"="fast_food"]',
    ],
    # OSM has no single canonical "rest stop" tag; highway=rest_area and
    # highway=services both represent driver rest facilities.
    "rest_stop": ['["highway"="rest_area"]', '["highway"="services"]'],
    "pharmacy": ['["amenity"="pharmacy"]'],
    # Deliberately excludes tourism=hostel/apartment/camp_site - those are a
    # meaningfully different kind of stop than a traveler expects under
    # "Lodging" (budget dorm-style / self-catering / camping, respectively);
    # narrower-but-accurate beats broad-but-misleading, same reasoning the
    # restaurant/fuel categories already follow elsewhere in this module.
    "lodging": [
        '["tourism"="hotel"]',
        '["tourism"="motel"]',
        '["tourism"="guest_house"]',
    ],
}


def _haversine_km(a: Coordinates, b: Coordinates) -> float:
    r = 6371.0088
    lat1, lon1, lat2, lon2 = map(math.radians, [a.lat, a.lon, b.lat, b.lon])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return round(2 * r * math.asin(math.sqrt(h)), 2)


class FacilityService:
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

    def _is_large_radius(self, radius_km: float) -> bool:
        return radius_km > self._settings.FACILITY_LARGE_RADIUS_THRESHOLD_KM

    def _request_timeout_seconds(self, radius_km: float) -> float:
        """
        Per-request HTTP timeout AND the Overpass `[timeout:N]` query clause.
        Wide-radius (globe-view) searches cover far more area and can
        legitimately take longer than the default REQUEST_TIMEOUT_SECONDS
        (shared by every other provider call) allows - see
        FACILITY_LARGE_RADIUS_TIMEOUT_SECONDS in config.py for why this is a
        separate, explicit setting rather than raising the global default or
        blindly hardcoding a larger number here.
        """
        if self._is_large_radius(radius_km):
            return self._settings.FACILITY_LARGE_RADIUS_TIMEOUT_SECONDS
        return self._settings.REQUEST_TIMEOUT_SECONDS

    def _overpass_out_limit(self, radius_km: float, n_categories: int) -> int:
        """
        The Overpass `out center N` cap. The original `n*50+50` formula is
        kept unchanged for small-radius searches (it already works well
        there); a wide-radius search is capped at the larger, explicit
        FACILITY_LARGE_RADIUS_RESULT_LIMIT instead, since a 70km-radius area
        can easily contain far more mapped facilities than a 1km one and the
        small formula would arbitrarily under-cover it. Either way this is
        an explicit, named setting - never an unevaluated blind constant.
        """
        small_radius_limit = n_categories * 50 + 50
        if self._is_large_radius(radius_km):
            return max(small_radius_limit, self._settings.FACILITY_LARGE_RADIUS_RESULT_LIMIT)
        return small_radius_limit

    def _build_query(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        categories: List[str],
        *,
        timeout_seconds: float,
        out_limit: int,
    ) -> str:
        clauses = []
        for cat in categories:
            for tag_filter in _CATEGORY_OSM_TAGS.get(cat, []):
                clauses.append(f"  node{tag_filter}(around:{radius_m},{lat},{lon});")
                clauses.append(f"  way{tag_filter}(around:{radius_m},{lat},{lon});")
        body = "\n".join(clauses)
        return f"[out:json][timeout:{int(timeout_seconds)}];\n(\n{body}\n);\nout center {out_limit};"

    def _tag_to_category(self, tags: Dict) -> Optional[FacilityCategory]:
        amenity = tags.get("amenity")
        highway = tags.get("highway")
        tourism = tags.get("tourism")
        if amenity == "hospital":
            return "hospital"
        if amenity == "fuel":
            return "fuel"
        if amenity in ("restaurant", "cafe", "fast_food"):
            return "restaurant"
        if highway in ("rest_area", "services"):
            return "rest_stop"
        if amenity == "pharmacy":
            return "pharmacy"
        if tourism in ("hotel", "motel", "guest_house"):
            return "lodging"
        return None

    async def search_nearby(
        self,
        point: Coordinates,
        radius_km: float,
        categories: List[FacilityCategory],
    ) -> FacilityNearbyResult:
        if not self._settings.facilities_configured:
            raise ServiceUnavailableError(
                "Facility provider is not configured", provider="facilities"
            )

        radius_m = int(radius_km * 1000)
        timeout_seconds = self._request_timeout_seconds(radius_km)
        out_limit = self._overpass_out_limit(radius_km, len(categories))
        query = self._build_query(
            point.lat,
            point.lon,
            radius_m,
            categories,
            timeout_seconds=timeout_seconds,
            out_limit=out_limit,
        )
        client = await self._get_client()

        try:
            resp = await client.post(
                self._settings.FACILITY_PROVIDER_URL,
                data={"data": query},
                # Overrides the client's default REQUEST_TIMEOUT_SECONDS for
                # this one request only (httpx supports a per-call timeout);
                # every other provider call on this shared client keeps the
                # default.
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ServiceUnavailableError(
                f"Facility request timed out: {exc}", provider="facilities"
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                f"Facility request failed: {exc}", provider="facilities"
            ) from exc

        if resp.status_code == 429:
            raise ServiceUnavailableError(
                "Facility provider rate-limited the request",
                provider="facilities",
                reason="rate_limited",
            )
        if resp.status_code >= 500:
            raise ServiceUnavailableError(
                f"Facility provider returned server error {resp.status_code}",
                provider="facilities",
            )
        if resp.status_code >= 400:
            raise ServiceResponseError(
                f"Facility provider returned client error {resp.status_code}",
                provider="facilities",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise ServiceResponseError(
                "Facility provider returned invalid JSON", provider="facilities"
            ) from exc

        elements = data.get("elements")
        if elements is None:
            raise ServiceResponseError(
                "Facility provider response missing 'elements'", provider="facilities"
            )

        # Overpass's `out center N` is a hard cap on raw elements, not a
        # "nearest N" guarantee - if the response came back at (or past) that
        # cap, there is a real chance more matching facilities exist outside
        # what was returned, so this is treated as a truncation signal. The
        # subsequent distance-sort below only reorders what we *did* get; it
        # cannot recover facilities Overpass never sent.
        truncated = len(elements) >= out_limit

        facilities: List[Facility] = []
        seen_ids = set()
        for el in elements:
            tags = el.get("tags") or {}
            category = self._tag_to_category(tags)
            if category is None:
                continue

            # nodes have lat/lon directly; ways/relations return a "center"
            if "lat" in el and "lon" in el:
                flat, flon = el["lat"], el["lon"]
            elif "center" in el and el["center"]:
                flat, flon = el["center"].get("lat"), el["center"].get("lon")
            else:
                continue  # no usable coordinates - skip rather than guess

            if flat is None or flon is None:
                continue

            osm_id = (
                f"{el.get('type', 'node')}/{el.get('id')}"
                if el.get("id") is not None
                else None
            )
            if osm_id in seen_ids:
                continue
            seen_ids.add(osm_id)

            try:
                coords = Coordinates(lat=float(flat), lon=float(flon))
            except (TypeError, ValueError):
                continue

            facilities.append(
                Facility(
                    id=osm_id,
                    name=tags.get("name"),
                    category=category,
                    coordinates=coords,
                    distance_km=_haversine_km(point, coords),
                    address=_format_address(tags),
                    source="overpass-osm",
                    # Returned directly by Overpass/OSM for this exact node/way -
                    # the authoritative source this backend uses for facility
                    # data - so coordinate confidence is "verified". This is NOT
                    # a claim about operating hours, open/closed status, or
                    # capabilities such as EV charging or CNG.
                    verification_status="verified",
                    coordinate_source="openstreetmap-overpass",
                    last_verified_at=datetime.now(timezone.utc),
                )
            )

        facilities.sort(
            key=lambda f: f.distance_km if f.distance_km is not None else math.inf
        )
        return FacilityNearbyResult(
            facilities=facilities,
            truncated=truncated,
            limit=out_limit if truncated else None,
        )

    async def search_along_route(
        self,
        points: List[Coordinates],
        radius_km: float,
        categories: List[FacilityCategory],
    ) -> List[Facility]:
        """
        Search near up to MAX_ROUTE_SAMPLE_POINTS points along a route
        (e.g. origin, geometric midpoint, destination) and merge the
        results, deduplicated by facility id. This is a bounded
        approximation of "facilities along the route" - each sample point
        gets its own independent `radius_km` search; the space between
        samples (if they are farther apart than ~2x radius_km) is not
        covered. See MAX_ROUTE_SAMPLE_POINTS and the module docstring.
        """
        sample_points = points[:MAX_ROUTE_SAMPLE_POINTS]
        merged: Dict[str, Facility] = {}
        unidentified: List[Facility] = []
        last_error: Optional[Exception] = None
        any_succeeded = False

        for pt in sample_points:
            try:
                # search_along_route's own public return type (List[Facility])
                # is unchanged - journeys.py's /journeys/analyse doesn't yet
                # surface a truncation signal, which is out of scope for this
                # feature (see docs/API_CONTRACT.md and the final report's
                # "known limitations"); only .facilities is used here.
                results = (await self.search_nearby(pt, radius_km, categories)).facilities
                any_succeeded = True
            except (ServiceUnavailableError, ServiceResponseError) as exc:
                # One sample point failing should not discard the others -
                # log and continue; only propagate if every sample failed.
                logger.warning(
                    "Facility sample search failed for %s,%s: %s", pt.lat, pt.lon, exc
                )
                last_error = exc
                continue
            for f in results:
                if f.id:
                    existing = merged.get(f.id)
                    # Keep the closest-distance observation if seen from multiple samples.
                    if existing is None or (
                        f.distance_km is not None
                        and (
                            existing.distance_km is None
                            or f.distance_km < existing.distance_km
                        )
                    ):
                        merged[f.id] = f
                else:
                    unidentified.append(f)

        if not any_succeeded and last_error is not None:
            raise last_error

        combined = list(merged.values()) + unidentified
        combined.sort(
            key=lambda f: f.distance_km if f.distance_km is not None else math.inf
        )
        return combined


def _format_address(tags: Dict) -> Optional[str]:
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:city"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None
