"""
Deterministic, rule-based risk-analysis engine.

Design constraints (see master spec section 6):
  - No FastAPI or HTTP dependencies here - pure functions over normalized
    data, so it can be unit tested in isolation and never silently
    depends on a particular transport or provider.
  - Duplicate alert reports must not be counted as independent evidence.
  - Missing data is never interpreted as evidence of safety.
  - Unknown-severity events are never assigned an arbitrary severity.
  - If there isn't enough reliable information, the result is "unknown",
    not a misleading number.
  - The score never claims to predict accidents or guarantee safety.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.schemas.alert import Alert
from app.schemas.common import Coordinates
from app.schemas.journey import RiskAssessment
from app.schemas.weather import WeatherObservation
from app.services.weather import ADVERSE_WEATHER_CODES

SAFETY_DISCLAIMER = (
    "This assessment reflects currently available data only. It does not "
    "predict accidents and does not guarantee travel safety."
)

# Score thresholds (0-100 scale, higher = more caution warranted).
LEVEL_THRESHOLDS = (
    (25, "low"),
    (60, "moderate"),
    (101, "high"),
)

ALERT_SEVERITY_WEIGHT = {"high": 30.0, "moderate": 15.0, "low": 5.0, "unknown": 0.0}

# Corridor half-width: an alert whose location is within this many km of the
# NEAREST POINT ON THE ROUTE LINE (not just the two endpoints) is treated as
# route-relevant. Checked against the full GeoJSON LineString when available;
# falls back to endpoint-only distance (and says so in `reasons`) when route
# geometry is missing, which is less precise and documented as such rather
# than silently treated as equivalent.
ROUTE_CORRIDOR_KM = 10.0
ALERT_STALE_HOURS = 12.0  # reports older than this get reduced weight

WEATHER_CODE_WEIGHT = {
    # fog
    45: 15.0,
    48: 18.0,
    # drizzle / freezing drizzle
    51: 8.0,
    53: 10.0,
    55: 12.0,
    56: 18.0,
    57: 20.0,
    # rain / freezing rain
    61: 12.0,
    63: 18.0,
    65: 25.0,
    66: 22.0,
    67: 28.0,
    # snow
    71: 20.0,
    73: 25.0,
    75: 30.0,
    77: 18.0,
    # rain showers
    80: 15.0,
    81: 20.0,
    82: 28.0,
    # snow showers
    85: 22.0,
    86: 28.0,
    # thunderstorm
    95: 32.0,
    96: 36.0,
    99: 40.0,
}
HIGH_WIND_KMH_THRESHOLD = 50.0
HIGH_WIND_WEIGHT = 10.0


@dataclass
class RiskInputs:
    route_available: bool
    weather: Optional[WeatherObservation] = None
    weather_status: str = (
        "unavailable"  # "ok" | "unavailable" | "error" | "not_configured"
    )
    alerts: Optional[List[Alert]] = None
    alerts_status: str = "unavailable"
    route_endpoints: List[Coordinates] = field(default_factory=list)
    route_geometry: Optional[dict] = field(
        default=None,
        metadata={
            "doc": "GeoJSON LineString ({'type': 'LineString', 'coordinates': [[lon,lat],...]}) "
            "used for route-corridor alert proximity. Falls back to endpoint-only "
            "distance when None/invalid."
        },
    )
    now: Optional[datetime] = None


def _haversine_km(a: Coordinates, b: Coordinates) -> float:
    r = 6371.0088
    lat1, lon1, lat2, lon2 = map(math.radians, [a.lat, a.lon, b.lat, b.lon])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(h))


def _project_km(lat: float, lon: float, ref_lat: float) -> Tuple[float, float]:
    """Local tangent-plane projection to (x_km, y_km), accurate enough for
    the highway-corridor distances this engine deals with (tens-hundreds
    of km); not meant for geodesy at a global scale."""
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * math.cos(math.radians(ref_lat))
    return lon * km_per_deg_lon, lat * km_per_deg_lat


def _point_to_segment_km(
    p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]
) -> float:
    """Minimum distance from point p to segment a-b, all in projected km."""
    ax, ay = a
    bx, by = b
    px, py = p
    abx, aby = bx - ax, by - ay
    len_sq = abx * abx + aby * aby
    if len_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / len_sq))
    cx, cy = ax + t * abx, ay + t * aby
    return math.hypot(px - cx, py - cy)


def _distance_to_route_geometry_km(
    point: Coordinates, geometry: Optional[dict]
) -> Optional[float]:
    """Minimum distance (km) from `point` to the route LineString, checking
    every segment - not just the two endpoints. Returns None if geometry is
    missing/malformed so the caller can fall back explicitly and say so,
    rather than this function silently guessing."""
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        return None
    coords = geometry.get("coordinates") or []
    if len(coords) < 2:
        return None

    ref_lat = point.lat
    try:
        p = _project_km(point.lat, point.lon, ref_lat)
        best = math.inf
        prev = None
        for lon, lat in coords:
            cur = _project_km(float(lat), float(lon), ref_lat)
            if prev is not None:
                best = min(best, _point_to_segment_km(p, prev, cur))
            prev = cur
    except (TypeError, ValueError, IndexError):
        return None

    return best if best != math.inf else None


def _dedupe_alerts(alerts: List[Alert]) -> List[Alert]:
    """Collapse alerts that plausibly describe the same real-world event so
    duplicated reports are never counted as independent evidence."""
    seen: Dict[tuple, Alert] = {}
    for a in alerts:
        if a.id:
            key = ("id", a.id)
        else:
            loc_key = None
            if a.location is not None:
                loc_key = (round(a.location.lat, 3), round(a.location.lon, 3))
            key = ("desc", a.category, loc_key, a.description.strip().lower())
        if key not in seen:
            seen[key] = a
    return list(seen.values())


def _level_for_score(score: float) -> str:
    for threshold, level in LEVEL_THRESHOLDS:
        if score < threshold:
            return level
    return "high"


def assess(inputs: RiskInputs) -> RiskAssessment:
    reasons: List[str] = []

    if not inputs.route_available:
        return RiskAssessment(
            level="unknown",
            score=None,
            reasons=[
                "Route could not be calculated, so no risk assessment can be produced.",
                SAFETY_DISCLAIMER,
            ],
        )

    weather_usable = inputs.weather_status == "ok"
    alerts_usable = inputs.alerts_status == "ok"

    if not weather_usable and not alerts_usable:
        return RiskAssessment(
            level="unknown",
            score=None,
            reasons=[
                "Insufficient reliable information to assess this journey: "
                "both the weather and alerts sources were unavailable.",
                SAFETY_DISCLAIMER,
            ],
        )

    score = 0.0
    now = inputs.now or datetime.now(timezone.utc)

    # --- Weather contribution ---
    if weather_usable and inputs.weather is not None:
        w = inputs.weather
        if w.weather_code is not None and w.weather_code in ADVERSE_WEATHER_CODES:
            weight = WEATHER_CODE_WEIGHT.get(w.weather_code, 15.0)
            score += weight
            reasons.append(
                f"Current weather near the route (code {w.weather_code}) indicates "
                f"potentially hazardous conditions."
            )
        else:
            reasons.append(
                "Current weather near the route does not indicate hazardous conditions."
            )

        if w.windspeed_kmh is not None and w.windspeed_kmh >= HIGH_WIND_KMH_THRESHOLD:
            score += HIGH_WIND_WEIGHT
            reasons.append(
                f"Wind speed ({w.windspeed_kmh:.0f} km/h) is high enough to affect driving conditions."
            )
    elif not weather_usable:
        reasons.append(
            "Weather data was unavailable, so weather-related risk could not be included."
        )

    # --- Alerts contribution ---
    if alerts_usable:
        all_alerts = inputs.alerts or []
        unique_alerts = _dedupe_alerts(all_alerts)
        if len(all_alerts) != len(unique_alerts):
            reasons.append(
                f"{len(all_alerts) - len(unique_alerts)} duplicate alert report(s) were "
                f"collapsed and counted once."
            )

        relevant_alerts = []
        used_endpoint_fallback = False
        for a in unique_alerts:
            if a.location is None:
                # Can't establish proximity - treat as not confirmed relevant, note it, don't drop silently.
                reasons.append(
                    f"An alert ('{a.description[:60]}') has no location data and could not be checked for route relevance."
                )
                continue

            route_dist = _distance_to_route_geometry_km(
                a.location, inputs.route_geometry
            )
            if route_dist is not None:
                min_dist = route_dist
            elif inputs.route_endpoints:
                # Missing/invalid geometry: fall back to endpoint-only distance.
                # This is explicitly reported (not silently treated as
                # equivalent) because it can miss a genuinely mid-route alert
                # (false negative) - it cannot manufacture a false positive,
                # since it only ever widens what counts as "close enough".
                min_dist = min(
                    _haversine_km(a.location, ep) for ep in inputs.route_endpoints
                )
                used_endpoint_fallback = True
            else:
                reasons.append(
                    f"An alert ('{a.description[:60]}') could not be checked for route "
                    f"relevance: no route geometry or endpoints were available."
                )
                continue

            if min_dist <= ROUTE_CORRIDOR_KM:
                relevant_alerts.append(a)

        if not unique_alerts:
            reasons.append("No relevant alerts were returned by the alerts source.")
        elif not relevant_alerts:
            reasons.append(
                f"{len(unique_alerts)} alert(s) were returned but none were within "
                f"{ROUTE_CORRIDOR_KM:.0f} km of the route."
            )
        if used_endpoint_fallback:
            reasons.append(
                "Route geometry was unavailable for at least one alert, so relevance "
                "was checked against the origin/destination points only, not the full "
                "route line - a mid-route alert could have been missed."
            )

        for a in relevant_alerts:
            weight = ALERT_SEVERITY_WEIGHT.get(a.severity, 0.0)
            if a.severity == "unknown":
                reasons.append(
                    f"An alert of unknown severity was reported near the route "
                    f"('{a.description[:80]}'); it is listed but not scored, since severity cannot be assumed."
                )
                continue

            if a.verified is False:
                weight *= 0.5
                staleness_note = ""
            elif a.verified is None:
                weight *= 0.75
                staleness_note = ""
            else:
                staleness_note = ""

            if a.retrieved_at is not None:
                age_hours = (now - a.retrieved_at).total_seconds() / 3600.0
                if age_hours > ALERT_STALE_HOURS:
                    weight *= 0.5
                    staleness_note = (
                        f", reported {age_hours:.0f}h ago (reduced weight due to age)"
                    )

            score += weight
            verified_note = {
                True: "verified",
                False: "unverified",
                None: "verification unknown",
            }[a.verified]
            reasons.append(
                f"{a.severity.capitalize()}-severity alert near the route ({verified_note}{staleness_note}): "
                f"{a.description[:100]}"
            )
    else:
        reasons.append(
            "Alert data was unavailable, so reported incidents could not be included in this score."
        )

    score = max(0.0, min(100.0, round(score, 1)))
    level = _level_for_score(score)

    # If only one of the two inputs was usable, say so plainly rather than
    # implying the score is comprehensive.
    if weather_usable != alerts_usable:
        missing = "alert" if not alerts_usable else "weather"
        reasons.append(
            f"Note: this score only reflects the available data source(s); {missing} data was not included."
        )

    reasons.append(SAFETY_DISCLAIMER)

    return RiskAssessment(level=level, score=score, reasons=reasons)


def recommendations_for(
    assessment: RiskAssessment,
    facilities_available: bool,
    alerts_status: str,
    weather_status: str,
) -> List[str]:
    """Generate recommendations tied directly to the actual assessment, not generic boilerplate."""
    recs: List[str] = []

    if assessment.level == "unknown":
        recs.append(
            "Check local conditions independently before departing, since this analysis could not be completed with the available data."
        )
    elif assessment.level == "high":
        recs.append(
            "Review the listed risk reasons carefully and consider delaying travel or choosing an alternate route if possible."
        )
    elif assessment.level == "moderate":
        recs.append(
            "Proceed with added caution and allow extra travel time given the conditions noted above."
        )
    else:
        recs.append(
            "No significant issues were found in the available data; standard travel precautions still apply."
        )

    if weather_status != "ok":
        recs.append(
            "Check a live weather source before departing, since weather data could not be retrieved here."
        )
    if alerts_status != "ok":
        recs.append(
            "Check a live traffic/alerts source before departing, since no alerts provider is currently configured."
        )
    if facilities_available:
        recs.append(
            "Nearby facilities found along the route are listed below for reference."
        )

    return recs
