from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models import Camera
from app.schemas import CameraCreate, CameraUpdate, CameraResponse

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.post("/", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    data: CameraCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    camera = Camera(
        user_id=UUID(user_id),
        name=data.name,
        rtsp_url=data.rtsp_url,
        status="setup",
    )
    db.add(camera)
    await db.flush()
    await db.refresh(camera)
    return camera


@router.get("/", response_model=List[CameraResponse])
async def list_cameras(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Camera).where(Camera.user_id == UUID(user_id))
    )
    return result.scalars().all()


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id, Camera.user_id == UUID(user_id))
    )
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: UUID,
    data: CameraUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id, Camera.user_id == UUID(user_id))
    )
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if data.name is not None:
        camera.name = data.name
    if data.rtsp_url is not None:
        camera.rtsp_url = data.rtsp_url

    await db.flush()
    await db.refresh(camera)
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id, Camera.user_id == UUID(user_id))
    )
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    await db.delete(camera)


@router.post("/{camera_id}/start", response_model=CameraResponse)
async def start_monitoring(
    camera_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id, Camera.user_id == UUID(user_id))
    )
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Import here to avoid circular imports
    from app.services.stream_ingestion import StreamManager
    stream_manager = StreamManager.get_instance()
    await stream_manager.start_camera(camera)

    camera.status = "active"
    await db.flush()
    await db.refresh(camera)
    return camera


@router.post("/{camera_id}/stop", response_model=CameraResponse)
async def stop_monitoring(
    camera_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id, Camera.user_id == UUID(user_id))
    )
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    from app.services.stream_ingestion import StreamManager
    stream_manager = StreamManager.get_instance()
    await stream_manager.stop_camera(str(camera.id))

    camera.status = "paused"
    await db.flush()
    await db.refresh(camera)
    return camera
