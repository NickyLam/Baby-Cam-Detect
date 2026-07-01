import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api import auth_router, cameras_router, events_router, notifications_router
from app.services.stream_ingestion import StreamManager

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    logger.info("Baby-Cam-Detect API starting up...")
    yield
    # Shutdown: stop all streams
    logger.info("Shutting down - stopping all streams...")
    stream_manager = StreamManager.get_instance()
    await stream_manager.stop_all()
    logger.info("All streams stopped. Goodbye!")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Baby safety monitoring via AI-powered video analysis",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(cameras_router, prefix=settings.api_prefix)
app.include_router(events_router, prefix=settings.api_prefix)
app.include_router(notifications_router, prefix=settings.api_prefix)


@app.get("/api/v1/health")
async def health_check():
    stream_manager = StreamManager.get_instance()
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": "0.1.0",
        "active_streams": stream_manager.active_count,
    }
