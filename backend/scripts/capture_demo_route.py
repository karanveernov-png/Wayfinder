#!/usr/bin/env python3
"""
One-time capture tool: fetch a REAL route from the configured routing
provider (OSRM by default) and overwrite app/data/demo/demo_journey.json
with the provider's actual distance, duration, and geometry - plus the
retrieval timestamp and source URL used.

Why this exists: the stored demo route was originally a hand-approximated
polyline, not a genuine provider response (see the "route data" fix in
the project's backend-repair notes). This script is how you properly
source it instead - it does not fabricate anything; if the request
fails, it fails loudly and leaves the existing file untouched.

This script requires real network access to the geocoding/routing
providers. It could NOT be run in the sandboxed environment this repair
was performed in (DNS resolution to nominatim.openstreetmap.org and
router.project-osrm.org both fail there) - run it yourself wherever you
have outbound internet access.

Usage:
    cd backend
    python3 scripts/capture_demo_route.py
    python3 scripts/capture_demo_route.py --origin "Chandigarh, India" --destination "Ludhiana, Punjab, India"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.exceptions import ServiceError  # noqa: E402
from app.services.routing import RoutingService  # noqa: E402

DEMO_JOURNEY_PATH = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "data"
    / "demo"
    / "demo_journey.json"
)


async def main(origin_query: str, destination_query: str) -> int:
    settings = get_settings()
    async with httpx.AsyncClient(
        timeout=settings.REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": settings.HTTP_USER_AGENT},
    ) as http_client:
        routing = RoutingService(settings=settings, client=http_client)
        try:
            print(
                f"Geocoding origin: {origin_query!r} via {settings.GEOCODING_PROVIDER_URL}"
            )
            origin = await routing.geocode(origin_query)
            print(f"  -> {origin.coordinates} ({origin.display_name})")

            print(f"Geocoding destination: {destination_query!r}")
            destination = await routing.geocode(destination_query)
            print(f"  -> {destination.coordinates} ({destination.display_name})")

            print(f"Requesting route via {settings.ROUTING_PROVIDER_URL}")
            route = await routing.get_route(
                origin.coordinates, destination.coordinates, "driving"
            )
            print(
                f"  -> distance_km={route.distance_km} duration_minutes={route.duration_minutes}"
            )
        except ServiceError as exc:
            print(f"\nFAILED ({exc.provider}): {exc.message}", file=sys.stderr)
            print("Existing demo_journey.json was NOT modified.", file=sys.stderr)
            return 1
        finally:
            await routing.aclose()

    retrieved_at = datetime.now(timezone.utc).isoformat()
    # NOTE: this nested shape (origin/destination as sub-objects with
    # query/display_name/lat/lon) is what app/services/demo.py:get_demo_journey()
    # actually parses - keep this script in sync with that function if its
    # parsing logic ever changes.
    payload = {
        "_meta": {
            "note": (
                "Captured from a live routing-provider response by "
                "scripts/capture_demo_route.py. Distance/duration/geometry "
                "are the provider's own values, not estimates. A stored "
                "route can still become STALE - it does not reflect "
                "current traffic, closures, or road conditions at the time "
                "a user runs the demo. Re-run this script periodically if "
                "the demo should track provider data more closely."
            ),
            "provider_validated": True,
            "routing_provider_url": settings.ROUTING_PROVIDER_URL,
            "geocoding_provider_url": settings.GEOCODING_PROVIDER_URL,
            "retrieved_at": retrieved_at,
        },
        "origin": {
            "query": origin_query,
            "display_name": origin.display_name,
            "lat": origin.coordinates.lat,
            "lon": origin.coordinates.lon,
        },
        "destination": {
            "query": destination_query,
            "display_name": destination.display_name,
            "lat": destination.coordinates.lat,
            "lon": destination.coordinates.lon,
        },
        "distance_km": route.distance_km,
        "duration_minutes": route.duration_minutes,
        "travel_mode": "driving",
        "geometry": route.geometry,
    }

    DEMO_JOURNEY_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"\nWrote {DEMO_JOURNEY_PATH} with a provider-verified route (retrieved_at={retrieved_at})."
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="Chandigarh, India")
    parser.add_argument("--destination", default="Ludhiana, Punjab, India")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.origin, args.destination)))
