"""
Tests for POST /api/v1/trip-intent/plan - the Groq-powered natural-language
trip-planning feature.

Every Groq call is mocked via respx (same technique the rest of this suite
already uses for Nominatim/OSRM/Overpass/Open-Meteo/EONET - see
tests/conftest.py's `mock_router` fixture) against Groq's real documented
endpoint, https://api.groq.com/openai/v1/chat/completions. No real API key
or network access is required or used.
"""

from __future__ import annotations

import json

import httpx
import pytest

from tests.conftest import make_settings

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

GEOCODE_JALANDHAR = [
    {"lat": "31.3260", "lon": "75.5762", "display_name": "Jalandhar, Punjab, India"}
]
GEOCODE_CHANDIGARH = [
    {"lat": "30.7333", "lon": "76.7794", "display_name": "Chandigarh, India"}
]
OSRM_OK = {
    "code": "Ok",
    "routes": [
        {
            "distance": 144000.0,
            "duration": 9000.0,
            "geometry": {
                "type": "LineString",
                "coordinates": [[75.5762, 31.3260], [76.7794, 30.7333]],
            },
        }
    ],
}
OVERPASS_OK = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": 30.73,
            "lon": 76.77,
            "tags": {"amenity": "pharmacy", "name": "Test Pharmacy"},
        },
    ]
}
OVERPASS_EMPTY = {"elements": []}
WEATHER_CLEAR = {
    "current_weather": {
        "temperature": 22.0,
        "windspeed": 10.0,
        "winddirection": 180,
        "weathercode": 0,
        "is_day": 1,
        "time": "2026-10-19T10:00",
    }
}


def _groq_response(content: str) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "openai/gpt-oss-20b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _mock_groq(mock_router, parsed: dict):
    mock_router.post(GROQ_CHAT_URL).mock(
        return_value=httpx.Response(200, json=_groq_response(json.dumps(parsed)))
    )


def _use_settings(**overrides):
    from app.core.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: make_settings(**overrides)


def _mock_happy_path_providers(mock_router):
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Jalandhar.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_JALANDHAR)
    )
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Chandigarh.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_CHANDIGARH)
    )
    mock_router.get(url__regex=r"^https://router\.test/route/v1/driving/.*$").mock(
        return_value=httpx.Response(200, json=OSRM_OK)
    )
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json=OVERPASS_OK)
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_CLEAR)
    )


# ---------------------------------------------------------------------
# 1. Valid structured output -> full journey, forwarded to existing
#    routing/facility pipeline.
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_trip_happy_path_forwards_to_existing_journey_pipeline(
    client, mock_router
):
    _use_settings(GROQ_API_KEY="test-key")
    _mock_groq(
        mock_router,
        {
            "origin": "Jalandhar, Punjab, India",
            "destination": "Chandigarh, India",
            "travel_mode": "driving",
            "priorities": ["shorter_travel_time"],
            "facilities": ["pharmacy"],
            "needs_clarification": False,
            "clarification_message": None,
        },
    )
    _mock_happy_path_providers(mock_router)

    from app.main import app

    try:
        resp = await client.post(
            "/api/v1/trip-intent/plan",
            json={
                "message": "Plan a trip from Jalandhar to Chandigarh, show pharmacies, prefer the fastest route."
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["intent"]["origin"] == "Jalandhar, Punjab, India"
    assert data["intent"]["destination"] == "Chandigarh, India"
    assert data["intent"]["facilities"] == ["pharmacy"]
    # The journey came from the real analyse_journey() pipeline, not a
    # hand-rolled copy: same shape, same computed distance/duration.
    assert data["journey"]["journey"]["distance_km"] == 144.0
    assert data["journey"]["journey"]["duration_minutes"] == 150.0
    assert len(data["journey"]["facilities"]) == 1
    assert data["journey"]["facilities"][0]["category"] == "pharmacy"
    assert "preference" in data["message"].lower()


# ---------------------------------------------------------------------
# 2. Missing origin/destination -> clarification, no journey call.
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_trip_asks_for_clarification_when_destination_missing(
    client, mock_router
):
    _use_settings(GROQ_API_KEY="test-key")
    _mock_groq(
        mock_router,
        {
            "origin": "Delhi",
            "destination": None,
            "travel_mode": "driving",
            "priorities": [],
            "facilities": [],
            "needs_clarification": True,
            "clarification_message": "Where would you like to go?",
        },
    )

    resp = await client.post(
        "/api/v1/trip-intent/plan", json={"message": "I want to leave from Delhi"}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "needs_clarification"
    assert data["journey"] is None
    assert "where" in data["message"].lower()


@pytest.mark.asyncio
async def test_plan_trip_forces_clarification_even_if_model_forgets_the_flag(
    client, mock_router
):
    """Belt-and-suspenders: even if the model sets needs_clarification=false
    but leaves destination null, the endpoint must not proceed to call the
    journey pipeline with an incomplete request."""
    _use_settings(GROQ_API_KEY="test-key")
    _mock_groq(
        mock_router,
        {
            "origin": "Delhi",
            "destination": None,
            "travel_mode": "driving",
            "priorities": [],
            "facilities": [],
            "needs_clarification": False,
            "clarification_message": None,
        },
    )

    resp = await client.post(
        "/api/v1/trip-intent/plan", json={"message": "I want to leave from Delhi"}
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "needs_clarification"


# ---------------------------------------------------------------------
# 3. Malformed model output -> graceful error, not a 500.
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_trip_handles_malformed_json_from_groq(client, mock_router):
    _use_settings(GROQ_API_KEY="test-key")
    mock_router.post(GROQ_CHAT_URL).mock(
        return_value=httpx.Response(200, json=_groq_response("not valid json at all"))
    )

    resp = await client.post(
        "/api/v1/trip-intent/plan", json={"message": "Plan a trip from Delhi to Shimla"}
    )

    assert resp.status_code == 200  # same "always 200, honest status field" convention
    data = resp.json()
    assert data["status"] == "error"
    assert data["journey"] is None


@pytest.mark.asyncio
async def test_plan_trip_handles_schema_mismatched_json_from_groq(client, mock_router):
    _use_settings(GROQ_API_KEY="test-key")
    # Valid JSON, but missing required fields / wrong types - must fail
    # Pydantic validation rather than being passed downstream.
    mock_router.post(GROQ_CHAT_URL).mock(
        return_value=httpx.Response(
            200, json=_groq_response(json.dumps({"origin": 12345}))
        )
    )

    resp = await client.post(
        "/api/v1/trip-intent/plan", json={"message": "Plan a trip from Delhi to Shimla"}
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


# ---------------------------------------------------------------------
# 4. Groq API failure / timeout -> graceful error.
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_trip_handles_groq_timeout(client, mock_router):
    _use_settings(GROQ_API_KEY="test-key")
    mock_router.post(GROQ_CHAT_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    resp = await client.post(
        "/api/v1/trip-intent/plan", json={"message": "Plan a trip from Delhi to Shimla"}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "unavailable" in data["message"].lower() or "try again" in data["message"].lower()


@pytest.mark.asyncio
async def test_plan_trip_handles_groq_invalid_api_key(client, mock_router):
    _use_settings(GROQ_API_KEY="test-key")
    mock_router.post(GROQ_CHAT_URL).mock(
        return_value=httpx.Response(401, json={"error": {"message": "invalid api key"}})
    )

    resp = await client.post(
        "/api/v1/trip-intent/plan", json={"message": "Plan a trip from Delhi to Shimla"}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "misconfigured" in data["message"].lower()


@pytest.mark.asyncio
async def test_plan_trip_handles_groq_rate_limit(client, mock_router):
    _use_settings(GROQ_API_KEY="test-key")
    mock_router.post(GROQ_CHAT_URL).mock(
        return_value=httpx.Response(429, json={"error": {"message": "rate limited"}})
    )

    resp = await client.post(
        "/api/v1/trip-intent/plan", json={"message": "Plan a trip from Delhi to Shimla"}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "busy" in data["message"].lower()


# ---------------------------------------------------------------------
# GROQ_API_KEY not configured -> "not_configured", never a crash.
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_trip_reports_not_configured_when_no_api_key(client, mock_router):
    # Default `client` fixture settings have GROQ_API_KEY unset.
    resp = await client.post(
        "/api/v1/trip-intent/plan", json={"message": "Plan a trip from Delhi to Shimla"}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "not set up" in data["message"].lower()


# ---------------------------------------------------------------------
# Empty facility/route results handled gracefully (reuses the existing
# pipeline's own honest-empty-results behaviour - nothing fabricated).
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_trip_handles_empty_facility_results(client, mock_router):
    _use_settings(GROQ_API_KEY="test-key")
    _mock_groq(
        mock_router,
        {
            "origin": "Jalandhar, Punjab, India",
            "destination": "Chandigarh, India",
            "travel_mode": "driving",
            "priorities": [],
            "facilities": ["hospital"],
            "needs_clarification": False,
            "clarification_message": None,
        },
    )
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Jalandhar.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_JALANDHAR)
    )
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Chandigarh.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_CHANDIGARH)
    )
    mock_router.get(url__regex=r"^https://router\.test/route/v1/driving/.*$").mock(
        return_value=httpx.Response(200, json=OSRM_OK)
    )
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json=OVERPASS_EMPTY)
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_CLEAR)
    )

    resp = await client.post(
        "/api/v1/trip-intent/plan",
        json={"message": "Plan a trip from Jalandhar to Chandigarh, show hospitals"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["journey"]["facilities"] == []


# ---------------------------------------------------------------------
# Fallback structured-output mode: a GROQ_MODEL outside the strict-schema
# list must use json_object mode and still validate the result manually.
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_trip_uses_json_object_fallback_for_non_strict_model(
    client, mock_router
):
    _use_settings(GROQ_API_KEY="test-key", GROQ_MODEL="llama-3.3-70b-versatile")

    captured = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=_groq_response(
                json.dumps(
                    {
                        "origin": "Delhi",
                        "destination": "Shimla",
                        "travel_mode": "driving",
                        "priorities": [],
                        "facilities": [],
                        "needs_clarification": False,
                        "clarification_message": None,
                    }
                )
            ),
        )

    mock_router.post(GROQ_CHAT_URL).mock(side_effect=_capture)
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Delhi.*$").mock(
        return_value=httpx.Response(
            200, json=[{"lat": "28.61", "lon": "77.20", "display_name": "Delhi, India"}]
        )
    )
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Shimla.*$").mock(
        return_value=httpx.Response(
            200, json=[{"lat": "31.10", "lon": "77.17", "display_name": "Shimla, India"}]
        )
    )
    mock_router.get(url__regex=r"^https://router\.test/route/v1/driving/.*$").mock(
        return_value=httpx.Response(200, json=OSRM_OK)
    )
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json=OVERPASS_EMPTY)
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_CLEAR)
    )

    resp = await client.post(
        "/api/v1/trip-intent/plan", json={"message": "Plan a trip from Delhi to Shimla"}
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert captured["body"]["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------
# Request validation: blank message is rejected the same way blank
# origin/destination already is on /journeys/analyse.
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_trip_rejects_blank_message(client):
    resp = await client.post("/api/v1/trip-intent/plan", json={"message": "   "})
    assert resp.status_code == 422
