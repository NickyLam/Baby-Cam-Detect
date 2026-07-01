from datetime import datetime, timedelta, timezone
from uuid import UUID
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models import Event, Camera
from app.schemas import EventResponse, EventSummary

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=List[EventResponse])
async def list_events(
    camera_id: Optional[UUID] = None,
    event_type: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # Get user's camera IDs
    camera_result = await db.execute(
        select(Camera.id).where(Camera.user_id == UUID(user_id))
    )
    user_camera_ids = [row[0] for row in camera_result.fetchall()]

    if not user_camera_ids:
        return []

    query = select(Event).where(Event.camera_id.in_(user_camera_ids))

    if camera_id:
        if camera_id not in user_camera_ids:
            raise HTTPException(status_code=403, detail="Not your camera")
        query = query.where(Event.camera_id == camera_id)

    if event_type:
        query = query.where(Event.event_type == event_type)

    query = query.order_by(Event.detected_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/summary", response_model=EventSummary)
async def get_event_summary(
    days: int = Query(default=7, ge=1, le=30),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    period_start = datetime.now(timezone.utc) - timedelta(days=days)
    period_end = datetime.now(timezone.utc)

    # Get user's camera IDs
    camera_result = await db.execute(
        select(Camera.id).where(Camera.user_id == UUID(user_id))
    )
    user_camera_ids = [row[0] for row in camera_result.fetchall()]

    if not user_camera_ids:
        return EventSummary(
            total_events=0, face_down_count=0, blanket_over_face_count=0,
            dismissed_count=0, period_start=period_start, period_end=period_end,
        )

    base_filter = and_(
        Event.camera_id.in_(user_camera_ids),
        Event.detected_at >= period_start,
    )

    # Total events
    total_result = await db.execute(
        select(func.count(Event.id)).where(base_filter)
    )
    total = total_result.scalar() or 0

    # By type
    face_down_result = await db.execute(
        select(func.count(Event.id)).where(base_filter, Event.event_type == "face_down")
    )
    face_down = face_down_result.scalar() or 0

    blanket_result = await db.execute(
        select(func.count(Event.id)).where(base_filter, Event.event_type == "blanket_over_face")
    )
    blanket = blanket_result.scalar() or 0

    dismissed_result = await db.execute(
        select(func.count(Event.id)).where(base_filter, Event.dismissed == True)
    )
    dismissed = dismissed_result.scalar() or 0

    return EventSummary(
        total_events=total,
        face_down_count=face_down,
        blanket_over_face_count=blanket,
        dismissed_count=dismissed,
        period_start=period_start,
        period_end=period_end,
    )


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Verify ownership
    camera_result = await db.execute(
        select(Camera).where(Camera.id == event.camera_id, Camera.user_id == UUID(user_id))
    )
    if not camera_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Access denied")

    return event


@router.post("/{event_id}/dismiss", response_model=EventResponse)
async def dismiss_event(
    event_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Verify ownership
    camera_result = await db.execute(
        select(Camera).where(Camera.id == event.camera_id, Camera.user_id == UUID(user_id))
    )
    if not camera_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Access denied")

    event.dismissed = True
    event.dismissed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(event)
    return event
