from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.api.deps import get_current_user, get_settings
from supabase import create_client, Client

router = APIRouter(prefix="/saved-journeys", tags=["saved-journeys"])


class SaveJourneyRequest(BaseModel):
    origin: str
    destination: str
    distance_km: Optional[float] = None
    duration_minutes: Optional[float] = None
    risk_level: Optional[str] = None
    data_status_mode: Optional[str] = None
    journey_json: dict
    params_json: Optional[dict] = None


class SavedJourneyResponse(BaseModel):
    id: str
    origin: str
    destination: str
    distance_km: Optional[float]
    duration_minutes: Optional[float]
    risk_level: Optional[str]
    data_status_mode: Optional[str]
    created_at: datetime


class SavedJourneyDetail(BaseModel):
    id: str
    origin: str
    destination: str
    distance_km: Optional[float]
    duration_minutes: Optional[float]
    risk_level: Optional[str]
    data_status_mode: Optional[str]
    journey_json: dict
    params_json: Optional[dict]
    created_at: datetime
    updated_at: datetime


def _sb(settings) -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


@router.post("", response_model=SavedJourneyResponse, status_code=status.HTTP_201_CREATED)
async def save_journey(
    req: SaveJourneyRequest,
    user_id: str = Depends(get_current_user),
    settings=Depends(get_settings),
):
    sb = _sb(settings)
    res = sb.table("saved_journeys").insert({
        "user_id": user_id,
        "origin": req.origin,
        "destination": req.destination,
        "distance_km": req.distance_km,
        "duration_minutes": req.duration_minutes,
        "risk_level": req.risk_level,
        "data_status_mode": req.data_status_mode,
        "journey_json": req.journey_json,
        "params_json": req.params_json,
    }).execute()
    if not res.data:
        raise HTTPException(500, "Failed to save journey")
    return res.data[0]


@router.get("", response_model=List[SavedJourneyResponse])
async def list_journeys(
    user_id: str = Depends(get_current_user),
    settings=Depends(get_settings),
):
    sb = _sb(settings)
    res = sb.table("saved_journeys").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return res.data


@router.delete("/{journey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_journey(
    journey_id: str,
    user_id: str = Depends(get_current_user),
    settings=Depends(get_settings),
):
    sb = _sb(settings)
    sb.table("saved_journeys").delete().eq("id", journey_id).eq("user_id", user_id).execute()


@router.get("/{journey_id}", response_model=SavedJourneyDetail)
async def get_journey(
    journey_id: str,
    user_id: str = Depends(get_current_user),
    settings=Depends(get_settings),
):
    sb = _sb(settings)
    res = (
        sb.table("saved_journeys")
        .select("*")
        .eq("id", journey_id)
        .eq("user_id", user_id)
        # .single() makes postgrest-py raise APIError (surfaced to the client
        # as an opaque 500 by the global exception handler) whenever zero
        # rows match — which is exactly what happens for a deleted journey,
        # a mistyped id, or (by design) another user's journey_id, since the
        # .eq("user_id", ...) filter above excludes it. .maybe_single() runs
        # the identical query but returns None on zero rows instead of
        # raising, which is what the "if not res.data: 404" line below
        # actually needs to be reachable.
        .maybe_single()
        .execute()
    )
    if not res or not res.data:
        raise HTTPException(404, "Not found")
    return res.data