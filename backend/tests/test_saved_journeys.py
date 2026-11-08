"""
Tests for /saved-journeys CRUD, authorization scoping and cross-user access.

Before this file was added, /saved-journeys (app/api/routes/saved_journeys.py)
had zero test coverage despite being the one part of the API that touches a
real database and must enforce per-user ownership on every operation. A fake
Supabase/postgrest client is used so these tests exercise the actual
.table()/.select()/.eq()/.single()/.maybe_single()/.execute() call chains the
route handlers build, including postgrest-py's real behavior of RAISING
(not returning empty data) when .single() matches zero rows — the bug fixed
in this same change (GET /saved-journeys/{id} used .single(), which turned a
normal "not found / not yours" case into an opaque 500; switched to
.maybe_single()).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from postgrest.exceptions import APIError

import app.api.routes.saved_journeys as saved_journeys_module
from app.api.deps import get_current_user, get_settings
from app.main import app

from .conftest import make_settings


# --------------------------------------------------------------------------
# A small fake Supabase/postgrest client that behaves like the real one for
# the subset of the API saved_journeys.py uses — including the real
# .single()-raises-on-zero-rows behavior (see postgrest._sync.request_builder
# .SyncSingleRequestBuilder.execute, which raises APIError, and
# .maybe_single(), which catches exactly that and returns None).
# --------------------------------------------------------------------------


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows, op, insert_payload=None):
        self._rows = rows
        self._op = op
        self._insert_payload = insert_payload
        self._filters = []
        self._single = False
        self._maybe_single = False

    def eq(self, key, value):
        self._filters.append((key, value))
        return self

    def order(self, _key, desc=False):
        self._order_desc = desc
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def _matches(self):
        return [r for r in self._rows if all(r.get(k) == v for k, v in self._filters)]

    def execute(self):
        if self._op == "insert":
            row = dict(self._insert_payload)
            row.setdefault("id", str(uuid.uuid4()))
            now = datetime.now(timezone.utc).isoformat()
            row.setdefault("created_at", now)
            row.setdefault("updated_at", now)
            self._rows.append(row)
            return _Result([row])

        if self._op == "delete":
            matched = self._matches()
            for row in matched:
                self._rows.remove(row)
            return _Result(matched)

        # select
        matched = self._matches()
        if self._single:
            # Faithful to postgrest-py: zero (or >1) rows under .single()
            # raises APIError instead of returning empty/None data.
            if len(matched) != 1:
                raise APIError(
                    {
                        "message": "JSON object requested, multiple (or no) rows returned",
                        "code": "PGRST116",
                        "details": "The result contains 0 rows",
                        "hint": None,
                    }
                )
            return _Result(matched[0])
        if self._maybe_single:
            if len(matched) != 1:
                return None
            return _Result(matched[0])
        return _Result(matched)


class _Table:
    def __init__(self, rows):
        self._rows = rows

    def insert(self, payload):
        return _Query(self._rows, "insert", insert_payload=payload)

    def select(self, *_a):
        return _Query(self._rows, "select")

    def delete(self):
        return _Query(self._rows, "delete")


class FakeSupabaseClient:
    """In-memory stand-in for supabase.Client, shared across calls within one test."""

    def __init__(self, seed_rows=None):
        self.rows = list(seed_rows or [])

    def table(self, _name):
        return _Table(self.rows)


@pytest.fixture
def fake_db(monkeypatch):
    fake = FakeSupabaseClient()
    monkeypatch.setattr(saved_journeys_module, "create_client", lambda url, key: fake)
    return fake


@pytest.fixture(autouse=True)
def _supabase_settings():
    custom = make_settings(
        SUPABASE_URL="https://proj.test.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="service-role-test-key",
        SUPABASE_JWT_SECRET="unit-test-secret",
    )
    app.dependency_overrides[get_settings] = lambda: custom
    yield
    app.dependency_overrides.pop(get_settings, None)


def _as_user(user_id):
    app.dependency_overrides[get_current_user] = lambda: user_id


@pytest.fixture(autouse=True)
def _clear_user_override():
    yield
    app.dependency_overrides.pop(get_current_user, None)


# --------------------------------------------------------------------------
# Save / list — basic happy paths and payload integrity.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_journey_stores_authenticated_users_id_not_client_supplied(client, fake_db):
    """SaveJourneyRequest has no user_id field, so a forged owner can't even
    be expressed in the request body — but confirm the server-derived
    user_id from the token is what actually lands in the row."""
    _as_user("user-A")
    resp = await client.post(
        "/api/v1/saved-journeys",
        json={
            "origin": "Chandigarh, India",
            "destination": "Ludhiana, Punjab, India",
            "journey_json": {"ok": True},
        },
    )
    assert resp.status_code == 201
    assert fake_db.rows[0]["user_id"] == "user-A"
    assert resp.json()["origin"] == "Chandigarh, India"


@pytest.mark.asyncio
async def test_list_journeys_only_returns_own_rows(client, fake_db):
    fake_db.rows.extend([
        {"id": "j1", "user_id": "user-A", "origin": "A", "destination": "X",
         "distance_km": None, "duration_minutes": None, "risk_level": None,
         "data_status_mode": None, "created_at": "2026-01-01T00:00:00Z"},
        {"id": "j2", "user_id": "user-B", "origin": "B", "destination": "Y",
         "distance_km": None, "duration_minutes": None, "risk_level": None,
         "data_status_mode": None, "created_at": "2026-01-01T00:00:00Z"},
    ])
    _as_user("user-A")
    resp = await client.get("/api/v1/saved-journeys")
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()]
    assert ids == ["j1"]


# --------------------------------------------------------------------------
# Cross-user access — the core authorization boundary.
# --------------------------------------------------------------------------


def _seed_user_b_journey(fake_db):
    fake_db.rows.append({
        "id": "secret-journey",
        "user_id": "user-B",
        "origin": "Home",
        "destination": "Work",
        "distance_km": 12.0,
        "duration_minutes": 20.0,
        "risk_level": "low",
        "data_status_mode": "live",
        "journey_json": {"private": "user-B's data"},
        "params_json": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })


@pytest.mark.asyncio
async def test_get_other_users_journey_is_404_not_leaked(client, fake_db):
    """This is also the regression test for the .single()->.maybe_single()
    fix: before the fix, this exact scenario (0 rows match once the
    user_id filter is applied) raised postgrest.exceptions.APIError, which
    the global handler turned into a generic 500 — not the intended 404."""
    _seed_user_b_journey(fake_db)
    _as_user("user-A")
    resp = await client.get("/api/v1/saved-journeys/secret-journey")
    assert resp.status_code == 404
    assert "user-B's data" not in resp.text


@pytest.mark.asyncio
async def test_get_nonexistent_journey_is_404(client, fake_db):
    _as_user("user-A")
    resp = await client.get("/api/v1/saved-journeys/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_own_journey_succeeds(client, fake_db):
    _seed_user_b_journey(fake_db)
    _as_user("user-B")
    resp = await client.get("/api/v1/saved-journeys/secret-journey")
    assert resp.status_code == 200
    assert resp.json()["journey_json"] == {"private": "user-B's data"}


@pytest.mark.asyncio
async def test_delete_other_users_journey_is_a_noop(client, fake_db):
    _seed_user_b_journey(fake_db)
    _as_user("user-A")
    resp = await client.delete("/api/v1/saved-journeys/secret-journey")
    assert resp.status_code == 204
    # Still present — user-A's delete must not have removed user-B's row.
    assert any(r["id"] == "secret-journey" for r in fake_db.rows)


@pytest.mark.asyncio
async def test_delete_own_journey_removes_it(client, fake_db):
    _seed_user_b_journey(fake_db)
    _as_user("user-B")
    resp = await client.delete("/api/v1/saved-journeys/secret-journey")
    assert resp.status_code == 204
    assert not any(r["id"] == "secret-journey" for r in fake_db.rows)


@pytest.mark.asyncio
async def test_all_saved_journey_routes_require_authentication(client, fake_db):
    _seed_user_b_journey(fake_db)
    for method, path in [
        ("GET", "/api/v1/saved-journeys"),
        ("GET", "/api/v1/saved-journeys/secret-journey"),
        ("POST", "/api/v1/saved-journeys"),
        ("DELETE", "/api/v1/saved-journeys/secret-journey"),
    ]:
        resp = await client.request(method, path, json={} if method == "POST" else None)
        assert resp.status_code == 401, f"{method} {path} should require auth"
