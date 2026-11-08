"""
POST /api/v1/trip-intent/plan

Natural-language trip planning. Groq interprets a free-text request (e.g.
"Plan a trip from Delhi to Shimla. Prefer a reasonably short and easy
route. Show hospitals and pharmacies along the way.") into the SAME
structured fields POST /journeys/analyse already accepts
(app/schemas/trip_intent.py:ParsedTripIntent). This handler then calls
analyse_journey() - the exact same function /journeys/analyse uses -
directly. No routing, geocoding, or facility-search logic is duplicated
here; Groq only ever supplies origin/destination/travel_mode/facility
categories/priorities, never route geometry, distances, or facility
records themselves.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.deps import (
    Settings,
    get_alert_service,
    get_facility_service,
    get_groq_service,
    get_routing_service,
    get_settings,
    get_weather_service,
)
from app.api.routes.journeys import analyse_journey
from app.schemas.journey import DEFAULT_FACILITY_CATEGORIES, JourneyAnalyseRequest
from app.schemas.trip_intent import (
    ParsedTripIntent,
    TripIntentPlanResponse,
    TripIntentRequest,
)
from app.services.alerts import AlertService
from app.services.exceptions import ServiceResponseError, ServiceUnavailableError
from app.services.facilities import FacilityService
from app.services.groq_service import GroqService
from app.services.routing import RoutingService
from app.services.weather import WeatherService

logger = logging.getLogger("wayfinder.routes.trip_intent")

router = APIRouter(prefix="/trip-intent", tags=["trip-intent"])


def _unavailable_message(exc: ServiceUnavailableError) -> str:
    if exc.reason == "not_configured":
        return (
            "The AI trip-planning assistant is not set up on this server "
            "(GROQ_API_KEY is not configured). Use the form below instead."
        )
    if exc.reason == "invalid_credentials":
        return (
            "The AI trip-planning assistant is misconfigured (the server's "
            "Groq API key was rejected). Please contact the site administrator."
        )
    if exc.reason == "rate_limited":
        return "The AI trip-planning assistant is temporarily busy. Please try again shortly."
    return (
        "The AI trip-planning assistant is temporarily unavailable. Please "
        "try again, or use the form below."
    )


@router.post("/plan", response_model=TripIntentPlanResponse)
async def plan_trip_from_text(
    request: TripIntentRequest,
    groq_service: GroqService = Depends(get_groq_service),
    routing: RoutingService = Depends(get_routing_service),
    facility_service: FacilityService = Depends(get_facility_service),
    weather_service: WeatherService = Depends(get_weather_service),
    alert_service: AlertService = Depends(get_alert_service),
    settings: Settings = Depends(get_settings),
) -> TripIntentPlanResponse:
    try:
        intent = await groq_service.parse_trip_request(request.message)
    except ServiceUnavailableError as exc:
        logger.warning("Groq unavailable (%s): %s", exc.reason, exc.message)
        return TripIntentPlanResponse(
            status="error",
            intent=ParsedTripIntent(),
            message=_unavailable_message(exc),
        )
    except ServiceResponseError as exc:
        logger.warning("Groq response could not be used: %s", exc.message)
        return TripIntentPlanResponse(
            status="error",
            intent=ParsedTripIntent(),
            message=(
                "The AI trip-planning assistant returned a response this "
                "server couldn't understand. Please try rephrasing, or use "
                "the form below."
            ),
        )

    if intent.needs_clarification or not intent.origin or not intent.destination:
        return TripIntentPlanResponse(
            status="needs_clarification",
            intent=intent,
            message=intent.clarification_message
            or "Could you tell me both the starting point and the destination?",
        )

    # Reuse the form's own default facility categories when the message
    # didn't ask for any specific ones - the same default
    # /journeys/analyse and the Trip Planner form already use.
    journey_request = JourneyAnalyseRequest(
        origin=intent.origin,
        destination=intent.destination,
        travel_mode=intent.travel_mode,
        include_facilities=True,
        include_alerts=True,
        facility_categories=intent.facilities or list(DEFAULT_FACILITY_CATEGORIES),
    )

    # This is the existing /journeys/analyse pipeline, called directly -
    # not re-implemented. It performs its own geocoding/routing/facility/
    # weather/alerts/risk-engine orchestration and always returns 200 with
    # an honest data_status, exactly as it does for the regular form.
    journey = await analyse_journey(
        journey_request,
        routing=routing,
        facility_service=facility_service,
        weather_service=weather_service,
        alert_service=alert_service,
        settings=settings,
    )

    note = None
    if intent.priorities:
        wanted = ", ".join(p.replace("_", " ") for p in intent.priorities)
        note = (
            f"Noted preference(s): {wanted}. This is the single route the "
            "configured routing provider returned for this request - the "
            "app only calls a route ‘shorter’ or ‘easier’ when there is "
            "another option it actually compared it against."
        )

    return TripIntentPlanResponse(status="ok", intent=intent, message=note, journey=journey)
