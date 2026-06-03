"""AOI CRUD endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, or_, select

from core.models import AOI
from db.database import AOIRow, ContactRow, FusedContactRow, async_session

router = APIRouter(prefix="/aoi", tags=["aoi"])


class AOICreate(BaseModel):
    """Request body for creating an AOI."""
    name: str
    bbox: list[float]
    domain: str
    revisit_hours: int = 24

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: list[float]) -> list[float]:
        if len(v) != 4:
            raise ValueError("bbox must have exactly 4 values")
        min_lon, min_lat, max_lon, max_lat = v
        if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
            raise ValueError("longitude must be between -180 and 180")
        if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
            raise ValueError("latitude must be between -90 and 90")
        if min_lon >= max_lon or min_lat >= max_lat:
            raise ValueError("min values must be less than max values")
        # Cap area so a user can't request a hemisphere-sized raster that would
        # OOM/timeout the free instance. 5° per side is generous for any AOI.
        if (max_lon - min_lon) > 5 or (max_lat - min_lat) > 5:
            raise ValueError("AOI too large — each side must span at most 5 degrees")
        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        if v not in ("land", "maritime", "mixed"):
            raise ValueError("domain must be land, maritime, or mixed")
        return v


class AOIUpdate(BaseModel):
    """Request body for updating an AOI."""
    name: str | None = None
    active: bool | None = None
    revisit_hours: int | None = None


def _row_to_dict(row: AOIRow) -> dict:
    """Convert an AOI DB row to a response dict."""
    return {
        "id": row.id,
        "name": row.name,
        "bbox": [row.min_lon, row.min_lat, row.max_lon, row.max_lat],
        "domain": row.domain,
        "terrain_type": row.terrain_type,
        "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "revisit_hours": row.revisit_hours,
        "owned": row.device_id is not None,
    }


@router.post("")
async def create_aoi(
    body: AOICreate,
    x_device_id: str | None = Header(default=None),
) -> dict:
    """Create a new AOI scoped to the requesting device."""
    # A missing device id would otherwise store device_id=NULL, which the
    # listing treats as a global "system" AOI visible to everyone and which
    # cannot be deleted. Require the header so only the browser client (which
    # always sends it) can create AOIs, and they stay device-scoped.
    if not x_device_id or not x_device_id.strip():
        raise HTTPException(status_code=400, detail="Missing device identifier")
    row = AOIRow(
        id=str(uuid.uuid4()),
        name=body.name,
        min_lon=body.bbox[0],
        min_lat=body.bbox[1],
        max_lon=body.bbox[2],
        max_lat=body.bbox[3],
        domain=body.domain,
        device_id=x_device_id,
        active=True,
        created_at=datetime.now(timezone.utc),
        revisit_hours=body.revisit_hours,
    )
    async with async_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return _row_to_dict(row)


@router.get("")
async def list_aois(
    x_device_id: str | None = Header(default=None),
) -> list[dict]:
    """List system AOIs plus this device's own AOIs."""
    async with async_session() as session:
        result = await session.execute(
            select(AOIRow).where(
                or_(AOIRow.device_id.is_(None), AOIRow.device_id == x_device_id)
            )
        )
        rows = result.scalars().all()
    return [_row_to_dict(r) for r in rows]


@router.get("/{aoi_id}")
async def get_aoi(aoi_id: str) -> dict:
    """Get a single AOI by id."""
    async with async_session() as session:
        row = await session.get(AOIRow, aoi_id)
    if not row:
        raise HTTPException(status_code=404, detail="AOI not found")
    return _row_to_dict(row)


@router.patch("/{aoi_id}")
async def update_aoi(
    aoi_id: str,
    body: AOIUpdate,
    x_device_id: str | None = Header(default=None),
) -> dict:
    """Update AOI fields — only the owning device may modify user-created AOIs."""
    async with async_session() as session:
        row = await session.get(AOIRow, aoi_id)
        if not row:
            raise HTTPException(status_code=404, detail="AOI not found")
        # System (seeded) AOIs are shared — nobody may mutate them. User AOIs
        # may only be modified by their owning device.
        if row.device_id is None:
            raise HTTPException(status_code=403, detail="System AOIs are read-only")
        if row.device_id != x_device_id:
            raise HTTPException(status_code=403, detail="Not your AOI")
        if body.name is not None:
            row.name = body.name
        if body.active is not None:
            row.active = body.active
        if body.revisit_hours is not None:
            row.revisit_hours = body.revisit_hours
        await session.commit()
        await session.refresh(row)
    return _row_to_dict(row)


@router.delete("/{aoi_id}")
async def delete_aoi(
    aoi_id: str,
    x_device_id: str | None = Header(default=None),
) -> dict:
    """Hard-delete a user-created AOI and its contacts — owner only."""
    async with async_session() as session:
        row = await session.get(AOIRow, aoi_id)
        if not row:
            raise HTTPException(status_code=404, detail="AOI not found")
        if row.device_id is None:
            raise HTTPException(status_code=403, detail="System AOIs cannot be deleted")
        if row.device_id != x_device_id:
            raise HTTPException(status_code=403, detail="Not your AOI")
        # Remove the AOI and any contacts/fused records it produced.
        await session.execute(delete(ContactRow).where(ContactRow.aoi_id == aoi_id))
        await session.execute(delete(FusedContactRow).where(FusedContactRow.aoi_id == aoi_id))
        await session.delete(row)
        await session.commit()
    return {"deleted": aoi_id}
