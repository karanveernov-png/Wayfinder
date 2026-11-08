from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.engine import risk_engine
from app.schemas.alert import Alert
from app.schemas.common import Coordinates
from app.schemas.weather import WeatherObservation

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
ORIGIN = Coordinates(lat=31.326, lon=75.576)
DEST = Coordinates(lat=30.733, lon=76.779)


def test_route_unavailable_is_unknown_not_fabricated():
    result = risk_engine.assess(risk_engine.RiskInputs(route_available=False))
    assert result.level == "unknown"
    assert result.score is None


def test_both_sources_unavailable_is_unknown():
    result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts_status="unavailable",
            route_endpoints=[ORIGIN, DEST],
        )
    )
    assert result.level == "unknown"
    assert result.score is None


def test_no_hazards_found_scores_low_not_zero_claim_of_safety():
    clear_weather = WeatherObservation(
        location=DEST, weather_code=0, windspeed_kmh=5, source="open-meteo"
    )
    result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather=clear_weather,
            weather_status="ok",
            alerts=[],
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            now=NOW,
        )
    )
    assert result.level == "low"
    assert result.score == 0.0
    assert any("does not indicate hazardous" in r for r in result.reasons)
    assert any(
        "does not" in r.lower() and "guarantee" in r.lower() for r in result.reasons
    )


def test_verified_high_severity_alert_raises_score():
    alert = Alert(
        id="a1",
        description="Major bridge collapse blocking the highway",
        category="road_closure",
        severity="high",
        location=DEST,
        source="test-provider",
        retrieved_at=NOW,
        verified=True,
    )
    result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts=[alert],
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            now=NOW,
        )
    )
    assert result.score == 30.0
    # A single verified high-severity alert (30/100) crosses into "moderate";
    # "high" requires either a more severe single event or several compounding ones.
    assert result.level == "moderate"
    assert any("Major bridge collapse" in r for r in result.reasons)


def test_multiple_high_severity_alerts_reach_high_level():
    alerts = [
        Alert(
            id="a1",
            description="Bridge collapse",
            severity="high",
            location=DEST,
            source="t",
            retrieved_at=NOW,
            verified=True,
        ),
        Alert(
            id="a2",
            description="Major flooding on highway",
            severity="high",
            location=DEST,
            source="t",
            retrieved_at=NOW,
            verified=True,
        ),
    ]
    result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts=alerts,
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            now=NOW,
        )
    )
    assert result.score == 60.0
    assert result.level == "high"


def test_duplicate_alerts_counted_once():
    alert = Alert(
        description="Flooding reported on route",
        category="flood",
        severity="moderate",
        location=DEST,
        source="test-provider",
        retrieved_at=NOW,
        verified=True,
    )
    duplicate = alert.model_copy()
    result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts=[alert, duplicate],
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            now=NOW,
        )
    )
    # Severity "moderate" weight is 15.0 - must appear ONCE, not doubled to 30.0
    assert result.score == 15.0
    assert any("duplicate" in r.lower() for r in result.reasons)


def test_unverified_and_stale_alert_gets_reduced_weight_vs_fresh_verified():
    fresh_verified = Alert(
        id="fresh",
        description="Accident reported",
        severity="moderate",
        location=DEST,
        source="test",
        retrieved_at=NOW,
        verified=True,
    )
    stale_unverified = Alert(
        id="stale",
        description="Accident reported",
        severity="moderate",
        location=DEST,
        source="test",
        retrieved_at=NOW - timedelta(hours=48),
        verified=False,
    )

    fresh_result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts=[fresh_verified],
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            now=NOW,
        )
    )
    stale_result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts=[stale_unverified],
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            now=NOW,
        )
    )
    assert stale_result.score < fresh_result.score


def test_unknown_severity_alert_is_not_assigned_arbitrary_score():
    alert = Alert(
        description="Unconfirmed report near the route",
        severity="unknown",
        location=DEST,
        source="test",
        retrieved_at=NOW,
        verified=None,
    )
    result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts=[alert],
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            now=NOW,
        )
    )
    assert result.score == 0.0
    assert any("unknown severity" in r.lower() for r in result.reasons)


def test_alert_far_from_route_not_counted():
    far_away = Coordinates(lat=10.0, lon=10.0)
    alert = Alert(
        description="Unrelated distant event",
        severity="high",
        location=far_away,
        source="test",
        retrieved_at=NOW,
        verified=True,
    )
    result = risk_engine.assess(
        risk_engine.RiskInputs(
            route_available=True,
            weather_status="unavailable",
            alerts=[alert],
            alerts_status="ok",
            route_endpoints=[ORIGIN, DEST],
            now=NOW,
        )
    )
    assert result.score == 0.0
    assert any("none were within" in r.lower() for r in result.reasons)


def test_recommendations_reflect_actual_findings():
    unknown_assessment = risk_engine.RiskAssessment(
        level="unknown", score=None, reasons=[]
    )
    recs = risk_engine.recommendations_for(
        unknown_assessment,
        facilities_available=False,
        alerts_status="unavailable",
        weather_status="unavailable",
    )
    assert any("could not be completed" in r for r in recs)

    high_assessment = risk_engine.RiskAssessment(level="high", score=80, reasons=[])
    recs = risk_engine.recommendations_for(
        high_assessment,
        facilities_available=True,
        alerts_status="ok",
        weather_status="ok",
    )
    assert any("delaying" in r.lower() or "alternate route" in r.lower() for r in recs)
    assert any("nearby facilities" in r.lower() for r in recs)
