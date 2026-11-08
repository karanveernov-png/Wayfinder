"""
Tests for app.api.deps.get_current_user — Supabase JWT verification.

Before this file was added, the project had zero automated coverage of
authentication: no test exercised a missing token, an invalid token, an
expired token, a wrong-audience token, a valid token, or the
SUPABASE_JWT_SECRET-unset case. Routed through a real protected endpoint
(GET /saved-journeys) rather than calling get_current_user directly, so
these tests also prove the dependency is actually wired into the route,
not just correct in isolation.
"""

from __future__ import annotations

import time

import pytest
from jose import jwt

from app.api.deps import get_settings
from app.main import app

from .conftest import make_settings

JWT_SECRET = "unit-test-jwt-secret"


def _token(*, secret=JWT_SECRET, sub="user-123", aud="authenticated", exp_delta=3600, **extra_claims):
    claims = {"sub": sub, "aud": aud, "exp": int(time.time()) + exp_delta}
    claims.update(extra_claims)
    return jwt.encode(claims, secret, algorithm="HS256")


def _use_settings(**overrides):
    """Overrides get_settings for the duration of one request. The autouse
    override_settings fixture in conftest already points get_settings at a
    Settings instance with no Supabase config; this replaces it with one
    that has SUPABASE_JWT_SECRET (and friends) set, exactly as a real
    deployment would."""
    base = dict(
        SUPABASE_URL="https://proj.test.supabase.co",
        SUPABASE_ANON_KEY="anon-test-key",
        SUPABASE_SERVICE_ROLE_KEY="service-role-test-key",
        SUPABASE_JWT_SECRET=JWT_SECRET,
    )
    base.update(overrides)
    custom = make_settings(**base)
    app.dependency_overrides[get_settings] = lambda: custom
    return custom


@pytest.mark.asyncio
async def test_no_authorization_header_is_401(client):
    _use_settings()
    resp = await client.get("/api/v1/saved-journeys")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "HTTP_ERROR"


@pytest.mark.asyncio
async def test_malformed_bearer_token_is_401(client):
    _use_settings()
    resp = await client.get(
        "/api/v1/saved-journeys", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_signed_with_wrong_secret_is_401(client):
    _use_settings()
    forged = _token(secret="attacker-controlled-secret")
    resp = await client.get(
        "/api/v1/saved-journeys", headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_is_401(client):
    _use_settings()
    expired = _token(exp_delta=-3600)
    resp = await client.get(
        "/api/v1/saved-journeys", headers={"Authorization": f"Bearer {expired}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_audience_is_401(client):
    _use_settings()
    wrong_aud = _token(aud="some-other-service")
    resp = await client.get(
        "/api/v1/saved-journeys", headers={"Authorization": f"Bearer {wrong_aud}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_jwt_secret_is_503_not_401(client, monkeypatch):
    """When Supabase auth simply isn't configured, the server must say so
    (503) rather than claim the caller's credentials were invalid (401)."""
    _use_settings(SUPABASE_JWT_SECRET=None)
    token = _token()
    resp = await client.get(
        "/api/v1/saved-journeys", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_valid_token_is_accepted_and_sub_is_used_as_user_id(client, monkeypatch):
    """A well-formed, correctly-signed, non-expired, correct-audience token
    must be accepted, and the `sub` claim must become the user id used to
    scope the database query (verified by inspecting what the mocked
    Supabase client was called with)."""
    _use_settings()
    captured = {}

    class _FakeResult:
        data = []

    class _FakeQuery:
        def eq(self, key, value):
            captured.setdefault("eq_calls", []).append((key, value))
            return self

        def order(self, *a, **kw):
            return self

        def execute(self):
            return _FakeResult()

    class _FakeTable:
        def select(self, *_a):
            return _FakeQuery()

    class _FakeClient:
        def table(self, name):
            captured["table"] = name
            return _FakeTable()

    import app.api.routes.saved_journeys as saved_journeys_module

    monkeypatch.setattr(saved_journeys_module, "create_client", lambda url, key: _FakeClient())

    token = _token(sub="user-xyz-789")
    resp = await client.get(
        "/api/v1/saved-journeys", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json() == []
    assert ("user_id", "user-xyz-789") in captured["eq_calls"]
