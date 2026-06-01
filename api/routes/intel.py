"""Cross-AOI regional intelligence — correlates activity across all areas.

Individual AOIs answer "what is happening here." This board answers the
higher-order question: "is something coordinated happening across the
theater?" — by surveying every active AOI's latest posture and flagging
simultaneous escalation.
"""

import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from sqlalchemy import select

from db.database import AOIRow, FusedContactRow, async_session

router = APIRouter(prefix="/intel", tags=["intel"])

logger = logging.getLogger(__name__)

# In-memory TTL cache for terrain geometry (the elevation API is slow and
# the same contact is inspected repeatedly).
_TERRAIN_CACHE: dict[str, tuple[float, dict]] = {}
_TERRAIN_TTL = 3600.0

_THREAT_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def _posture(max_rank: int, escalating: int) -> str:
    """Single-AOI posture label."""
    if max_rank >= 3 or escalating >= 2:
        return "ALERT"
    if max_rank == 2 or escalating == 1:
        return "ELEVATED"
    if max_rank == 1:
        return "WATCH"
    return "QUIET"


@router.get("/regional")
async def regional_board() -> dict:
    """Theater-wide threat board with coordinated-escalation detection."""
    async with async_session() as session:
        aoi_rows = (await session.execute(select(AOIRow))).scalars().all()

        board: list[dict] = []
        for aoi in aoi_rows:
            result = await session.execute(
                select(FusedContactRow)
                .where(FusedContactRow.aoi_id == aoi.id)
                .order_by(FusedContactRow.timestamp.desc())
                .limit(200)
            )
            rows = result.scalars().all()

            # Keep only the latest observation per track for current posture.
            latest: dict[str, FusedContactRow] = {}
            for r in rows:
                key = r.track_id or r.id
                if key not in latest:
                    latest[key] = r

            tracks = list(latest.values())
            counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            escalating = 0
            max_rank = -1
            for t in tracks:
                counts[t.threat_level] = counts.get(t.threat_level, 0) + 1
                max_rank = max(max_rank, _THREAT_RANK.get(t.threat_level, 0))
                if (t.lifecycle or "new") == "escalating":
                    escalating += 1

            last_scan = max((r.timestamp for r in rows), default=None)
            board.append({
                "aoi_id": aoi.id,
                "name": aoi.name,
                "active": aoi.active,
                "posture": _posture(max_rank, escalating) if tracks else "QUIET",
                "active_tracks": len(tracks),
                "threat_counts": counts,
                "escalating_tracks": escalating,
                "last_scan": last_scan.isoformat() if last_scan else None,
            })

    # Coordinated-escalation heuristic across the theater.
    alert_areas = [b for b in board if b["posture"] == "ALERT"]
    escalating_areas = [b for b in board if b["escalating_tracks"] > 0]
    total_escalating = sum(b["escalating_tracks"] for b in board)

    if len(alert_areas) >= 2:
        regional = "REGIONAL ESCALATION — multiple areas at ALERT posture"
    elif len(escalating_areas) >= 2:
        regional = "COORDINATED ACTIVITY — escalation detected across multiple areas"
    elif alert_areas:
        regional = "LOCALIZED ALERT — single area at ALERT posture"
    else:
        regional = "NOMINAL — no coordinated escalation detected"

    board.sort(key=lambda b: (-_posture_rank(b["posture"]), -b["escalating_tracks"]))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regional_assessment": regional,
        "areas_total": len(board),
        "areas_alert": len(alert_areas),
        "areas_escalating": len(escalating_areas),
        "total_escalating_tracks": total_escalating,
        "board": board,
    }


def _posture_rank(posture: str) -> int:
    return {"ALERT": 3, "ELEVATED": 2, "WATCH": 1, "QUIET": 0}.get(posture, 0)


@router.get("/aoi/{aoi_id}/tracks")
async def aoi_tracks(aoi_id: str) -> dict:
    """Per-track history for one AOI: how each target has evolved over time."""
    async with async_session() as session:
        result = await session.execute(
            select(FusedContactRow)
            .where(FusedContactRow.aoi_id == aoi_id)
            .order_by(FusedContactRow.timestamp.asc())
        )
        rows = result.scalars().all()

    tracks: dict[str, dict] = {}
    for r in rows:
        key = r.track_id or r.id
        t = tracks.setdefault(key, {
            "track_id": key,
            "lat": r.lat, "lon": r.lon,
            "first_seen": r.first_seen.isoformat() if r.first_seen else (r.timestamp.isoformat() if r.timestamp else None),
            "observations": [],
        })
        t["lat"], t["lon"] = r.lat, r.lon
        t["last_seen"] = r.timestamp.isoformat() if r.timestamp else None
        t["latest_threat"] = r.threat_level
        t["latest_lifecycle"] = r.lifecycle or "new"
        t["observation_count"] = r.observation_count or len(t["observations"]) + 1
        t["observations"].append({
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "confidence": r.confidence,
            "threat_level": r.threat_level,
            "lifecycle": r.lifecycle or "new",
            "sources": json.loads(r.sources),
        })

    ordered = sorted(
        tracks.values(),
        key=lambda t: (_THREAT_RANK.get(t.get("latest_threat", "low"), 0), t.get("observation_count", 0)),
        reverse=True,
    )
    return {"aoi_id": aoi_id, "track_count": len(ordered), "tracks": ordered}


@router.get("/terrain")
async def terrain_geometry(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> dict:
    """Terrain-derived tactical geometry for a point: key terrain, avenues of
    approach, observation radius — computed from real elevation samples.

    Used by the map overlay to draw militarily grounded geometry. Cached so
    repeated inspection of a contact is instant.
    """
    key = f"{round(lat, 3)}:{round(lon, 3)}"
    now = time.time()
    cached = _TERRAIN_CACHE.get(key)
    if cached and now - cached[0] < _TERRAIN_TTL:
        return cached[1]

    # Imported lazily to avoid pulling LangGraph/Groq into the request path
    # unless terrain is actually requested.
    from core.simulation.ocoka import _fetch_elevations

    terrain = await _fetch_elevations(lat, lon)
    geometry = terrain.get("tactical_geometry") if isinstance(terrain, dict) else None
    payload = {
        "lat": lat,
        "lon": lon,
        "available": geometry is not None,
        "tactical_geometry": geometry,
        "terrain_type": terrain.get("terrain_type") if isinstance(terrain, dict) else None,
        "error": terrain.get("error") if isinstance(terrain, dict) else "unavailable",
    }
    if geometry:
        _TERRAIN_CACHE[key] = (now, payload)
    return payload
