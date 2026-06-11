"""FastAPI application entry point for ARGUS."""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from api.routes import aoi, contacts, intel, monitor, reports, ws
from core.models import AOI
from db.database import AOIRow, FusedContactRow, async_session, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


_SEED_AOIS = [
    {"name": "Galwan Valley",           "bbox": [79.8, 34.2, 80.6, 34.8], "domain": "land"},
    {"name": "Kashmir LoC",             "bbox": [73.8, 33.5, 74.8, 34.5], "domain": "land"},
    {"name": "Siachen Glacier",         "bbox": [76.5, 35.2, 77.5, 36.0], "domain": "land", "terrain_type": "glacial"},
    {"name": "Spratly Islands",         "bbox": [113.5,  9.5, 115.5, 11.5], "domain": "maritime"},
    {"name": "Taiwan Strait",           "bbox": [119.5, 23.0, 122.0, 26.0], "domain": "maritime"},
    {"name": "Strait of Hormuz",        "bbox": [ 56.0, 25.5,  57.5, 27.0], "domain": "maritime"},
    {"name": "Korean DMZ",              "bbox": [126.5, 37.5, 129.0, 38.5], "domain": "land"},
    {"name": "Donbas Front",            "bbox": [ 37.0, 47.5,  39.5, 49.0], "domain": "land"},
    {"name": "Gaza Strip",              "bbox": [ 34.2, 31.2,  34.6, 31.6], "domain": "land"},
    {"name": "Gulf of Aden",            "bbox": [ 44.0, 11.0,  51.0, 15.0], "domain": "maritime"},
    {"name": "Java Volcanic Arc",       "bbox": [109.5, -8.0, 111.0, -7.0], "domain": "land", "terrain_type": "volcanic"},
    {"name": "Eastern DRC",             "bbox": [ 28.5, -3.0,  30.0, -1.0], "domain": "land"},
    {"name": "Red Sea — Bab el-Mandeb", "bbox": [ 42.5, 12.0,  44.0, 14.0], "domain": "maritime"},
    {"name": "Sudan — Khartoum",        "bbox": [ 32.0, 15.0,  33.5, 16.0], "domain": "land"},
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
                terrain_type=spec.get("terrain_type"),
                active=True,
                created_at=now,
                revisit_hours=24,
            ))
        await session.commit()
        logger.info("Seeded %d demo AOIs", len(_SEED_AOIS))


_scheduler = AsyncIOScheduler(timezone="UTC")


async def _autonomous_scan() -> None:
    """Hourly watchdog: scan every active AOI that is overdue per revisit_hours."""
    from api.routes.ws import broadcast
    from api.scanner import ScanOrchestrator

    async with async_session() as session:
        result = await session.execute(select(AOIRow).where(AOIRow.active == True))
        rows = list(result.scalars().all())

    if not rows:
        return

    now = datetime.now(timezone.utc)
    overdue: list[AOIRow] = []

    for row in rows:
        async with async_session() as session:
            last_ts = await session.scalar(
                select(func.max(FusedContactRow.timestamp))
                .where(FusedContactRow.aoi_id == row.id)
            )
        if last_ts is None:
            overdue.append(row)
            continue
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        if (now - last_ts).total_seconds() / 3600 >= row.revisit_hours:
            overdue.append(row)

    if not overdue:
        logger.debug("Auto-scan: all AOIs within revisit window")
        return

    logger.info("Auto-scan: %d AOI(s) overdue", len(overdue))
    orch = ScanOrchestrator()

    for row in overdue:
        aoi = AOI(
            id=row.id, name=row.name,
            bbox=(row.min_lon, row.min_lat, row.max_lon, row.max_lat),
            domain=row.domain, terrain_type=row.terrain_type,
            active=row.active, created_at=row.created_at,
            revisit_hours=row.revisit_hours,
        )
        try:
            result = await orch.scan(aoi)
            fused = result["fused_contacts"]
            await broadcast({
                "type": "auto_scan_complete",
                "aoi_id": aoi.id,
                "aoi_name": aoi.name,
                "fused_count": len(fused),
                "max_threat": max(
                    (fc.threat_level for fc in fused),
                    key=lambda t: {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(t, 0),
                    default="low",
                ) if fused else "low",
                "has_critical": any(fc.threat_level == "critical" for fc in fused),
            })
            logger.info("Auto-scan complete: %s — %d contacts", aoi.name, len(fused))
        except Exception as exc:
            logger.error("Auto-scan failed for %s: %s", aoi.name, exc)


_ENABLE_AUTOSCAN = os.getenv("ENABLE_AUTOSCAN", "").strip().lower() in ("1", "true", "yes")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize DB, seed AOIs, and (optionally) start the scan scheduler."""
    await init_db()
    await _seed_demo_aoi()
    # The autonomous hourly scan is OFF by default: on a public free-tier
    # deploy it would otherwise re-scan every seeded AOI around the clock with
    # zero users, burning external API quota. Enable with ENABLE_AUTOSCAN=true
    # when running a dedicated instance.
    if _ENABLE_AUTOSCAN:
        _scheduler.add_job(
            _autonomous_scan, "interval", hours=1,
            id="auto_scan", coalesce=True, max_instances=1, replace_existing=True,
        )
        _scheduler.start()
        logger.info("ARGUS API started — autonomous scan scheduler ACTIVE (1h interval)")
    else:
        logger.info("ARGUS API started — autonomous scan DISABLED (set ENABLE_AUTOSCAN=true to enable)")
    # Start Redis subscriber for multi-worker WebSocket fan-out (no-op if
    # REDIS_URL unset). Keep a reference so the task can't be GC'd mid-flight.
    from api.routes.ws import start_redis_subscriber
    redis_task = asyncio.create_task(start_redis_subscriber())
    yield
    redis_task.cancel()
    if _ENABLE_AUTOSCAN and _scheduler.running:
        _scheduler.shutdown(wait=False)
    logger.info("ARGUS API shutting down")


app = FastAPI(
    title="ARGUS",
    description="Multi-source geospatial intelligence fusion platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Lock CORS to known origins in production via ALLOWED_ORIGINS (comma-separated).
# Falls back to permissive "*" for local dev — but with credentials disabled,
# so it's the spec-valid form (no cookies are used; only the X-Device-ID header).
_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
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
