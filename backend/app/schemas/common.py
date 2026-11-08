"""Shared schema primitives used across journeys, facilities, weather, alerts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Coordinates(BaseModel):
    lat: float = Field(..., description="Latitude in decimal degrees")
    lon: float = Field(..., description="Longitude in decimal degrees")

    @field_validator("lat")
    @classmethod
    def _valid_lat(cls, v: float) -> float:
        if not -90.0 <= v <= 90.0:
            raise ValueError("lat must be between -90 and 90")
        return v

    @field_validator("lon")
    @classmethod
    def _valid_lon(cls, v: float) -> float:
        if not -180.0 <= v <= 180.0:
            raise ValueError("lon must be between -180 and 180")
        return v


SourceStatus = Literal["ok", "unavailable", "error", "not_configured"]


class SourceMeta(BaseModel):
    """Describes the outcome of calling one external data source."""

    name: str = Field(
        ..., description="Human-readable provider name, e.g. 'osrm-routing'"
    )
    status: SourceStatus
    detail: Optional[str] = Field(
        None, description="Human-readable explanation, populated when status != 'ok'"
    )
    retrieved_at: Optional[datetime] = Field(
        None, description="UTC timestamp the data was retrieved, if status == 'ok'"
    )


class DataStatus(BaseModel):
    """
    Top-level honesty signal for API consumers.

    mode:
      - "live"     -> every requested source returned usable data
      - "partial"  -> at least one non-critical source failed/was unavailable,
                       but the response still contains usable results
      - "degraded" -> a critical source (e.g. routing) failed; results may
                       be missing core fields
      - "demo"     -> pre-stored demonstration data was returned (no live
                       provider calls were made).  All facilities, alerts and
                       route values carry source="demo-*" identifiers.
                       Never present demo results as live travel conditions.
    """

    mode: Literal["live", "partial", "degraded", "demo"]
    sources: List[SourceMeta] = Field(default_factory=list)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
