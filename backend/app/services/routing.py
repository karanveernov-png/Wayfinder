"""
Routing service.

Responsible for:
  - Geocoding free-text place names into coordinates (Nominatim).
  - Requesting route geometry from Bhuvan when configured, with OSRM as fallback.

Both providers are called behind this module so the rest of the
application never depends on their specific request/response shapes.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import Settings
from app.schemas.common import Coordinates
from app.services.exceptions import (
    NotFoundError,
    ServiceResponseError,
    ServiceUnavailableError,
)
from app.services.text_similarity import generate_fallback_queries, similarity_ratio

logger = logging.getLogger("wayfinder.services.routing")


class _RedactTokenQueryFilter(logging.Filter):
    """Prevent query-string Bhuvan tokens from appearing in HTTP client logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = re.sub(
            r"([?&]token=)[^&\s\"]+",
            r"\1[REDACTED]",
            message,
            flags=re.IGNORECASE,
        )
        redacted = re.sub(
            r"(/api/area/csv/)[^/\s\"]+",
            r"\1[REDACTED]",
            redacted,
            flags=re.IGNORECASE,
        )
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_RedactTokenQueryFilter())


class _AsyncThrottle:
    """Process-wide async throttle: guarantees at least `min_interval`
    seconds between the starts of successive calls that await it.

    A RoutingService instance is created fresh per-request (see
    app/api/deps.py), so the throttle state lives at module level instead -
    one shared instance enforces the limit across every request this
    process handles, which is what Nominatim's usage policy actually cares
    about (requests per second from your client, not per object)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_call: Optional[float] = None

    async def wait(self, min_interval: float) -> None:
        if min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            if self._last_call is not None:
                remaining = min_interval - (now - self._last_call)
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_call = time.monotonic()


# Shared across all RoutingService instances in this process - see
# _AsyncThrottle docstring. Geocoding only: Nominatim's public-instance
# policy is the strict one; OSRM's demo server has no documented
# per-second cap as of this writing.
_nominatim_throttle = _AsyncThrottle()


@dataclass
class GeocodeResult:
    coordinates: Coordinates
    display_name: str


@dataclass
class LocationSuggestionResult:
    """One normalized location-suggestion candidate. See
    RoutingService.suggest_locations() - converted to the API's
    LocationSuggestion schema in app/api/routes/locations.py."""

    place_id: str
    display_name: str
    name: str
    coordinates: Coordinates
    region: Optional[str] = None
    country: Optional[str] = None
    place_type: Optional[str] = None
    match_confidence: float = 0.0
    is_fallback_match: bool = False


@dataclass
class SuggestLocationsResult:
    suggestions: List[LocationSuggestionResult]
    used_fallback: bool


@dataclass
class RouteResult:
    distance_km: Optional[float]
    duration_minutes: Optional[float]
    geometry: Dict  # GeoJSON LineString
    provider: str
    fallback_reason: Optional[str] = None
    fallback_status: Optional[str] = None


class RoutingService:
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

    async def _request_bhuvan_shortest_path(
        self, origin: Coordinates, destination: Coordinates
    ) -> Dict[str, Any]:
        token = (self._settings.ISRO_BHUVAN_TOKEN or "").strip()
        if not token:
            raise ServiceUnavailableError(
                "ISRO_BHUVAN_TOKEN is not configured.",
                provider="isro_bhuvan",
                reason="not_configured",
            )
        client = await self._get_client()
        url = self._settings.ISRO_BHUVAN_SHORTEST_PATH_URL
        params = {
            "lat1": str(origin.lat),
            "lon1": str(origin.lon),
            "lat2": str(destination.lat),
            "lon2": str(destination.lon),
            "token": token,
        }

        try:
            resp = await client.get(
                url,
                params=params,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.TimeoutException as exc:
            raise ServiceUnavailableError(
                f"ISRO Bhuvan routing request timed out: {exc}", provider="isro_bhuvan"
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                f"ISRO Bhuvan routing request failed: {exc}", provider="isro_bhuvan"
            ) from exc

        if resp.status_code == 401:
            raise ServiceResponseError(
                "ISRO Bhuvan token is invalid or expired.",
                provider="isro_bhuvan",
            )
        if resp.status_code == 429:
            raise ServiceUnavailableError(
                "ISRO Bhuvan rate-limited the request", provider="isro_bhuvan",
                reason="rate_limited",
            )
        if resp.status_code >= 500:
            raise ServiceUnavailableError(
                f"ISRO Bhuvan returned server error {resp.status_code}",
                provider="isro_bhuvan",
            )
        if resp.status_code >= 400:
            response_text = resp.text[:500]
            lower_response = response_text.lower()
            if "state" in lower_response and any(
                marker in lower_response for marker in ("different", "intra", "mismatch")
            ):
                raise ServiceResponseError(
                    "Bhuvan rejected the route; its Shortest Path API may not support routes across state boundaries.",
                    provider="isro_bhuvan",
                )
            raise ServiceResponseError(
                f"ISRO Bhuvan returned client error {resp.status_code}",
                provider="isro_bhuvan",
            )

        try:
            payload = resp.json()
        except ValueError as exc:
            raise ServiceResponseError(
                "ISRO Bhuvan returned invalid JSON", provider="isro_bhuvan"
            ) from exc

        if not isinstance(payload, dict):
            raise ServiceResponseError(
                "ISRO Bhuvan response was not a GeoJSON object", provider="isro_bhuvan"
            )

        return payload

    @staticmethod
    def _bhuvan_linestring(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract a usable GeoJSON LineString from Bhuvan's GeoJSON response."""
        message = " ".join(
            str(payload.get(key, ""))
            for key in ("error", "message", "detail", "status")
        ).lower()
        if "token" in message and any(
            marker in message for marker in ("invalid", "expired", "unauthorized")
        ):
            raise ServiceResponseError(
                "ISRO Bhuvan token appears invalid or expired; renew it in backend/.env. The backup router will be used.",
                provider="isro_bhuvan",
            )
        if "state" in message and any(
            marker in message for marker in ("different", "intra", "mismatch")
        ):
            raise ServiceResponseError(
                "Bhuvan rejected this route because its Shortest Path API is intrastate-only. The backup router will be used.",
                provider="isro_bhuvan",
            )

        geometry_objects: List[Dict[str, Any]] = []
        payload_type = payload.get("type")

        if payload_type == "FeatureCollection":
            features = payload.get("features")
            if isinstance(features, list):
                for feature in features:
                    if isinstance(feature, dict) and isinstance(feature.get("geometry"), dict):
                        geometry_objects.append(feature["geometry"])
        elif payload_type == "Feature":
            geometry = payload.get("geometry")
            if isinstance(geometry, dict):
                geometry_objects.append(geometry)
        elif payload_type in ("LineString", "MultiLineString"):
            geometry_objects.append(payload)

        lines: List[List[List[float]]] = []
        for geometry in geometry_objects:
            geometry_type = geometry.get("type")
            coordinates = geometry.get("coordinates")
            if geometry_type == "LineString" and isinstance(coordinates, list):
                candidates = [coordinates]
            elif geometry_type == "MultiLineString" and isinstance(coordinates, list):
                candidates = coordinates
            else:
                continue

            for candidate in candidates:
                if not isinstance(candidate, list):
                    continue
                valid_points = []
                for point in candidate:
                    if (
                        isinstance(point, (list, tuple))
                        and len(point) >= 2
                        and isinstance(point[0], (int, float))
                        and isinstance(point[1], (int, float))
                        and math.isfinite(point[0])
                        and math.isfinite(point[1])
                    ):
                        valid_points.append([float(point[0]), float(point[1])])
                if len(valid_points) >= 2:
                    lines.append(valid_points)

        if not lines:
            raise ServiceResponseError(
                "ISRO Bhuvan response did not contain a usable GeoJSON route.",
                provider="isro_bhuvan",
            )

        coordinates = []
        for line in lines:
            if coordinates and coordinates[-1] == line[0]:
                coordinates.extend(line[1:])
            else:
                coordinates.extend(line)
        return {"type": "LineString", "coordinates": coordinates}

    async def geocode(self, place: str) -> GeocodeResult:
        if not self._settings.geocoding_configured:
            raise ServiceUnavailableError(
                "Geocoding provider is not configured", provider="geocoding"
            )

        client = await self._get_client()
        url = f"{self._settings.GEOCODING_PROVIDER_URL.rstrip('/')}/search"
        params = {"q": place, "format": "jsonv2", "limit": 1}

        await _nominatim_throttle.wait(self._settings.NOMINATIM_MIN_INTERVAL_SECONDS)
        try:
            resp = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise ServiceUnavailableError(
                f"Geocoding request timed out: {exc}", provider="geocoding"
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                f"Geocoding request failed: {exc}", provider="geocoding"
            ) from exc

        if resp.status_code == 429:
            raise ServiceUnavailableError(
                "Geocoding provider rate-limited the request",
                provider="geocoding",
                reason="rate_limited",
            )
        if resp.status_code >= 500:
            raise ServiceUnavailableError(
                f"Geocoding provider returned server error {resp.status_code}",
                provider="geocoding",
            )
        if resp.status_code >= 400:
            raise ServiceResponseError(
                f"Geocoding provider returned client error {resp.status_code}",
                provider="geocoding",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise ServiceResponseError(
                "Geocoding provider returned invalid JSON", provider="geocoding"
            ) from exc

        if not isinstance(data, list) or len(data) == 0:
            raise NotFoundError(
                f"No geocoding match found for '{place}'", provider="geocoding"
            )

        top = data[0]
        try:
            lat = float(top["lat"])
            lon = float(top["lon"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceResponseError(
                "Geocoding provider response missing valid lat/lon",
                provider="geocoding",
            ) from exc

        return GeocodeResult(
            coordinates=Coordinates(lat=lat, lon=lon),
            display_name=top.get("display_name", place),
        )

    # ------------------------------------------------------------------
    # Location suggestions / autocomplete / disambiguation
    #
    # Unlike geocode() above (which keeps only the single top Nominatim
    # result, for the existing journey-planning pipeline), this returns
    # several normalized candidates so the frontend can show the user a
    # real choice - see docs/LOCATION_AUTOCOMPLETE_GUIDE.md.
    # ------------------------------------------------------------------

    # A fuzzy-fallback result below this textual-similarity score (against
    # the user's ORIGINAL raw input, not the trimmed variant that was
    # actually searched - see text_similarity.generate_fallback_queries)
    # is considered too weak to show. This only applies to fallback
    # results; a provider match for the user's exact input is shown
    # regardless of its score, since Nominatim's own relevance ranking is
    # already a stronger signal there than ours.
    _FALLBACK_MIN_CONFIDENCE = 0.45

    # A raw query shorter than this is treated as "not enough to search
    # yet" and returns no suggestions without calling the provider at all
    # - avoids noisy single/two-letter results and an unnecessary request
    # on every keystroke before the frontend's own debounce even kicks in.
    _MIN_QUERY_LENGTH = 2

    async def _nominatim_search_raw(
        self, client: httpx.AsyncClient, query_text: str, limit: int
    ) -> List[Dict[str, Any]]:
        """One throttled call to Nominatim's /search, returning the raw
        (not yet normalized) JSON array. An empty list is a legitimate,
        successful result (zero matches) - NOT an error; only a genuine
        transport/provider failure raises here."""
        url = f"{self._settings.GEOCODING_PROVIDER_URL.rstrip('/')}/search"
        params = {
            "q": query_text,
            "format": "jsonv2",
            "addressdetails": 1,
            "dedupe": 1,
            "limit": str(max(1, min(limit, 10))),
        }

        await _nominatim_throttle.wait(self._settings.NOMINATIM_MIN_INTERVAL_SECONDS)
        try:
            resp = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise ServiceUnavailableError(
                f"Geocoding request timed out: {exc}", provider="geocoding"
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                f"Geocoding request failed: {exc}", provider="geocoding"
            ) from exc

        if resp.status_code == 429:
            raise ServiceUnavailableError(
                "Geocoding provider rate-limited the request",
                provider="geocoding",
                reason="rate_limited",
            )
        if resp.status_code >= 500:
            raise ServiceUnavailableError(
                f"Geocoding provider returned server error {resp.status_code}",
                provider="geocoding",
            )
        if resp.status_code >= 400:
            raise ServiceResponseError(
                f"Geocoding provider returned client error {resp.status_code}",
                provider="geocoding",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise ServiceResponseError(
                "Geocoding provider returned invalid JSON", provider="geocoding"
            ) from exc

        if not isinstance(data, list):
            raise ServiceResponseError(
                "Geocoding provider returned an unexpected response shape",
                provider="geocoding",
            )
        return data

    @staticmethod
    def _normalize_suggestion(
        item: Dict[str, Any], raw_query: str, *, is_fallback: bool = False
    ) -> Optional[LocationSuggestionResult]:
        """One raw Nominatim result -> LocationSuggestionResult, or None if
        the entry is unusable (missing/invalid coordinates or no name at
        all). Never fabricates a field that isn't present in the provider
        response - every bit of metadata here traces back to `item`."""
        if not isinstance(item, dict):
            return None
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        try:
            coordinates = Coordinates(lat=lat, lon=lon)
        except ValueError:
            # Pydantic's own -90..90 / -180..180 range validation caught an
            # invalid provider value - skip this one entry rather than
            # fail the whole suggestions request over it.
            return None

        display_name = (item.get("display_name") or "").strip()
        if not display_name:
            return None

        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        name = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
            or address.get("state")
            or display_name.split(",")[0].strip()
        )
        region = address.get("state") or address.get("state_district")
        country = address.get("country")
        place_type = item.get("addresstype") or item.get("type") or item.get("class")
        place_id = item.get("place_id") or item.get("osm_id") or f"{lat:.6f}:{lon:.6f}"

        confidence = max(
            similarity_ratio(raw_query, name),
            similarity_ratio(raw_query, display_name.split(",")[0]),
        )

        return LocationSuggestionResult(
            place_id=str(place_id),
            display_name=display_name,
            name=str(name).strip() or display_name,
            coordinates=coordinates,
            region=str(region).strip() if region else None,
            country=str(country).strip() if country else None,
            place_type=str(place_type) if place_type else None,
            match_confidence=round(min(confidence, 1.0), 3),
            is_fallback_match=is_fallback,
        )

    @staticmethod
    def _dedupe_suggestions(
        items: List[LocationSuggestionResult],
    ) -> List[LocationSuggestionResult]:
        """Collapses results that are effectively the same place. Keyed on
        rounded coordinates (~11m precision) rather than display_name,
        per the "do not treat a display name as a unique identifier"
        requirement - two differently-worded results for the same spot
        still collapse, while two genuinely different places that happen
        to share a name (the actual disambiguation scenario this feature
        exists for) are correctly kept as separate entries."""
        seen: set[tuple[float, float]] = set()
        deduped: List[LocationSuggestionResult] = []
        for item in items:
            key = (round(item.coordinates.lat, 4), round(item.coordinates.lon, 4))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    async def suggest_locations(
        self, query: str, limit: int = 6
    ) -> SuggestLocationsResult:
        """
        Up to `limit` real, distinct location candidates for `query`,
        normalized and deduplicated, for the frontend's autocomplete /
        disambiguation UI (see docs/LOCATION_AUTOCOMPLETE_GUIDE.md).

        If the raw query returns nothing, a small bounded set of trimmed
        variants is tried (see text_similarity.generate_fallback_queries);
        any results from that fallback are scored against the user's
        ORIGINAL input and only kept above _FALLBACK_MIN_CONFIDENCE, and
        flagged is_fallback_match=True so the caller can label them
        distinctly. This never raises NotFoundError - a genuine "nothing
        found anywhere" is a successful response with an empty
        `suggestions` list (Scenario D: never invent a location).
        """
        if not self._settings.geocoding_configured:
            raise ServiceUnavailableError(
                "Geocoding provider is not configured",
                provider="geocoding",
                reason="not_configured",
            )

        cleaned = query.strip()
        if len(cleaned) < self._MIN_QUERY_LENGTH:
            return SuggestLocationsResult(suggestions=[], used_fallback=False)

        client = await self._get_client()
        bounded_limit = max(1, min(limit, 10))

        raw = await self._nominatim_search_raw(client, cleaned, bounded_limit)
        candidates = [
            c
            for c in (self._normalize_suggestion(item, cleaned) for item in raw)
            if c is not None
        ]
        deduped = self._dedupe_suggestions(candidates)

        used_fallback = False
        if not deduped:
            for variant in generate_fallback_queries(cleaned):
                used_fallback = True
                raw_variant = await self._nominatim_search_raw(
                    client, variant, bounded_limit
                )
                variant_candidates = [
                    c
                    for c in (
                        self._normalize_suggestion(item, cleaned, is_fallback=True)
                        for item in raw_variant
                    )
                    if c is not None
                ]
                variant_candidates = [
                    c
                    for c in variant_candidates
                    if c.match_confidence >= self._FALLBACK_MIN_CONFIDENCE
                ]
                if variant_candidates:
                    variant_candidates.sort(
                        key=lambda c: c.match_confidence, reverse=True
                    )
                    deduped = self._dedupe_suggestions(variant_candidates)
                    break

        return SuggestLocationsResult(
            suggestions=deduped[:bounded_limit], used_fallback=used_fallback
        )

    async def get_route(
        self, origin: Coordinates, destination: Coordinates, mode: str
    ) -> RouteResult:
        # ISRO Bhuvan only supports driving; everything else goes straight
        # to the OSRM fallback with the matching profile.
        if mode != "driving":
            return await self._osrm_route(origin, destination, mode, fallback_reason=None, fallback_status=None)

        fallback_reason = None
        fallback_status = None
        try:
            payload = await self._request_bhuvan_shortest_path(origin, destination)
            geometry = self._bhuvan_linestring(payload)
            return RouteResult(
                distance_km=None,
                duration_minutes=None,
                geometry=geometry,
                provider="isro-bhuvan-routing",
            )
        except ServiceUnavailableError as exc:
            fallback_reason = exc.message
            fallback_status = (
                "not_configured" if exc.reason == "not_configured" else "unavailable"
            )
        except (NotFoundError, ServiceResponseError) as exc:
            fallback_reason = exc.message
            fallback_status = "error"

        logger.warning(
            "ISRO Bhuvan routing unavailable; using OSRM fallback: %s",
            fallback_reason,
        )

        return await self._osrm_route(
            origin, destination, mode, fallback_reason=fallback_reason, fallback_status=fallback_status
        )

    async def get_route_alternatives(
        self,
        origin: Coordinates,
        destination: Coordinates,
        mode: str,
        max_alternatives: int = 3,
    ) -> List[RouteResult]:
        """
        Up to `max_alternatives` distinct routes between the same two
        points, for side-by-side comparison.

        OSRM-only: ISRO Bhuvan's shortest-path API returns a single route
        with no alternatives concept, so this always goes straight to
        OSRM's `alternatives` parameter regardless of travel mode (even
        "driving", which get_route() would otherwise prefer Bhuvan for).
        Not every OSRM deployment/profile actually returns more than one
        route for a given pair of points (it depends on whether a
        meaningfully different path exists, and whether the configured
        server enables alternatives at all) - callers should handle a
        single-element result as "no alternates available", not an error.
        """
        results = await self._osrm_route(
            origin,
            destination,
            mode,
            fallback_reason=None,
            fallback_status=None,
            alternatives=True,
        )
        return results[:max_alternatives]

    async def _osrm_route(
        self,
        origin: Coordinates,
        destination: Coordinates,
        mode: str,
        fallback_reason: Optional[str],
        fallback_status: Optional[str],
        alternatives: bool = False,
    ) -> "List[RouteResult] | RouteResult":
        # Map Wayfinder travel modes to OSRM routing profiles
        profile_map = {
            "driving": "driving",
            "two-wheeler": "driving",  # OSRM doesn't have a dedicated motorcycle profile; driving is the closest
            "cycling": "cycling",
            "transit": "driving",      # OSRM doesn't have a transit profile; driving provides the most comprehensive routes
        }
        osrm_profile = profile_map.get(mode, "driving")

        if not self._settings.routing_configured:
            raise ServiceUnavailableError(
                f"OSRM backup routing is not configured. Fallback reason: {fallback_reason}",
                provider="routing",
                reason="not_configured",
            )

        client = await self._get_client()
        coords = f"{origin.lon},{origin.lat};{destination.lon},{destination.lat}"
        url = f"{self._settings.ROUTING_PROVIDER_URL.rstrip('/')}/route/v1/{osrm_profile}/{coords}"
        params = {"overview": "full", "geometries": "geojson"}
        if alternatives:
            # "true" rather than a specific count: supported across more
            # OSRM server versions than the newer integer-count form, at
            # the cost of not being able to request an exact number back -
            # get_route_alternatives() slices the result instead.
            params["alternatives"] = "true"

        try:
            resp = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise ServiceUnavailableError(
                f"OSRM routing request timed out: {exc}"
                + (
                    f" Bhuvan also failed: {fallback_reason}"
                    if fallback_reason
                    else ""
                ),
                provider="routing",
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                f"OSRM routing request failed: {exc}"
                + (
                    f" Bhuvan also failed: {fallback_reason}"
                    if fallback_reason
                    else ""
                ),
                provider="routing",
            ) from exc

        if resp.status_code == 429:
            raise ServiceUnavailableError(
                "OSRM routing provider rate-limited the request."
                + (
                    f" Bhuvan also failed: {fallback_reason}"
                    if fallback_reason
                    else ""
                ),
                provider="routing",
                reason="rate_limited",
            )
        if resp.status_code >= 500:
            raise ServiceUnavailableError(
                f"OSRM routing provider returned server error {resp.status_code}."
                + (
                    f" Bhuvan also failed: {fallback_reason}"
                    if fallback_reason
                    else ""
                ),
                provider="routing",
            )
        if resp.status_code >= 400:
            raise ServiceResponseError(
                f"OSRM routing provider returned client error {resp.status_code}."
                + (
                    f" Bhuvan also failed: {fallback_reason}"
                    if fallback_reason
                    else ""
                ),
                provider="routing",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise ServiceResponseError(
                "Routing provider returned invalid JSON", provider="routing"
            ) from exc

        if data.get("code") != "Ok":
            raise NotFoundError(
                f"OSRM could not find a route (code={data.get('code')})."
                + (
                    f" Bhuvan also failed: {fallback_reason}"
                    if fallback_reason
                    else ""
                ),
                provider="routing",
            )

        routes = data.get("routes") or []
        if not routes:
            raise NotFoundError(
                "OSRM returned no routes."
                + (
                    f" Bhuvan also failed: {fallback_reason}"
                    if fallback_reason
                    else ""
                ),
                provider="routing",
            )

        parsed: List[RouteResult] = []
        for route in routes:
            try:
                distance_km = round(float(route["distance"]) / 1000.0, 2)
                duration_minutes = round(float(route["duration"]) / 60.0, 1)
                geometry = route["geometry"]
            except (KeyError, TypeError, ValueError) as exc:
                # A malformed entry among several alternatives is skipped
                # rather than failing the whole request; a malformed single
                # (non-alternatives) response still raises, below.
                if alternatives:
                    continue
                raise ServiceResponseError(
                    "Routing provider response missing distance/duration/geometry",
                    provider="routing",
                ) from exc

            if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
                if alternatives:
                    continue
                raise ServiceResponseError(
                    "Routing provider geometry was not a GeoJSON LineString",
                    provider="routing",
                )

            parsed.append(
                RouteResult(
                    distance_km=distance_km,
                    duration_minutes=duration_minutes,
                    geometry=geometry,
                    provider="osrm-routing",
                    fallback_reason=fallback_reason,
                    fallback_status=fallback_status,
                )
            )

        if not parsed:
            raise ServiceResponseError(
                "None of OSRM's returned routes had usable distance/duration/geometry",
                provider="routing",
            )

        return parsed if alternatives else parsed[0]
