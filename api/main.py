"""FastAPI application entry point for ARGUS."""

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from api.routes import aoi, contacts, intel, monitor, reports, ws
from db.database import AOIRow, async_session, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


_SEED_AOIS = [
    {"name": "Galwan Valley",           "bbox": [79.8, 34.2, 80.6, 34.8], "domain": "land"},
    {"name": "Kashmir LoC",             "bbox": [73.8, 33.5, 74.8, 34.5], "domain": "land"},
    {"name": "Siachen Glacier",         "bbox": [76.5, 35.2, 77.5, 36.0], "domain": "land"},
    {"name": "Spratly Islands",         "bbox": [113.5,  9.5, 115.5, 11.5], "domain": "maritime"},
    {"name": "Taiwan Strait",           "bbox": [119.5, 23.0, 122.0, 26.0], "domain": "maritime"},
    {"name": "Strait of Hormuz",        "bbox": [ 56.0, 25.5,  57.5, 27.0], "domain": "maritime"},
    {"name": "Korean DMZ",              "bbox": [126.5, 37.5, 129.0, 38.5], "domain": "land"},
    {"name": "Donbas Front",            "bbox": [ 37.0, 47.5,  39.5, 49.0], "domain": "land"},
    {"name": "Gaza Strip",              "bbox": [ 34.2, 31.2,  34.6, 31.6], "domain": "land"},
    {"name": "Gulf of Aden",            "bbox": [ 44.0, 11.0,  51.0, 15.0], "domain": "maritime"},
]


async def _seed_demo_aoi() -> None:
    async with async_session() as session:
        count = await session.scalar(select(func.count()).select_from(AOIRow))
        if count and count > 0:
            return
        now = datetime.now(timezone.utc)
        for spec in _SEED_AOIS:
            b = spec["bbox"]
            session.add(AOIRow(
                id=str(uuid.uuid4()),
                name=spec["name"],
                min_lon=b[0], min_lat=b[1], max_lon=b[2], max_lat=b[3],
                domain=spec["domain"],
                active=True,
                created_at=now,
                revisit_hours=24,
            ))
        await session.commit()
        logger.info("Seeded %d demo AOIs", len(_SEED_AOIS))


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
app.include_router(ws.router)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
