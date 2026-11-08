"""
POST /api/v1/journeys/analyse

Orchestrates geocoding, routing, facilities, weather, and alerts, then
runs the deterministic risk engine over the normalized results.

Design decision (documented in docs/API_CONTRACT.md): this endpoint
always returns HTTP 200 with the full documented schema, using null
fields and an explicit `data_status` to represent partial or failed
upstream data - rather than returning a 5xx for the whole request when
only part of the pipeline fails. A 4xx is still returned for invalid
client input (bad coordinates, unsupported travel_mode, etc. - handled
by Pydantic validation before this handler runs).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    Settings,
    get_alert_service,
    get_facility_service,
    get_routing_service,
    get_settings,
    get_weather_service,
)
from app.engine import risk_engine
from app.schemas.alert import Alert
from app.schemas.common import Coordinates, DataStatus, SourceMeta
from app.schemas.facility import Facility
from app.schemas.journey import (
    JourneyAnalyseRequest,
    JourneyAnalyseResponse,
    JourneyPayload,
    Location,
    RouteComparisonRequest,
    RouteComparisonResponse,
    RouteOption,
)
from app.schemas.weather import WeatherObservation
from app.services.alerts import AlertService
from app.services.demo import get_demo_alerts, get_demo_facilities, get_demo_journey
from app.services.exceptions import (
    NotFoundError,
    ServiceResponseError,
    ServiceUnavailableError,
)
from app.services.facilities import MAX_ROUTE_SAMPLE_POINTS, FacilityService
from app.services.routing import RouteResult, RoutingService
from app.services.weather import WeatherService

router = APIRouter(tags=["journeys"])

# Capped at the same value used for facility route-sampling (see
# app/services/facilities.py MAX_ROUTE_SAMPLE_POINTS) so a journey analysis
# makes at most this many Overpass requests AND this many Open-Meteo
# requests - bounded, predictable load regardless of route length.
_MAX_WEATHER_SAMPLE_POINTS = MAX_ROUTE_SAMPLE_POINTS


def _route_sample_points(
    origin: Coordinates,
    destination: Coordinates,
    geometry: Optional[dict],
    max_points: int = MAX_ROUTE_SAMPLE_POINTS,
) -> List[Coordinates]:
    """
    Up to `max_points` points to sample facilities/weather near, along the
    route. Always includes origin and destination; a third "midpoint"
    sample is added when there's room for it.

    Limitation (documented, not hidden): the midpoint is the middle VERTEX
    of the route polyline when geometry is available - a simple
    approximation, not a distance-interpolated true midpoint - or the
    straight-line average of origin/destination when no geometry exists.
    For a long or winding route this is not a substitute for continuous
    coverage; see docs/API_CONTRACT.md "Route-aware facilities/weather".
    """
    points = [origin, destination]
    if max_points >= 3:
        mid: Optional[Coordinates] = None
        if isinstance(geometry, dict) and geometry.get("type") == "LineString":
            coords = geometry.get("coordinates") or []
            if len(coords) >= 3:
                mid_lon, mid_lat = coords[len(coords) // 2]
                mid = Coordinates(lat=mid_lat, lon=mid_lon)
        if mid is None:
            mid = Coordinates(
                lat=(origin.lat + destination.lat) / 2,
                lon=(origin.lon + destination.lon) / 2,
            )
        points.insert(1, mid)
    return points[:max_points]


def _build_demo_response() -> JourneyAnalyseResponse:
    """
    Assemble a deterministic demonstration response from pre-stored data.

    No live provider calls are made.  The real risk engine still runs so
    the risk-assessment output reflects genuine rule-based logic applied to
    the demo alert data; it is not a hard-coded value.
    """
    journey = get_demo_journey()
    facilities = get_demo_facilities()
    alerts = get_demo_alerts()

    assessment = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather=None,
            weather_status="unavailable",
            alerts=alerts,
            alerts_status="ok",
            route_endpoints=[journey.origin_coords, journey.destination_coords],
            route_geometry=journey.geometry,
        )
    )
    recommendations = risk_engine.recommendations_for(
        assessment,
        facilities_available=len(facilities) > 0,
        alerts_status="ok",
        weather_status="unavailable",
    )

    return JourneyAnalyseResponse(
        journey=JourneyPayload(
            origin=Location(
                query=journey.origin_query,
                resolved=journey.origin_coords,
                display_name=journey.origin_display,
            ),
            destination=Location(
                query=journey.destination_query,
                resolved=journey.destination_coords,
                display_name=journey.destination_display,
            ),
            distance_km=journey.distance_km,
            duration_minutes=journey.duration_minutes,
            geometry=journey.geometry,
        ),
        facilities=facilities,
        alerts=alerts,
        risk_assessment=assessment,
        recommendations=recommendations,
        data_status=DataStatus(
            mode="demo",
            sources=[
                SourceMeta(
                    name="demo-journey",
                    status="ok",
                    detail=(
                        f"Stored demonstration route for Chandigarh → Ludhiana (NH-95). "
                        f"Distance {journey.distance_km} km / {journey.duration_minutes} min "
                        f"are representative, hand-approximated values - NOT a live routing "
                        f"response (provider_validated: false in demo_journey.json). "
                        f"See scripts/capture_demo_route.py."
                    ),
                ),
                SourceMeta(
                    name="demo-facilities",
                    status="ok",
                    detail=(
                        "18 CANDIDATE POIs from the Chandigarh–Ludhiana highway "
                        "directory (fuel, hospitals, restaurants, rest stops). "
                        "Coordinates are address-derived approximations, not "
                        "independently verified - see each facility's "
                        "verification_status (all 'unverified_coordinates')."
                    ),
                ),
                SourceMeta(
                    name="demo-alerts",
                    status="ok",
                    detail=(
                        "2 demonstration alerts (fictional, clearly labelled). "
                        "Not live traffic data."
                    ),
                ),
                SourceMeta(
                    name="open-meteo",
                    status="unavailable",
                    detail=(
                        "Weather is not included in demo mode. "
                        "Check a live weather source before departing."
                    ),
                ),
            ],
        ),
    )


async def _resolve_location(
    query: str,
    routing: RoutingService,
    coordinates: Optional[Coordinates] = None,
) -> Tuple[Location, SourceMeta]:
    if coordinates is not None:
        # `query` is always a meaningful label already by the time
        # coordinates are supplied - a raw map click sends its own
        # "Map point (lat, lon)" text (see frontend TripPlannerPage.jsx
        # formatMapPoint), and a location-suggestion selection sends the
        # real place name (see LocationAutocomplete.jsx /
        # locationSuggestions.js formatSuggestionLabel). Using it directly
        # here - instead of re-synthesizing a generic "Map point (...)"
        # label - means a selected suggestion's actual name (e.g.
        # "Chandigarh, Chandigarh, India") is preserved through to the
        # journey summary instead of being silently replaced with raw
        # coordinates. Pre-existing bug, not introduced by this change:
        # every map-click caller already sent that exact text as `query`,
        # so this is a no-op for that path and a fix for the new one.
        return (
            Location(
                query=query,
                resolved=coordinates,
                display_name=query,
            ),
            SourceMeta(
                name="map-selection",
                status="ok",
                retrieved_at=datetime.now(timezone.utc),
            ),
        )

    try:
        result = await routing.geocode(query)
        return (
            Location(
                query=query,
                resolved=result.coordinates,
                display_name=result.display_name,
            ),
            SourceMeta(
                name="nominatim-geocoding",
                status="ok",
                retrieved_at=datetime.now(timezone.utc),
            ),
        )
    except NotFoundError as exc:
        return (
            Location(query=query, resolved=None, display_name=None),
            SourceMeta(name="nominatim-geocoding", status="error", detail=exc.message),
        )
    except ServiceUnavailableError as exc:
        return (
            Location(query=query, resolved=None, display_name=None),
            SourceMeta(
                name="nominatim-geocoding", status="unavailable", detail=exc.message
            ),
        )
    except ServiceResponseError as exc:
        return (
            Location(query=query, resolved=None, display_name=None),
            SourceMeta(name="nominatim-geocoding", status="error", detail=exc.message),
        )


@router.post("/journeys/analyse", response_model=JourneyAnalyseResponse)
async def analyse_journey(
    request: JourneyAnalyseRequest,
    routing: RoutingService = Depends(get_routing_service),
    facility_service: FacilityService = Depends(get_facility_service),
    weather_service: WeatherService = Depends(get_weather_service),
    alert_service: AlertService = Depends(get_alert_service),
    settings: Settings = Depends(get_settings),
) -> JourneyAnalyseResponse:
    # --- Demo mode: skip all live provider calls ---
    if request.demo:
        return _build_demo_response()

    # facility_radius_km has no hardcoded bound in the Pydantic schema (see
    # JourneyAnalyseRequest) - validated here against the same live
    # MIN/MAX_FACILITY_RADIUS_KM settings /facilities/nearby uses, so the
    # two endpoints can never silently diverge on the supported range
    # again. Only checked when a facility search was actually requested,
    # matching /facilities/nearby's contract (this field is otherwise
    # unused).
    if request.include_facilities:
        if request.facility_radius_km > settings.MAX_FACILITY_RADIUS_KM:
            raise HTTPException(
                status_code=422,
                detail=f"facility_radius_km must not exceed {settings.MAX_FACILITY_RADIUS_KM} km",
            )
        if request.facility_radius_km < settings.MIN_FACILITY_RADIUS_KM:
            raise HTTPException(
                status_code=422,
                detail=f"facility_radius_km must be at least {settings.MIN_FACILITY_RADIUS_KM} km",
            )

    sources: List[SourceMeta] = []

    # --- Geocoding ---
    origin_loc, origin_src = await _resolve_location(
        request.origin, routing, request.origin_coordinates
    )
    dest_loc, dest_src = await _resolve_location(
        request.destination, routing, request.destination_coordinates
    )
    sources.extend([origin_src, dest_src])

    # --- Routing ---
    route_distance_km: Optional[float] = None
    route_duration_minutes: Optional[float] = None
    route_geometry = None
    route_available = False

    if origin_loc.resolved and dest_loc.resolved:
        try:
            route = await routing.get_route(
                origin_loc.resolved, dest_loc.resolved, request.travel_mode
            )
            route_distance_km = route.distance_km
            route_duration_minutes = route.duration_minutes
            route_geometry = route.geometry
            route_available = True
            if route.fallback_reason:
                sources.append(
                    SourceMeta(
                        name="isro-bhuvan-routing",
                        status=route.fallback_status or "error",
                        detail=route.fallback_reason,
                    )
                )
            sources.append(
                    SourceMeta(
                        name=route.provider,
                        status="ok",
                        detail=(
                            f"Backup routing used after Bhuvan failure: {route.fallback_reason}"
                            if route.fallback_reason
                            else (
                                "Bhuvan supplied route geometry; distance and duration are unavailable."
                                if route.provider == "isro-bhuvan-routing"
                                else (
                                    (
                                        "Transit requested; OSRM has no transit profile, so this is a road-route approximation, not a train itinerary."
                                        if request.travel_mode == "transit"
                                        else (
                                            "Two-wheeler requested via OSRM's driving profile; motorcycle-specific restrictions are not modeled."
                                            if request.travel_mode == "two-wheeler"
                                            else (
                                                "Cycling requested via the OSRM cycling profile; the configured OSRM server must support that profile."
                                                if request.travel_mode == "cycling"
                                                else None
                                            )
                                        )
                                    )
                                    if request.travel_mode != "driving" and route.provider == "osrm-routing"
                                    else None
                                )
                            )
                        ),
                        retrieved_at=datetime.now(timezone.utc),
                    )
                )
        except NotFoundError as exc:
            sources.append(
                SourceMeta(name="osrm-routing", status="error", detail=exc.message)
            )
        except ServiceUnavailableError as exc:
            sources.append(
                SourceMeta(
                    name="osrm-routing", status="unavailable", detail=exc.message
                )
            )
        except ServiceResponseError as exc:
            sources.append(
                SourceMeta(name="osrm-routing", status="error", detail=exc.message)
            )
    else:
        sources.append(
            SourceMeta(
                name="osrm-routing",
                status="error",
                detail="Route not requested: one or both locations could not be geocoded.",
            )
        )

    route_endpoints = [
        c for c in (origin_loc.resolved, dest_loc.resolved) if c is not None
    ]
    sample_points = (
        _route_sample_points(origin_loc.resolved, dest_loc.resolved, route_geometry)
        if origin_loc.resolved and dest_loc.resolved
        else route_endpoints
    )

    # --- Facilities (sampled along the route: up to MAX_ROUTE_SAMPLE_POINTS
    # points - origin/midpoint/destination - each independently searched and
    # merged/deduplicated; see FacilityService.search_along_route) ---
    facilities: List[Facility] = []
    if request.include_facilities and sample_points:
        try:
            facilities = await facility_service.search_along_route(
                sample_points,
                request.facility_radius_km,
                request.facility_categories,
            )
            sources.append(
                SourceMeta(
                    name="overpass-osm",
                    status="ok",
                    retrieved_at=datetime.now(timezone.utc),
                )
            )
        except ServiceUnavailableError as exc:
            sources.append(
                SourceMeta(
                    name="overpass-osm", status="unavailable", detail=exc.message
                )
            )
        except ServiceResponseError as exc:
            sources.append(
                SourceMeta(name="overpass-osm", status="error", detail=exc.message)
            )
    elif request.include_facilities:
        sources.append(
            SourceMeta(
                name="overpass-osm",
                status="error",
                detail="Skipped: origin/destination could not be geocoded.",
            )
        )

    # --- Weather (sampled at up to _MAX_WEATHER_SAMPLE_POINTS points along
    # the route). This is a limited sample, NOT a continuous forecast of
    # every route segment - see weather_samples field docs. The risk engine
    # below uses only the destination sample, to keep its scoring logic
    # focused on "what you're arriving into" rather than averaging samples
    # of different real-world severity together. ---
    weather_samples: List[WeatherObservation] = []
    weather_status = "unavailable"
    weather_for_risk: Optional[WeatherObservation] = None
    if sample_points:
        any_ok = False
        last_error_status = "unavailable"
        last_error_detail = "All weather samples failed."
        for pt in sample_points[:_MAX_WEATHER_SAMPLE_POINTS]:
            try:
                obs = await weather_service.get_current_weather(pt)
                weather_samples.append(obs)
                any_ok = True
                if dest_loc.resolved and pt == dest_loc.resolved:
                    weather_for_risk = obs
            except ServiceUnavailableError as exc:
                last_error_status = "unavailable"
                last_error_detail = exc.message
            except ServiceResponseError as exc:
                last_error_status = "error"
                last_error_detail = exc.message
        if any_ok:
            weather_status = "ok"
            if weather_for_risk is None and weather_samples:
                # Destination sample specifically failed but others
                # succeeded; fall back to the last successful sample rather
                # than silently leaving the risk engine with nothing.
                weather_for_risk = weather_samples[-1]
            sources.append(
                SourceMeta(
                    name="open-meteo",
                    status="ok",
                    retrieved_at=datetime.now(timezone.utc),
                )
            )
        else:
            weather_status = last_error_status
            sources.append(
                SourceMeta(
                    name="open-meteo",
                    status=last_error_status,
                    detail=last_error_detail,
                )
            )
    else:
        sources.append(
            SourceMeta(
                name="open-meteo",
                status="error",
                detail="Skipped: origin/destination could not be geocoded.",
            )
        )

    # --- Alerts (checked at every sampled route point - origin, midpoint,
    # destination - not just the origin, via a single combined-bbox
    # request; see AlertService.get_alerts_for_route) ---
    alerts: List[Alert] = []
    alerts_status = "unavailable"
    if request.include_alerts and sample_points:
        try:
            alerts = await alert_service.get_alerts_for_route(sample_points)
            alerts_status = "ok"
            sources.append(SourceMeta(name="alerts", status="ok"))
        except ServiceUnavailableError as exc:
            status = (
                "not_configured" if exc.reason == "not_configured" else "unavailable"
            )
            sources.append(SourceMeta(name="alerts", status=status, detail=exc.message))
        except ServiceResponseError as exc:
            sources.append(SourceMeta(name="alerts", status="error", detail=exc.message))
    elif request.include_alerts:
        # sample_points is empty only when neither endpoint could be
        # geocoded (same condition the facilities/weather sections above
        # check), so this mirrors their "skipped" messaging.
        sources.append(
            SourceMeta(
                name="alerts",
                status="error",
                detail="Skipped: no resolved coordinates available.",
            )
        )

    # --- Risk engine (uses the destination weather sample specifically -
    # see the weather section's comment above) ---
    assessment = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=route_available,
            weather=weather_for_risk,
            weather_status=weather_status
            if weather_for_risk is not None
            else "unavailable",
            alerts=alerts,
            alerts_status=alerts_status,
            route_endpoints=route_endpoints,
            route_geometry=route_geometry,
        )
    )
    recommendations = risk_engine.recommendations_for(
        assessment,
        facilities_available=len(facilities) > 0,
        alerts_status=alerts_status,
        weather_status=weather_status,
    )

    # --- Overall data_status.mode ---
    critical_ok = route_available
    any_failure = any(s.status != "ok" for s in sources)
    if critical_ok and not any_failure:
        mode = "live"
    elif critical_ok and any_failure:
        mode = "partial"
    else:
        mode = "degraded"

    return JourneyAnalyseResponse(
        journey=JourneyPayload(
            origin=origin_loc,
            destination=dest_loc,
            distance_km=route_distance_km,
            duration_minutes=route_duration_minutes,
            geometry=route_geometry,
        ),
        facilities=facilities,
        alerts=alerts,
        weather_samples=weather_samples,
        risk_assessment=assessment,
        recommendations=recommendations,
        data_status=DataStatus(mode=mode, sources=sources),
    )


async def _assess_route_option(
    route: RouteResult,
    label: str,
    origin: Coordinates,
    destination: Coordinates,
    weather_service: WeatherService,
    alert_service: AlertService,
) -> RouteOption:
    """
    A lighter-weight version of the weather/alerts/risk section of
    analyse_journey() above, run per-alternate for route comparison:
    2 sample points (not up to MAX_ROUTE_SAMPLE_POINTS) and no facility
    search, since comparison is about route-level risk/weather, not a
    facility dashboard - see RouteComparisonRequest's docstring. Several
    of these run concurrently via asyncio.gather in compare_routes(),
    below, so N alternatives costs roughly one round-trip, not N.
    """
    sample_points = _route_sample_points(origin, destination, route.geometry, max_points=2)

    weather_obs: Optional[WeatherObservation] = None
    weather_status = "unavailable"
    try:
        weather_obs = await weather_service.get_current_weather(sample_points[-1])
        weather_status = "ok"
    except (ServiceUnavailableError, ServiceResponseError):
        pass  # risk engine below treats a missing sample as "unavailable", same as the main pipeline

    alerts: List[Alert] = []
    alerts_status = "unavailable"
    try:
        alerts = await alert_service.get_alerts_for_route(sample_points)
        alerts_status = "ok"
    except ServiceUnavailableError as exc:
        alerts_status = "not_configured" if exc.reason == "not_configured" else "unavailable"
    except ServiceResponseError:
        alerts_status = "error"

    assessment = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather=weather_obs,
            weather_status=weather_status,
            alerts=alerts,
            alerts_status=alerts_status,
            route_endpoints=[origin, destination],
            route_geometry=route.geometry,
        )
    )

    return RouteOption(
        label=label,
        distance_km=route.distance_km,
        duration_minutes=route.duration_minutes,
        geometry=route.geometry,
        risk_assessment=assessment,
        weather=weather_obs,
        alerts_count=len(alerts),
    )


@router.post("/journeys/compare-routes", response_model=RouteComparisonResponse)
async def compare_routes(
    request: RouteComparisonRequest,
    routing: RoutingService = Depends(get_routing_service),
    weather_service: WeatherService = Depends(get_weather_service),
    alert_service: AlertService = Depends(get_alert_service),
) -> RouteComparisonResponse:
    origin_loc, origin_src = await _resolve_location(
        request.origin, routing, request.origin_coordinates
    )
    dest_loc, dest_src = await _resolve_location(
        request.destination, routing, request.destination_coordinates
    )

    if not origin_loc.resolved or not dest_loc.resolved:
        return RouteComparisonResponse(
            origin=origin_loc,
            destination=dest_loc,
            routes=[],
            data_status=DataStatus(mode="degraded", sources=[origin_src, dest_src]),
        )

    try:
        route_results = await routing.get_route_alternatives(
            origin_loc.resolved,
            dest_loc.resolved,
            request.travel_mode,
            max_alternatives=request.max_alternatives,
        )
    except (NotFoundError, ServiceUnavailableError, ServiceResponseError) as exc:
        return RouteComparisonResponse(
            origin=origin_loc,
            destination=dest_loc,
            routes=[],
            data_status=DataStatus(
                mode="degraded",
                sources=[origin_src, dest_src, SourceMeta(name="osrm-routing", status="error", detail=exc.message)],
            ),
        )

    labels = [
        "Fastest route" if i == 0 else f"Alternate route {i}"
        for i in range(len(route_results))
    ]

    options = list(
        await asyncio.gather(
            *[
                _assess_route_option(
                    route, label, origin_loc.resolved, dest_loc.resolved, weather_service, alert_service
                )
                for route, label in zip(route_results, labels)
            ]
        )
    )

    if options:
        fastest = min(options, key=lambda o: o.duration_minutes if o.duration_minutes is not None else float("inf"))
        fastest.is_fastest = True
        shortest = min(options, key=lambda o: o.distance_km if o.distance_km is not None else float("inf"))
        shortest.is_shortest_distance = True

    return RouteComparisonResponse(
        origin=origin_loc,
        destination=dest_loc,
        routes=options,
        data_status=DataStatus(
            mode="live" if len(options) > 1 else "partial" if options else "degraded",
            sources=[origin_src, dest_src, SourceMeta(name="osrm-routing", status="ok")],
        ),
    )
