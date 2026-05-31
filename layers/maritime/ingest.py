"""AIS vessel data ingestion via AISHub API."""

import asyncio
import logging
import os
from datetime import datetime, timezone

import aiohttp
from dotenv import load_dotenv

from core.models import AOI

load_dotenv()

logger = logging.getLogger(__name__)

AISHUB_URL = "https://data.aishub.net/ws.php"


async def _fetch_aishub(aoi: AOI, session: aiohttp.ClientSession) -> list[dict]:
    """Fetch vessel positions from AISHub within AOI bbox."""
    username = os.environ.get("AISHUB_USERNAME", "")
    if not username:
        raise RuntimeError("AISHUB_USERNAME not set in environment")

    min_lon, min_lat, max_lon, max_lat = aoi.bbox
    params = {
        "username": username,
        "format": 1,
        "output": "json",
        "latmin": min_lat,
        "latmax": max_lat,
        "lonmin": min_lon,
        "lonmax": max_lon,
    }

    async with session.get(
        AISHUB_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"AISHub returned HTTP {resp.status}")
        data = await resp.json(content_type=None)

    if not data or not isinstance(data, list):
        return []

    # AISHub returns [metadata_obj, [vessel_list]]
    if len(data) < 2 or not isinstance(data[1], list):
        return []

    vessels: list[dict] = []
    for v in data[1]:
        vessels.append({
            "mmsi": str(v.get("MMSI", "")),
            "vessel_name": v.get("NAME", "Unknown"),
            "vessel_type": int(v.get("TYPE", 0)),
            "lat": float(v.get("LATITUDE", 0)),
            "lon": float(v.get("LONGITUDE", 0)),
            "speed": float(v.get("SOG", 0)),
            "heading": float(v.get("HEADING", 0)),
            "timestamp": datetime.now(timezone.utc),
            "status": int(v.get("NAVSTAT", 0)),
            "track": [],
        })

    logger.info("AISHub returned %d vessels for AOI %s", len(vessels), aoi.id)
    return vessels


async def ingest(aoi: AOI) -> dict:
    """Fetch AIS vessel data for an AOI."""
    if aoi.domain == "land":
        return {"skipped": True, "reason": "land_aoi"}

    vessels: list[dict] = []
    error: str | None = None

    try:
        async with aiohttp.ClientSession() as session:
            vessels = await _fetch_aishub(aoi, session)
    except Exception as exc:
        error = str(exc)
        logger.warning("AIS fetch failed for AOI %s: %s", aoi.id, exc)

    return {
        "vessels": vessels,
        "fetch_timestamp": datetime.now(timezone.utc),
        "vessel_count": len(vessels),
        "error": error,
    }
