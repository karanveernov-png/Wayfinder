"""Weather service: normalizes Open-Meteo's current-weather response."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import Settings
from app.schemas.common import Coordinates
from app.schemas.weather import WeatherObservation
from app.services.exceptions import ServiceResponseError, ServiceUnavailableError

logger = logging.getLogger("wayfinder.services.weather")

# Open-Meteo weather codes that indicate meaningfully adverse conditions
# for driving. Full table: https://open-meteo.com/en/docs (WMO codes).
ADVERSE_WEATHER_CODES = {
    45,
    48,  # fog
    51,
    53,
    55,
    56,
    57,  # drizzle / freezing drizzle
    61,
    63,
    65,
    66,
    67,  # rain / freezing rain
    71,
    73,
    75,
    77,  # snow
    80,
    81,
    82,  # rain showers
    85,
    86,  # snow showers
    95,
    96,
    99,  # thunderstorm
}


class WeatherService:
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

    async def get_current_weather(self, point: Coordinates) -> WeatherObservation:
        if not self._settings.weather_configured:
            raise ServiceUnavailableError(
                "Weather provider is not configured", provider="weather"
            )

        client = await self._get_client()
        url = f"{self._settings.WEATHER_PROVIDER_URL.rstrip('/')}/v1/forecast"
        params = {
            "latitude": point.lat,
            "longitude": point.lon,
            "current_weather": "true",
        }

        try:
            resp = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise ServiceUnavailableError(
                f"Weather request timed out: {exc}", provider="weather"
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                f"Weather request failed: {exc}", provider="weather"
            ) from exc

        if resp.status_code == 429:
            raise ServiceUnavailableError(
                "Weather provider rate-limited the request",
                provider="weather",
                reason="rate_limited",
            )
        if resp.status_code >= 500:
            raise ServiceUnavailableError(
                f"Weather provider returned server error {resp.status_code}",
                provider="weather",
            )
        if resp.status_code >= 400:
            raise ServiceResponseError(
                f"Weather provider returned client error {resp.status_code}",
                provider="weather",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise ServiceResponseError(
                "Weather provider returned invalid JSON", provider="weather"
            ) from exc

        current = data.get("current_weather")
        if not current:
            raise ServiceResponseError(
                "Weather provider response missing 'current_weather'",
                provider="weather",
            )

        obs_time = None
        raw_time = current.get("time")
        if raw_time:
            try:
                obs_time = datetime.fromisoformat(raw_time).replace(tzinfo=timezone.utc)
            except ValueError:
                obs_time = None

        return WeatherObservation(
            location=point,
            observation_time=obs_time,
            temperature_c=current.get("temperature"),
            windspeed_kmh=current.get("windspeed"),
            winddirection_deg=current.get("winddirection"),
            weather_code=current.get("weathercode"),
            is_day=bool(current["is_day"]) if "is_day" in current else None,
            source="open-meteo",
        )
