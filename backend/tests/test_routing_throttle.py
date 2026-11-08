from __future__ import annotations

import time

import httpx
import pytest

from app.core.config import Settings
from app.services.routing import RoutingService, _AsyncThrottle


@pytest.mark.asyncio
async def test_throttle_enforces_minimum_interval_between_calls():
    throttle = _AsyncThrottle()  # dedicated instance - not the shared module-level one
    start = time.monotonic()
    await throttle.wait(0.15)
    await throttle.wait(0.15)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15


@pytest.mark.asyncio
async def test_throttle_is_a_noop_when_interval_is_zero():
    throttle = _AsyncThrottle()
    start = time.monotonic()
    await throttle.wait(0)
    await throttle.wait(0)
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


@pytest.mark.asyncio
async def test_geocode_respects_configured_throttle(mock_router):
    settings = Settings(
        GEOCODING_PROVIDER_URL="https://nominatim-throttle.test",
        NOMINATIM_MIN_INTERVAL_SECONDS=0.2,
    )
    mock_router.get(url__regex=r"^https://nominatim-throttle\.test/search.*$").mock(
        return_value=httpx.Response(
            200, json=[{"lat": "30.73", "lon": "76.78", "display_name": "Test Place"}]
        )
    )
    async with httpx.AsyncClient() as http_client:
        service = RoutingService(settings=settings, client=http_client)
        start = time.monotonic()
        await service.geocode("Place A")
        await service.geocode("Place B")
        elapsed = time.monotonic() - start
    assert elapsed >= 0.2


def test_default_user_agent_is_an_unmistakable_placeholder_not_a_fake_contact():
    # _env_file=None: check the CODED default specifically, not whatever a
    # developer's own backend/.env currently has HTTP_USER_AGENT set to.
    # Settings() alone would read the ambient .env file in the cwd - so
    # this test would fail (for the right engineering reason, but on the
    # wrong assertion) for any developer who already followed this
    # project's own README instructions and replaced the placeholder with
    # their real contact info before running the app locally.
    settings = Settings(_env_file=None)
    assert (
        "CHANGE.ME" in settings.HTTP_USER_AGENT
        or "PLACEHOLDER" in settings.HTTP_USER_AGENT
    )
    # Must NOT look like a real, usable address someone might mistake for contactable.
    assert "dev@example.com" not in settings.HTTP_USER_AGENT


def test_user_agent_is_configurable_via_settings():
    settings = Settings(HTTP_USER_AGENT="my-real-app/1.0 (contact: ops@myteam.example)")
    assert settings.HTTP_USER_AGENT == "my-real-app/1.0 (contact: ops@myteam.example)"
