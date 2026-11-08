from __future__ import annotations

from app.services.demo import get_demo_alerts


def test_demo_alert_descriptions_are_unmistakably_fictional():
    """Core data-integrity fix: the fictional disclaimer must live in the
    `description` field itself (what an API consumer actually sees), not
    only in an internal field that gets stripped before the response."""
    alerts = get_demo_alerts()
    assert len(alerts) == 2
    for a in alerts:
        assert "SIMULATED DEMO DATA" in a.description
        assert "not a real incident" in a.description.lower()
        assert a.verified is False
        assert a.source == "demo-data"
