"""
Route-corridor alert proximity tests.

Previous behavior only checked distance to the route's two ENDPOINTS,
which could miss a genuinely mid-route alert on a long journey (a false
negative) or, for a very short/direct route, treat a distant alert as
relevant just because it happened to be near a straight line between two
points (a false positive, though less likely in practice). These tests
exercise the fixed behavior: distance to the actual route LineString.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.engine import risk_engine
from app.schemas.alert import Alert
from app.schemas.common import Coordinates

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)

# A simple straight-ish route: Chandigarh (30.74, 76.78) -> Ludhiana (30.90, 75.86)
ORIGIN = Coordinates(lat=30.7400, lon=76.7800)
DEST = Coordinates(lat=30.9000, lon=75.8600)
ROUTE_GEOMETRY = {
    "type": "LineString",
    "coordinates": [
        [76.7800, 30.7400],
        [76.4000, 30.8000],
        [76.0000, 30.8600],
        [75.8600, 30.9000],
    ],
}


def _alert(lat, lon, severity="high", verified=True):
    return Alert(
        id="mid-route-test",
        description="Test alert",
        severity=severity,
        location=Coordinates(lat=lat, lon=lon),
        source="test",
        retrieved_at=NOW,
        verified=verified,
    )


def test_alert_near_middle_of_route_is_detected_via_geometry():
    # Sits essentially ON the second route vertex (76.40, 30.80) - would be
    # missed entirely by an endpoints-only check, since it's roughly
    # equidistant from and far from both ORIGIN and DEST individually.
    mid_alert = _alert(lat=30.80, lon=76.40)

    # Sanity check: this point IS far from both endpoints individually.
    from app.engine.risk_engine import _haversine_km

    dist_to_origin = _haversine_km(mid_alert.location, ORIGIN)
    dist_to_dest = _haversine_km(mid_alert.location, DEST)
    assert dist_to_origin > risk_engine.ROUTE_CORRIDOR_KM
    assert dist_to_dest > risk_engine.ROUTE_CORRIDOR_KM

    result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts=[mid_alert],
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            route_geometry=ROUTE_GEOMETRY,
            now=NOW,
        )
    )
    # It must be scored (i.e. detected as route-relevant), proving the
    # check used the full geometry rather than just the two endpoints.
    assert result.score == 30.0
    assert any("Test alert" in r for r in result.reasons)


def test_alert_near_middle_of_route_missed_without_geometry():
    """Same alert, but with geometry withheld - demonstrates the documented
    endpoint-only fallback behavior (and that it's explicitly reported)."""
    mid_alert = _alert(lat=30.80, lon=76.40)
    result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts=[mid_alert],
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            route_geometry=None,
            now=NOW,
        )
    )
    assert result.score == 0.0
    assert any("none were within" in r.lower() for r in result.reasons)
    assert any("geometry was unavailable" in r.lower() for r in result.reasons)


def test_alert_far_from_full_route_is_excluded():
    far_alert = _alert(lat=31.5, lon=77.5)  # well off the corridor
    result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts=[far_alert],
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            route_geometry=ROUTE_GEOMETRY,
            now=NOW,
        )
    )
    assert result.score == 0.0
    assert any("none were within" in r.lower() for r in result.reasons)


def test_malformed_geometry_falls_back_without_crashing():
    mid_alert = _alert(lat=30.80, lon=76.40)
    for bad_geometry in [
        {},
        {"type": "Point"},
        {"type": "LineString", "coordinates": []},
        None,
    ]:
        result = risk_engine.assess(
            risk_engine.RiskInputs(
                route_available=True,
                weather_status="unavailable",
                alerts=[mid_alert],
                alerts_status="ok",
                route_endpoints=[ORIGIN, DEST],
                route_geometry=bad_geometry,
                now=NOW,
            )
        )
        # Must not crash, and must fall back to the (less precise) endpoint check.
        assert result.level in ("low", "moderate", "high")
        assert result.score == 0.0
