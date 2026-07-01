from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models import DeviceToken, NotificationPreference
from app.schemas import DeviceTokenCreate, NotificationPreferenceUpdate, NotificationPreferenceResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/devices", status_code=status.HTTP_201_CREATED)
async def register_device(
    data: DeviceTokenCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # Check if token already exists
    result = await db.execute(
        select(DeviceToken).where(DeviceToken.push_token == data.push_token)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.user_id = UUID(user_id)
        existing.is_active = True
        existing.platform = data.platform
    else:
        device = DeviceToken(
            user_id=UUID(user_id),
            push_token=data.push_token,
            platform=data.platform,
        )
        db.add(device)

    return {"status": "registered"}


@router.delete("/devices/{push_token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(
    push_token: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DeviceToken).where(
            DeviceToken.push_token == push_token,
            DeviceToken.user_id == UUID(user_id),
        )
    )
    device = result.scalar_one_or_none()
    if device:
        device.is_active = False


@router.get("/preferences", response_model=NotificationPreferenceResponse)
async def get_preferences(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == UUID(user_id)
        )
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        # Create defaults
        prefs = NotificationPreference(user_id=UUID(user_id))
        db.add(prefs)
        await db.flush()
        await db.refresh(prefs)
    return prefs


@router.put("/preferences", response_model=NotificationPreferenceResponse)
async def update_preferences(
    data: NotificationPreferenceUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == UUID(user_id)
        )
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        prefs = NotificationPreference(user_id=UUID(user_id))
        db.add(prefs)
        await db.flush()

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prefs, field, value)

    await db.flush()
    await db.refresh(prefs)
    return prefs
