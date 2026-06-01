"""FastAPI application entry point for ARGUS."""

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from api.routes import aoi, contacts, intel, monitor, reports
from db.database import AOIRow, async_session, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def _seed_demo_aoi() -> None:
    async with async_session() as session:
        count = await session.scalar(select(func.count()).select_from(AOIRow))
        if count and count > 0:
            return
        galwan = AOIRow(
            id=str(uuid.uuid4()),
            name="Galwan Valley",
            min_lon=79.8,
            min_lat=34.2,
            max_lon=80.6,
            max_lat=34.8,
            domain="land",
            active=True,
            created_at=datetime.now(timezone.utc),
            revisit_hours=24,
        )
        session.add(galwan)
        await session.commit()
        logger.info("Seeded demo AOI: Galwan Valley")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize the database on startup."""
    await init_db()
    await _seed_demo_aoi()
    logger.info("ARGUS API started")
    yield
    logger.info("ARGUS API shutting down")


app = FastAPI(
    title="ARGUS",
    description="Multi-source geospatial intelligence fusion platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(aoi.router)
app.include_router(contacts.router)
app.include_router(monitor.router)
app.include_router(reports.router)
app.include_router(intel.router)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
