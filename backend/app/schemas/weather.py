from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import Coordinates, DataStatus


class WeatherObservation(BaseModel):
    location: Coordinates
    observation_time: Optional[datetime] = Field(
        None, description="Time the provider's data point refers to (UTC)"
    )
    temperature_c: Optional[float] = None
    windspeed_kmh: Optional[float] = None
    winddirection_deg: Optional[float] = None
    weather_code: Optional[int] = Field(
        None, description="Provider weather code, see provider docs"
    )
    is_day: Optional[bool] = None
    source: str


class WeatherResponse(BaseModel):
    observation: Optional[WeatherObservation] = None
    data_status: DataStatus
