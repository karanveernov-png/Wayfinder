from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_validation_error_uses_unified_envelope(client, mock_router):
    resp = await client.post("/api/v1/journeys/analyse", json={"origin": "A"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "message" in body["error"]
    assert isinstance(body["error"]["details"], list)
    assert body["error"]["details"][0]["loc"]


@pytest.mark.asyncio
async def test_manually_raised_http_exception_uses_same_envelope(client, mock_router):
    """app/api/routes/facilities.py raises a plain HTTPException for an
    oversized radius - this must come back in the same {"error": {...}}
    shape as every other error, not FastAPI's bare {"detail": "..."}."""
    resp = await client.get(
        "/api/v1/facilities/nearby",
        params={"lat": 30.73, "lon": 76.77, "radius_km": 500},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "radius_km" in body["error"]["message"]
    assert "detail" not in body  # old bare FastAPI shape must not leak through


@pytest.mark.asyncio
async def test_404_uses_unified_envelope(client, mock_router):
    resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
