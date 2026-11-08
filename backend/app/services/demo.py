"""
Demo mode data service.

Loads pre-stored, clearly-labelled demonstration data for the
Chandigarh → Ludhiana (NH-95) corridor. Used when a journey analysis
request includes ``demo=true``.

Design rules:
  - No live provider calls are made here.
  - All returned objects use ``source="demo-*"`` so downstream code and
    the frontend can clearly distinguish demo records from live data.
  - The risk engine still runs on the demo inputs (real engine, demo data),
    so the risk-assessment output is demonstrably produced by real logic.
  - Coordinates in demo_facilities.json are address-derived approximations,
    not geocoder or Overpass output. Each record's verification_status is
    "unverified_coordinates" (never "verified") and coordinate_source
    documents how the estimate was produced. They are not random/fabricated
    values - each is a best-estimate for the documented address along the
    NH-95 corridor - but they have not been independently confirmed.
  - Demo alerts in demo_alerts.json are clearly fictional; the _demo_note
    field in each record says so explicitly.  Never present them as live
    traffic reports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from app.schemas.alert import Alert
from app.schemas.common import Coordinates
from app.schemas.facility import Facility

_DATA_DIR = Path(__file__).parent.parent / "data" / "demo"


@dataclass(frozen=True)
class DemoJourney:
    origin_query: str
    origin_display: str
    origin_coords: Coordinates
    destination_query: str
    destination_display: str
    destination_coords: Coordinates
    distance_km: float
    duration_minutes: float
    geometry: dict  # GeoJSON LineString


def _load(filename: str):
    with (_DATA_DIR / filename).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_demo_journey() -> DemoJourney:
    d = _load("demo_journey.json")
    return DemoJourney(
        origin_query=d["origin"]["query"],
        origin_display=d["origin"]["display_name"],
        origin_coords=Coordinates(lat=d["origin"]["lat"], lon=d["origin"]["lon"]),
        destination_query=d["destination"]["query"],
        destination_display=d["destination"]["display_name"],
        destination_coords=Coordinates(
            lat=d["destination"]["lat"], lon=d["destination"]["lon"]
        ),
        distance_km=d["distance_km"],
        duration_minutes=d["duration_minutes"],
        geometry=d["geometry"],
    )


def get_demo_facilities() -> List[Facility]:
    """
    Return the 18 CANDIDATE POIs from the Chandigarh-Ludhiana highway
    directory (Deepak's dataset). These are NOT independently verified
    locations - every record carries verification_status="unverified_coordinates"
    because the coordinates are address-derived manual approximations, not
    geocoder or Overpass output (see demo_facilities.json and
    docs/API_CONTRACT.md "Facility verification"). The ``_coord_note`` and
    any other ``_``-prefixed keys in the raw JSON are metadata and are not
    passed to the Facility schema.

    A record that fails schema validation is a data bug, not something to
    paper over - this raises rather than silently dropping it, so a bad
    demo-data edit fails loudly (at import/test time) instead of quietly
    shrinking the facility count in production.
    """
    raw: list = _load("demo_facilities.json")
    facilities: List[Facility] = []
    for item in raw:
        # Strip private metadata keys before Pydantic validation.
        clean = {k: v for k, v in item.items() if not k.startswith("_")}
        try:
            facilities.append(Facility(**clean))
        except Exception as exc:
            raise ValueError(
                f"Invalid demo facility record (id={item.get('id', '?')}): {exc}"
            ) from exc
    return facilities


def get_demo_alerts() -> List[Alert]:
    """
    Return the two demonstration alerts for the Ludhiana approach on NH-95.
    Both are unmistakably fictional: the `description` text itself starts
    with an explicit "[SIMULATED DEMO DATA]" marker (not just an internal
    `_demo_note` that would never reach an API consumer), plus
    source="demo-data" and verified=False.

    Same fail-loud policy as get_demo_facilities(): a malformed record
    raises instead of being silently skipped.
    """
    raw: list = _load("demo_alerts.json")
    alerts: List[Alert] = []
    for item in raw:
        clean = {k: v for k, v in item.items() if not k.startswith("_")}
        try:
            alerts.append(Alert(**clean))
        except Exception as exc:
            raise ValueError(
                f"Invalid demo alert record (id={item.get('id', '?')}): {exc}"
            ) from exc
    return alerts
