"""
Application configuration.

Loads settings from environment variables (and a local .env file in
development). Optional external providers are allowed to be unconfigured:
in that case the corresponding feature is marked unavailable at runtime
rather than crashing the application at startup.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("wayfinder.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: str = "development"
    # Comma-separated list of allowed frontend origins (exact scheme+host+port
    # match, used directly in CORSMiddleware's allow_origins - see main.py).
    # The defaults below are dev-only; ADD YOUR DEPLOYED FRONTEND'S ORIGIN
    # (e.g. https://your-app.vercel.app) here before deploying, or every
    # request from the deployed frontend will be CORS-blocked.
    # Vite's default dev-server port is 5173; 3000 kept for CRA / other tools.
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    # Geocoding is required to turn a free-text origin/destination into
    # coordinates before a route can be requested. Nominatim's public
    # instance is used by default (keyless, but rate-limited and subject
    # to its usage policy: https://operations.osmfoundation.org/policies/nominatim/).
    GEOCODING_PROVIDER_URL: Optional[str] = "https://nominatim.openstreetmap.org"
    GEOCODING_PROVIDER_KEY: Optional[str] = None

    # Routing: OSRM's public demo server is keyless and fine for an MVP,
    # but is explicitly NOT intended for production load
    # (https://project-osrm.org/ - "Demo server... fair use").
    ROUTING_PROVIDER_URL: Optional[str] = "https://router.project-osrm.org"
    ROUTING_PROVIDER_KEY: Optional[str] = None

    # Facilities: OpenStreetMap Overpass API (keyless).
    FACILITY_PROVIDER_URL: Optional[str] = "https://overpass-api.de/api/interpreter"
    FACILITY_PROVIDER_KEY: Optional[str] = None

    # Weather: Open-Meteo (keyless, no auth required for non-commercial use).
    WEATHER_PROVIDER_URL: Optional[str] = "https://api.open-meteo.com"
    WEATHER_PROVIDER_KEY: Optional[str] = None

    # Alerts: no free/keyless provider of verified TRAFFIC/road-closure data
    # was available at build time, but NASA's EONET (Earth Observatory
    # Natural Event Tracker) is a free, keyless, actively-maintained feed of
    # ongoing natural-hazard events (wildfires, storms, floods, volcanoes,
    # landslides, etc.) - a genuine, documented API, not a guess - so it is
    # configured here by default, the same way the other providers above
    # have free defaults. See app/services/alerts.py for what it does and
    # does not cover, and the README "Known Limitations" for why a true
    # traffic/road-closure feed is still not included.
    ALERT_PROVIDER_URL: Optional[str] = "https://eonet.gsfc.nasa.gov/api/v3"
    # Not used by the default EONET provider (keyless). Reserved for a
    # different alerts provider you might point ALERT_PROVIDER_URL at
    # instead, sent as a Bearer token if set - see services/alerts.py.
    ALERT_PROVIDER_KEY: Optional[str] = None
    # How many days back EONET should look for still-open events.
    ALERT_DAYS_LOOKBACK: int = 20

    # Supabase Auth + Database
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    # The secret Supabase signs user access-token JWTs with - NOT the anon/
    # publishable key (that is itself a token, not a signing secret; using it
    # here would reject every real user token). Dashboard -> Project Settings
    # -> API -> JWT Settings -> "JWT Secret". Required for GET/POST/DELETE
    # /saved-journeys (app/api/deps.py get_current_user) to work at all.
    SUPABASE_JWT_SECRET: Optional[str] = None

    # Optional Bhuvan primary routing provider. OSRM is the automatic backup.
    ISRO_BHUVAN_TOKEN: Optional[str] = None
    ISRO_BHUVAN_SHORTEST_PATH_URL: str = (
        "https://bhuvan-app1.nrsc.gov.in/api/routing/curl_routing_state.php"
    )

    # AI trip-planning: Groq (https://console.groq.com/docs/overview) turns a
    # natural-language request ("Plan a trip from Delhi to Shimla, prefer a
    # short route, show hospitals and pharmacies") into the SAME structured
    # fields /journeys/analyse already accepts - it never computes routes,
    # distances or facility data itself (see app/services/groq_service.py).
    # Optional, same convention as ALERT_PROVIDER_*/ISRO_BHUVAN_TOKEN above:
    # unset means the feature reports "not_configured" rather than crashing
    # the app at startup.
    GROQ_API_KEY: Optional[str] = None
    # openai/gpt-oss-20b is a currently-documented Groq production model
    # (console.groq.com/docs/models) that supports strict JSON Schema
    # structured outputs (console.groq.com/docs/structured-outputs) - a
    # good fit for "extract fixed fields from free text", not open-ended
    # chat. Override via GROQ_MODEL if Groq's lineup changes; see
    # app/services/groq_service.py _STRICT_SCHEMA_MODELS for the fallback
    # behaviour when the configured model doesn't support strict mode.
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_REQUEST_TIMEOUT_SECONDS: float = 15.0

    REQUEST_TIMEOUT_SECONDS: float = 10.0

    # NOT a real contact address - this is a placeholder that must be
    # replaced before any non-trivial use of the public Nominatim instance.
    # Nominatim's usage policy requires a genuine, working contact method in
    # the User-Agent so the operators can reach you if your traffic causes
    # problems (https://operations.osmfoundation.org/policies/nominatim/).
    # Set HTTP_USER_AGENT in your .env with a real app name and contact
    # email/URL before deploying this anywhere beyond local development.
    HTTP_USER_AGENT: str = (
        "wayfinder-backend/0.1 (PLACEHOLDER-SET-HTTP_USER_AGENT-CONTACT@CHANGE.ME)"
    )

    # Nominatim's usage policy caps public-instance traffic at roughly one
    # request per second; this is enforced in RoutingService.geocode() via a
    # simple async throttle rather than relying on callers to self-limit.
    NOMINATIM_MIN_INTERVAL_SECONDS: float = 1.0

    DEFAULT_FACILITY_RADIUS_KM: float = 5.0
    # Raised from 50.0 -> 70.0 for the hybrid map-to-globe feature (Nearby
    # Places' radius selector now goes up to 70km, entering "globe" view
    # past 20km - see frontend/src/lib/geo.js VIEW_MODE_THRESHOLDS_M). This
    # is the single bound /facilities/nearby validates against; keep it in
    # sync with the frontend's MAX_RADIUS_M if either changes.
    MAX_FACILITY_RADIUS_KM: float = 70.0
    # Matches the frontend's smallest radius preset (200m). A request below
    # this is rejected rather than silently accepted with an impractically
    # tiny or zero search area.
    MIN_FACILITY_RADIUS_KM: float = 0.2

    # --- Large-radius safeguards (section 7 of the hybrid map-to-globe spec) ---
    # A radius search above this threshold (globe-view territory) uses the
    # longer timeout and the larger Overpass result cap below, instead of
    # the small-radius defaults. Kept independent of the frontend's view-mode
    # threshold (which is a UI concern) even though both default to 20km.
    FACILITY_LARGE_RADIUS_THRESHOLD_KM: float = 20.0
    # Per-request HTTP timeout AND the Overpass `[timeout:N]` query clause
    # for large-radius searches, which cover far more area and can
    # legitimately take longer than REQUEST_TIMEOUT_SECONDS (used for every
    # other provider call, including small-radius facility searches) allows.
    # Not applied globally, so geocoding/routing/weather timeouts are
    # unaffected by this.
    FACILITY_LARGE_RADIUS_TIMEOUT_SECONDS: float = 25.0
    # Overpass's `out center N` limit for a large-radius query. Small-radius
    # queries keep the existing `len(categories) * 50 + 50` formula (fine
    # for a <=20km area); a wide area can plausibly contain far more mapped
    # facilities, so this is a separate, explicit, larger cap rather than
    # silently reusing the small-radius formula (which would arbitrarily
    # truncate results in a way not sorted by distance) or lifting the cap
    # entirely (unbounded response size/time against a shared public
    # instance). See FacilityService._overpass_out_limit.
    FACILITY_LARGE_RADIUS_RESULT_LIMIT: int = 400

    @field_validator("REQUEST_TIMEOUT_SECONDS")
    @classmethod
    def _positive_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("REQUEST_TIMEOUT_SECONDS must be positive")
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def routing_configured(self) -> bool:
        return bool(self.ROUTING_PROVIDER_URL)

    @property
    def geocoding_configured(self) -> bool:
        return bool(self.GEOCODING_PROVIDER_URL)

    @property
    def facilities_configured(self) -> bool:
        return bool(self.FACILITY_PROVIDER_URL)

    @property
    def weather_configured(self) -> bool:
        return bool(self.WEATHER_PROVIDER_URL)

    @property
    def alerts_configured(self) -> bool:
        return bool(self.ALERT_PROVIDER_URL)

    @property
    def groq_configured(self) -> bool:
        return bool(self.GROQ_API_KEY)

    def log_provider_status(self) -> None:
        logger.info("Provider availability at startup:")
        logger.info(
            "  routing:    %s",
            "configured" if self.routing_configured else "NOT configured",
        )
        logger.info(
            "  geocoding:  %s",
            "configured" if self.geocoding_configured else "NOT configured",
        )
        logger.info(
            "  facilities: %s",
            "configured" if self.facilities_configured else "NOT configured",
        )
        logger.info(
            "  weather:    %s",
            "configured" if self.weather_configured else "NOT configured",
        )
        logger.info(
            "  alerts:     %s",
            "configured"
            if self.alerts_configured
            else "NOT configured (no key/url set)",
        )
        logger.info(
            "  groq (AI trip-planning): %s",
            "configured" if self.groq_configured else "NOT configured (GROQ_API_KEY unset)",
        )
        if "CHANGE.ME" in self.HTTP_USER_AGENT or "PLACEHOLDER" in self.HTTP_USER_AGENT:
            logger.warning(
                "HTTP_USER_AGENT is still the placeholder value. Nominatim's usage "
                "policy requires a real, working contact method - set HTTP_USER_AGENT "
                "in your .env before any non-trivial geocoding traffic."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
