"""FastAPI dependency providers. Keeps route handlers thin and testable."""

from __future__ import annotations

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from app.core.config import Settings, get_settings
from app.services.alerts import AlertService
from app.services.facilities import FacilityService
from app.services.groq_service import GroqService
from app.services.routing import RoutingService
from app.services.weather import WeatherService


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Returns the single shared AsyncClient created at app startup
    (see app/main.py lifespan). Reusing one client enables connection
    pooling instead of opening a new TCP/TLS connection per request."""
    return request.app.state.http_client


def get_routing_service(
    settings: Settings = Depends(get_settings),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> RoutingService:
    return RoutingService(settings=settings, client=client)


def get_facility_service(
    settings: Settings = Depends(get_settings),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> FacilityService:
    return FacilityService(settings=settings, client=client)


def get_weather_service(
    settings: Settings = Depends(get_settings),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> WeatherService:
    return WeatherService(settings=settings, client=client)


def get_alert_service(
    settings: Settings = Depends(get_settings),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> AlertService:
    return AlertService(settings=settings, client=client)


def get_groq_service(settings: Settings = Depends(get_settings)) -> GroqService:
    # GroqService manages its own Groq SDK client (separate from the shared
    # httpx client above, which talks to the routing/facilities/weather/
    # alerts providers) - see app/services/groq_service.py.
    return GroqService(settings=settings)


# Supabase JWT authentication
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate Supabase JWT, return user_id (sub claim)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not settings.SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured on this server (SUPABASE_JWT_SECRET unset).",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


__all__ = [
    "get_settings",
    "Settings",
    "get_http_client",
    "get_routing_service",
    "get_facility_service",
    "get_weather_service",
    "get_alert_service",
    "get_groq_service",
    "get_current_user",
    "security",
]
