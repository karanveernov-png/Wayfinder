from __future__ import annotations

import pytest
import respx
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.main import app


def make_settings(**overrides) -> Settings:
    base = dict(
        GEOCODING_PROVIDER_URL="https://nominatim.test",
        ROUTING_PROVIDER_URL="https://router.test",
        FACILITY_PROVIDER_URL="https://overpass.test/api/interpreter",
        WEATHER_PROVIDER_URL="https://weather.test",
        ALERT_PROVIDER_URL=None,
        ISRO_BHUVAN_TOKEN=None,
        # Tests make many rapid geocoding calls; the 1 req/sec production
        # default would make the suite impractically slow, so disable the
        # throttle here. The throttle's own logic is covered directly by
        # tests/test_routing_throttle.py using the real default.
        NOMINATIM_MIN_INTERVAL_SECONDS=0,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings():
    return make_settings()


@pytest.fixture(autouse=True)
def override_settings(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    get_settings.cache_clear()
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
async def client():
    # ASGITransport does not fire lifespan events on its own, so drive the
    # app's lifespan manually to get a real app.state.http_client, exactly
    # as it would exist when served by uvicorn.
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac


@pytest.fixture
def mock_router():
    with respx.mock(assert_all_called=False) as m:
        yield m
