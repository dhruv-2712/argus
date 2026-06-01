"""NASA FIRMS VIIRS/MODIS thermal anomaly ingest.

Free MAP_KEY obtained from https://firms.modaps.eosdis.nasa.gov/api/map_key/
Set FIRMS_MAP_KEY env var.  Falls back gracefully when absent (layer skipped).
"""

import csv
import io
import logging
import os

import aiohttp

from core.models import AOI

logger = logging.getLogger(__name__)

_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
_SOURCE = "VIIRS_SNPP_NRT"
_DAYS = 2  # look-back window


async def fetch_thermal(aoi: AOI) -> dict:
    api_key = os.getenv("FIRMS_MAP_KEY", "").strip()
    if not api_key:
        logger.debug("FIRMS_MAP_KEY not set — thermal layer skipped")
        return {"skipped": True, "reason": "no_api_key", "hotspots": []}

    min_lon, min_lat, max_lon, max_lat = aoi.bbox
    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    url = f"{_BASE}/{api_key}/{_SOURCE}/{bbox_str}/{_DAYS}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status == 401:
                    logger.warning("FIRMS: invalid API key")
                    return {"skipped": True, "reason": "invalid_api_key", "hotspots": []}
                if resp.status != 200:
                    return {"error": f"FIRMS HTTP {resp.status}", "hotspots": []}
                text = await resp.text()

        hotspots = _parse_csv(text)
        logger.info("FIRMS: %d thermal anomalies for AOI %s", len(hotspots), aoi.id)
        return {"hotspots": hotspots}

    except Exception as exc:
        logger.warning("FIRMS fetch failed: %s", exc)
        return {"error": str(exc), "hotspots": []}


def _parse_csv(text: str) -> list[dict]:
    hotspots: list[dict] = []
    try:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                hotspots.append({
                    "lat": float(row["latitude"]),
                    "lon": float(row["longitude"]),
                    "bright_ti4": float(row.get("bright_ti4") or 0),
                    "frp": float(row.get("frp") or 0),
                    "confidence": str(row.get("confidence", "nominal")).lower(),
                    "daynight": str(row.get("daynight", "D")),
                    "acq_date": row.get("acq_date", ""),
                    "acq_time": row.get("acq_time", ""),
                })
            except (ValueError, KeyError):
                continue
    except Exception:
        pass
    return hotspots
