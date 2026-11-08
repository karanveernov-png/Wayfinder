"""
Groq service: turns a free-text trip request into the structured
``ParsedTripIntent`` fields (app/schemas/trip_intent.py).

What this module is - and is not:
  - It ONLY interprets the user's sentence into fixed fields (origin,
    destination, travel mode, priorities, requested facility types). It
    never computes a route, a distance, a travel time, or a list of
    hospitals/pharmacies itself - those always come from the existing
    RoutingService / FacilityService, called afterwards by
    app/api/routes/trip_intent.py with the validated output of this
    module. The LLM interprets; it does not calculate or invent
    geographical information.
  - It never executes code, and never calls an arbitrary function the
    model names - Groq is used here purely for text-in/JSON-out, with no
    tool-calling. The model's only output is validated JSON text.
  - The API key never leaves the backend; this module is only imported
    by server-side code.

Structured output strategy:
  Groq's "Structured Outputs" feature can force a model's response to
  exactly match a JSON Schema ("strict" mode - see
  https://console.groq.com/docs/structured-outputs), but as of this
  writing only a handful of models support it. `_STRICT_SCHEMA_MODELS`
  below is the documented list. When the configured GROQ_MODEL is in
  that set, this module uses strict json_schema mode (the model's output
  is guaranteed schema-valid). For any other model (e.g. if GROQ_MODEL is
  overridden to a general chat model that doesn't support strict mode),
  it falls back to Groq's basic JSON Object Mode plus an explicit
  Pydantic validation pass in Python - the "reliable fallback" the
  project spec asks for. Either way the output is validated against
  ParsedTripIntent before anything downstream ever sees it.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import groq
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.trip_intent import ParsedTripIntent
from app.services.exceptions import ServiceResponseError, ServiceUnavailableError

logger = logging.getLogger("wayfinder.services.groq")

# Groq production/preview models documented (as of this writing, see
# console.groq.com/docs/structured-outputs) to support STRICT JSON Schema
# structured outputs. Keep this in sync if Groq's lineup changes - any
# model not in this set automatically uses the JSON-object fallback path
# below instead of failing outright.
_STRICT_SCHEMA_MODELS = frozenset(
    {
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "qwen/qwen3.8-27b",
        "meta-models/muse-spark-open",
    }
)

_TRIP_INTENT_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "origin": {
            "type": ["string", "null"],
            "description": "The trip's starting place, exactly as the user wrote or implied it. Null if not determinable.",
        },
        "destination": {
            "type": ["string", "null"],
            "description": "The trip's destination. Null if not determinable.",
        },
        "travel_mode": {
            "type": "string",
            "enum": ["driving", "two-wheeler", "cycling", "transit"],
        },
        "priorities": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["shorter_travel_time", "easier_route", "avoid_highways"],
            },
        },
        "facilities": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["hospital", "fuel", "restaurant", "rest_stop", "pharmacy", "lodging"],
            },
        },
        "needs_clarification": {
            "type": "boolean",
            "description": "True if origin and/or destination could not be confidently determined.",
        },
        "clarification_message": {
            "type": ["string", "null"],
            "description": "A short question for the user. Required to be non-null when needs_clarification is true.",
        },
    },
    "required": [
        "origin",
        "destination",
        "travel_mode",
        "priorities",
        "facilities",
        "needs_clarification",
        "clarification_message",
    ],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = """You are a trip-request parser for a road-navigation app. \
Extract ONLY the following fields from the user's message, as JSON matching \
the given schema. You do not plan routes, calculate distances, or know real \
hospital/pharmacy names - another part of the system does that with real \
map data. Your only job is understanding the sentence.

Rules:
- "origin" / "destination": the place names the user stated or clearly \
implied. Copy them as written (do not geocode, correct spelling, or add \
", India" or any region unless the user wrote it). If either is missing or \
too vague to act on (e.g. "somewhere nice"), set it to null.
- If origin or destination is null, set "needs_clarification" to true and \
"clarification_message" to one short, friendly question asking the user to \
provide the missing piece(s). Otherwise "needs_clarification" is false and \
"clarification_message" is null.
- "travel_mode": one of driving, two-wheeler, cycling, transit. Default to \
"driving" unless the message clearly implies another (e.g. "on my bike" -> \
cycling, "by bus"/"by train" -> transit, "on my scooter/motorcycle" -> \
two-wheeler).
- "priorities": only include values the message clearly asks for - \
"shorter_travel_time" for requests about the fastest/shortest/quickest \
option, "easier_route" for easy/simple/less-complicated requests, \
"avoid_highways" only if explicitly requested. Leave the list empty if \
nothing like this is mentioned - do not guess.
- "facilities": only include categories the user actually asked to see, \
from this fixed list: hospital, fuel, restaurant, rest_stop, pharmacy, \
lodging (map "pharmacies"/"medicine/chemist" -> pharmacy, "hospitals/medical \
help" -> hospital, "gas/petrol/fuel station" -> fuel, "food/restaurants/cafes" \
-> restaurant, "hotels/places to stay" -> lodging, "rest stops/breaks" -> \
rest_stop). Leave the list empty if the user didn't ask for any facilities.

Never invent a place name, distance, or travel time. Return ONLY the JSON object."""


class GroqService:
    """Thin wrapper around the Groq SDK for the trip-intent feature only."""

    def __init__(self, settings: Settings, client: Optional["groq.AsyncGroq"] = None):
        self._settings = settings
        self._client = client

    def _get_client(self) -> "groq.AsyncGroq":
        if self._client is None:
            self._client = groq.AsyncGroq(
                api_key=self._settings.GROQ_API_KEY,
                timeout=self._settings.GROQ_REQUEST_TIMEOUT_SECONDS,
                max_retries=0,  # the route handler surfaces failures honestly; no silent retries
            )
        return self._client

    async def parse_trip_request(self, message: str) -> ParsedTripIntent:
        if not self._settings.groq_configured:
            raise ServiceUnavailableError(
                "GROQ_API_KEY is not configured.",
                provider="groq",
                reason="not_configured",
            )

        model = self._settings.GROQ_MODEL
        use_strict_schema = model in _STRICT_SCHEMA_MODELS
        client = self._get_client()

        if use_strict_schema:
            response_format: Dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "trip_intent",
                    "strict": True,
                    "schema": _TRIP_INTENT_JSON_SCHEMA,
                },
            }
        else:
            # Fallback for a configured model that doesn't support strict
            # JSON Schema structured outputs: basic JSON Object Mode, with
            # the schema spelled out in the prompt itself instead, and a
            # full Pydantic validation pass below (never trust this path's
            # output without validating it, unlike the strict path which is
            # schema-guaranteed by Groq itself).
            logger.info(
                "GROQ_MODEL=%s does not support strict JSON Schema mode; "
                "using JSON object mode with manual validation.",
                model,
            )
            response_format = {"type": "json_object"}

        system_prompt = _SYSTEM_PROMPT
        if not use_strict_schema:
            system_prompt += (
                "\n\nRespond with a single JSON object with EXACTLY these keys: "
                "origin, destination, travel_mode, priorities, facilities, "
                "needs_clarification, clarification_message. No other text."
            )

        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                response_format=response_format,
                temperature=0,
                max_tokens=500,
            )
        except groq.AuthenticationError as exc:
            raise ServiceUnavailableError(
                "Groq rejected the configured GROQ_API_KEY (invalid credentials).",
                provider="groq",
                reason="invalid_credentials",
            ) from exc
        except groq.PermissionDeniedError as exc:
            raise ServiceUnavailableError(
                "Groq denied access for the configured GROQ_API_KEY.",
                provider="groq",
                reason="invalid_credentials",
            ) from exc
        except groq.RateLimitError as exc:
            raise ServiceUnavailableError(
                "Groq rate-limited this request.",
                provider="groq",
                reason="rate_limited",
            ) from exc
        except groq.APITimeoutError as exc:
            raise ServiceUnavailableError(
                f"Groq request timed out after {self._settings.GROQ_REQUEST_TIMEOUT_SECONDS}s.",
                provider="groq",
                reason="unreachable",
            ) from exc
        except groq.APIConnectionError as exc:
            raise ServiceUnavailableError(
                f"Could not reach Groq: {exc}",
                provider="groq",
                reason="unreachable",
            ) from exc
        except groq.BadRequestError as exc:
            # In strict mode this shouldn't happen (Groq guarantees
            # schema-valid output); in JSON-object fallback mode a model
            # can occasionally reject the request outright.
            raise ServiceResponseError(
                f"Groq rejected the request: {exc}", provider="groq"
            ) from exc
        except groq.InternalServerError as exc:
            raise ServiceUnavailableError(
                f"Groq reported a server error: {exc}",
                provider="groq",
                reason="unreachable",
            ) from exc
        except groq.APIStatusError as exc:
            raise ServiceResponseError(
                f"Groq returned an unexpected error (status {exc.status_code}).",
                provider="groq",
            ) from exc
        except groq.GroqError as exc:
            # Defensive catch-all for any other Groq SDK error so a change
            # upstream can never crash the endpoint.
            raise ServiceUnavailableError(
                f"Groq request failed: {exc}", provider="groq", reason="unreachable"
            ) from exc

        choices = completion.choices or []
        if not choices or choices[0].message is None:
            raise ServiceResponseError(
                "Groq response contained no message content.", provider="groq"
            )

        raw_content = choices[0].message.content
        if not raw_content:
            raise ServiceResponseError(
                "Groq returned an empty response.", provider="groq"
            )

        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ServiceResponseError(
                "Groq returned malformed JSON.", provider="groq"
            ) from exc

        if not isinstance(payload, dict):
            raise ServiceResponseError(
                "Groq's JSON response was not an object.", provider="groq"
            )

        try:
            intent = ParsedTripIntent.model_validate(payload)
        except ValidationError as exc:
            raise ServiceResponseError(
                f"Groq's output did not match the expected trip-intent schema: {exc}",
                provider="groq",
            ) from exc

        # Belt-and-suspenders: never let missing-origin/destination slip
        # through as "ok" even if the model forgot to set the flag itself.
        if (not intent.origin or not intent.destination) and not intent.needs_clarification:
            intent = intent.model_copy(
                update={
                    "needs_clarification": True,
                    "clarification_message": intent.clarification_message
                    or "I couldn't tell where you want to start and/or end this trip - could you name both the starting point and the destination?",
                }
            )

        return intent
