from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Coordinates, DataStatus

AlertSeverity = Literal["low", "moderate", "high", "unknown"]


class Alert(BaseModel):
    id: Optional[str] = None
    description: str
    category: Optional[str] = None
    severity: AlertSeverity = "unknown"
    location: Optional[Coordinates] = None
    source: str
    retrieved_at: Optional[datetime] = None
    verified: Optional[bool] = Field(
        None,
        description="Whether the source itself marks this report as verified. Null if unknown.",
    )
    relevance: Optional[str] = Field(
        None,
        description="Short explanation of why this alert is considered relevant to the route",
    )


class AlertSearchResponse(BaseModel):
    query: Coordinates
    alerts: List[Alert] = Field(default_factory=list)
    data_status: DataStatus
