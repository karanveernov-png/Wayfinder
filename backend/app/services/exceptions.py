"""
Shared exception types for external-service integrations.

Route handlers catch these and translate them into honest, structured
responses (never a silently-fabricated 200 OK with fake data).
"""

from typing import Literal

# Explicit machine-readable reason a service couldn't produce data. Routes
# use this directly to set SourceMeta.status - NEVER by pattern-matching
# exc.message text (that was a real bug: inferring "not_configured" from
# the string "not configured" inside a human-readable message is brittle
# and breaks the moment the message wording changes).
UnavailableReason = Literal[
    "not_configured", "unreachable", "rate_limited", "invalid_credentials"
]


class ServiceError(Exception):
    """Base class for all external-service integration errors."""

    def __init__(self, message: str, *, provider: str):
        super().__init__(message)
        self.message = message
        self.provider = provider


class ServiceUnavailableError(ServiceError):
    """The provider is not configured, timed out, or is unreachable.

    `reason` is the explicit, structured cause - set by the raising code,
    never inferred downstream from the message text.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        reason: UnavailableReason = "unreachable",
    ):
        super().__init__(message, provider=provider)
        self.reason: UnavailableReason = reason


class ServiceResponseError(ServiceError):
    """The provider responded, but the response was invalid or unusable."""


class NotFoundError(ServiceError):
    """The provider successfully processed the request but found nothing
    (e.g. a route could not be calculated between the two points, or a
    place name could not be geocoded). This is distinct from the service
    being unavailable."""
