"""Contact query endpoints."""

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import ContactRow, FusedContactRow, async_session

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _fused_row_to_dict(row: FusedContactRow) -> dict:
    """Convert a FusedContact DB row to a response dict."""
    return {
        "id": row.id,
        "aoi_id": row.aoi_id,
        "constituent_contacts": json.loads(row.constituent_contacts),
        "sources": json.loads(row.sources),
        "confidence": row.confidence,
        "detection_types": json.loads(row.detection_types),
        "lat": row.lat,
        "lon": row.lon,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "threat_level": row.threat_level,
        "summary": row.summary,
        "simulation_run": row.simulation_run,
        "track_id": row.track_id,
        "first_seen": row.first_seen.isoformat() if row.first_seen else None,
        "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        "observation_count": row.observation_count or 1,
        "lifecycle": row.lifecycle or "new",
        "confidence_delta": row.confidence_delta or 0.0,
        "persistence_score": row.persistence_score or 0.0,
    }


def _contact_row_to_dict(row: ContactRow) -> dict:
    """Convert a raw Contact DB row to a response dict."""
    return {
        "id": row.id,
        "aoi_id": row.aoi_id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "source": row.source,
        "confidence": row.confidence,
        "detection_type": row.detection_type,
        "lat": row.lat,
        "lon": row.lon,
        "description": row.description,
        "raw_evidence": json.loads(row.raw_evidence) if row.raw_evidence else {},
        "fused": row.fused,
        "threat_level": row.threat_level,
    }


@router.get("")
async def list_contacts(
    aoi_id: str | None = None,
    source: str | None = None,
    threat_level: str | None = None,
    detection_type: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    limit: int = Query(default=50, le=500),
) -> list[dict]:
    """Query fused contacts with optional filters."""
    stmt = select(FusedContactRow).order_by(FusedContactRow.timestamp.desc())

    if aoi_id:
        stmt = stmt.where(FusedContactRow.aoi_id == aoi_id)
    if threat_level:
        stmt = stmt.where(FusedContactRow.threat_level == threat_level)
    if after:
        stmt = stmt.where(FusedContactRow.timestamp >= after)
    if before:
        stmt = stmt.where(FusedContactRow.timestamp <= before)

    stmt = stmt.limit(limit)

    async with async_session() as session:
        result = await session.execute(stmt)
        rows = result.scalars().all()

    contacts = [_fused_row_to_dict(r) for r in rows]

    if source:
        contacts = [c for c in contacts if source in c["sources"]]
    if detection_type:
        contacts = [c for c in contacts if detection_type in c["detection_types"]]

    return contacts


@router.get("/{contact_id}")
async def get_contact(contact_id: str) -> dict:
    """Get a single FusedContact with its constituent raw contacts."""
    async with async_session() as session:
        row = await session.get(FusedContactRow, contact_id)
        if not row:
            raise HTTPException(status_code=404, detail="Contact not found")

        fused = _fused_row_to_dict(row)

        constituent_ids = json.loads(row.constituent_contacts)
        raw_rows = []
        for cid in constituent_ids:
            raw_row = await session.get(ContactRow, cid)
            if raw_row:
                raw_rows.append(raw_row)

    fused["raw_contacts"] = [_contact_row_to_dict(r) for r in raw_rows]
    return fused


@router.get("/{contact_id}/evidence")
async def get_evidence(contact_id: str) -> list[dict]:
    """Get raw_evidence from all constituent contacts of a FusedContact."""
    async with async_session() as session:
        row = await session.get(FusedContactRow, contact_id)
        if not row:
            raise HTTPException(status_code=404, detail="Contact not found")

        constituent_ids = json.loads(row.constituent_contacts)
        evidence: list[dict] = []
        for cid in constituent_ids:
            raw_row = await session.get(ContactRow, cid)
            if raw_row:
                ev = json.loads(raw_row.raw_evidence) if raw_row.raw_evidence else {}
                ev["contact_id"] = raw_row.id
                ev["source"] = raw_row.source
                ev["detection_type"] = raw_row.detection_type
                evidence.append(ev)

    return evidence
