"""Start/stop monitoring and trigger scans for an AOI."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_orchestrator, get_specter
from api.ratelimit import SCAN_SEMAPHORE, rate_limit
from api.scanner import ScanOrchestrator
from core.fusion.summary import build_scan_summary, polish_summary_llm
from core.models import AOI, FusedContact
from core.simulation.ocoka import Specter
from db.database import AOIRow, FusedContactRow, async_session

router = APIRouter(prefix="/aoi", tags=["monitor"])


class ScanRequest(BaseModel):
    """Optional layer filter for scan requests."""
    layers: list[str] | None = None


def _row_to_aoi(row: AOIRow) -> AOI:
    """Convert DB row to AOI model."""
    return AOI(
        id=row.id,
        name=row.name,
        bbox=(row.min_lon, row.min_lat, row.max_lon, row.max_lat),
        domain=row.domain,
        terrain_type=row.terrain_type,
        active=row.active,
        created_at=row.created_at,
        revisit_hours=row.revisit_hours,
    )


async def _get_aoi_row(aoi_id: str) -> AOIRow:
    """Fetch AOI row or raise 404."""
    async with async_session() as session:
        row = await session.get(AOIRow, aoi_id)
    if not row:
        raise HTTPException(status_code=404, detail="AOI not found")
    return row


@router.post("/{aoi_id}/scan", dependencies=[Depends(rate_limit("scan", 15.0))])
async def scan_aoi(
    aoi_id: str,
    body: ScanRequest | None = None,
    orchestrator: ScanOrchestrator = Depends(get_orchestrator),
) -> dict:
    """Trigger an immediate full scan for this AOI."""
    row = await _get_aoi_row(aoi_id)
    aoi = _row_to_aoi(row)

    # Cap concurrent scans worker-wide so one client can't thrash the instance.
    try:
        await asyncio.wait_for(SCAN_SEMAPHORE.acquire(), timeout=0.5)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Scanner is busy with another request — try again in a moment.",
        )
    try:
        layers = body.layers if body else None
        result = await orchestrator.scan(aoi, layers=layers)
    finally:
        SCAN_SEMAPHORE.release()

    fused = result["fused_contacts"]
    if not fused and result["raw_contact_count"] == 0 and len(result["layer_errors"]) == len(result["layers_run"]):
        raise HTTPException(
            status_code=503,
            detail={"scan_failed": True, "errors": result["layer_errors"]},
        )

    # Plain-language summary of what this scan did and found. The deterministic
    # backbone is instant; the Groq pass (best-effort) rewrites it into simpler
    # English and falls back silently if the key is missing or the call fails.
    summary = build_scan_summary(aoi, result)
    summary["narrative"] = await polish_summary_llm(summary["narrative"])

    # Push a live event to all connected operators.
    from api.routes.ws import broadcast
    await broadcast({
        "type": "scan_complete",
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

    return {
        "aoi_id": aoi.id,
        "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        "fused_contacts": [fc.model_dump() for fc in fused],
        "raw_contact_count": result["raw_contact_count"],
        "layer_errors": result["layer_errors"],
        "layers_run": result["layers_run"],
        "summary": summary,
    }


@router.post("/{aoi_id}/monitor/start")
async def start_monitoring(aoi_id: str) -> dict:
    """Set AOI active=True to enable monitoring."""
    async with async_session() as session:
        row = await session.get(AOIRow, aoi_id)
        if not row:
            raise HTTPException(status_code=404, detail="AOI not found")
        row.active = True
        await session.commit()
        await session.refresh(row)
        return {
            "id": row.id, "name": row.name, "active": row.active,
            "bbox": [row.min_lon, row.min_lat, row.max_lon, row.max_lat],
            "domain": row.domain, "revisit_hours": row.revisit_hours,
        }


@router.post("/{aoi_id}/monitor/stop")
async def stop_monitoring(aoi_id: str) -> dict:
    """Set AOI active=False to stop monitoring."""
    async with async_session() as session:
        row = await session.get(AOIRow, aoi_id)
        if not row:
            raise HTTPException(status_code=404, detail="AOI not found")
        row.active = False
        await session.commit()
        await session.refresh(row)
        return {
            "id": row.id, "name": row.name, "active": row.active,
            "bbox": [row.min_lon, row.min_lat, row.max_lon, row.max_lat],
            "domain": row.domain, "revisit_hours": row.revisit_hours,
        }


@router.get("/{aoi_id}/status")
async def aoi_status(aoi_id: str) -> dict:
    """Get monitoring status and contact counts for an AOI."""
    row = await _get_aoi_row(aoi_id)

    async with async_session() as session:
        total_q = await session.execute(
            select(func.count()).where(FusedContactRow.aoi_id == aoi_id)
        )
        total = total_q.scalar() or 0

        threat_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for level in threat_counts:
            q = await session.execute(
                select(func.count()).where(
                    FusedContactRow.aoi_id == aoi_id,
                    FusedContactRow.threat_level == level,
                )
            )
            threat_counts[level] = q.scalar() or 0

        last_q = await session.execute(
            select(FusedContactRow.timestamp)
            .where(FusedContactRow.aoi_id == aoi_id)
            .order_by(FusedContactRow.timestamp.desc())
            .limit(1)
        )
        last_scan_row = last_q.scalar()

    return {
        "aoi_id": row.id,
        "active": row.active,
        "last_scan": last_scan_row.isoformat() if last_scan_row else None,
        "total_contacts": total,
        "fused_contacts_by_threat": threat_counts,
    }


class SimulateRequest(BaseModel):
    """Request body for on-demand SPECTER simulation."""
    contact_id: str


@router.post("/{aoi_id}/simulate")
async def simulate_contact(
    aoi_id: str,
    body: SimulateRequest,
    specter: Specter = Depends(get_specter),
) -> dict:
    """Run SPECTER terrain analysis on a specific FusedContact."""
    row = await _get_aoi_row(aoi_id)
    aoi = _row_to_aoi(row)

    async with async_session() as session:
        fc_row = await session.get(FusedContactRow, body.contact_id)
    if not fc_row:
        raise HTTPException(status_code=404, detail="Contact not found")

    fc = FusedContact(
        id=fc_row.id,
        aoi_id=fc_row.aoi_id,
        constituent_contacts=json.loads(fc_row.constituent_contacts),
        sources=json.loads(fc_row.sources),
        confidence=fc_row.confidence,
        detection_types=json.loads(fc_row.detection_types),
        lat=fc_row.lat,
        lon=fc_row.lon,
        timestamp=fc_row.timestamp,
        threat_level=fc_row.threat_level,
        summary=fc_row.summary,
        simulation_run=fc_row.simulation_run,
    )

    result = await specter.analyze(aoi, fc)
    if result is None:
        raise HTTPException(
            status_code=422,
            detail=f"Contact confidence {fc.confidence:.2f} below SPECTER threshold",
        )

    # Mark as simulated in DB
    async with async_session() as session:
        fc_row_update = await session.get(FusedContactRow, body.contact_id)
        if fc_row_update:
            fc_row_update.simulation_run = True
            await session.commit()

    return {
        "contact_id": fc.id,
        "aoi_id": aoi_id,
        "terrain_data": result["terrain_data"],
        "ocoka_analysis": result["ocoka_analysis"],
        "threat_assessment": result["threat_assessment"],
        "final_report": result["final_report"],
    }
