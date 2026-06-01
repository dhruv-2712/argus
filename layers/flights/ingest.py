"""OpenSky Network live ADS-B aircraft state ingest.

Free, no authentication required (anonymous rate limit: 10 req/10s).
Docs: https://openskynetwork.github.io/opensky-api/rest.html
"""

import logging
from datetime import datetime, timezone

import aiohttp

from core.models import AOI

logger = logging.getLogger(__name__)

_URL = "https://opensky-network.org/api/states/all"


async def fetch_flights(aoi: AOI) -> dict:
    min_lon, min_lat, max_lon, max_lat = aoi.bbox
    params = {
        "lamin": min_lat, "lomin": min_lon,
        "lamax": max_lat, "lomax": max_lon,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _URL, params=params,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"Accept": "application/json"},
            ) as resp:
                if resp.status == 429:
                    return {"error": "OpenSky rate limited", "aircraft": []}
                if resp.status == 503:
                    return {"error": "OpenSky unavailable", "aircraft": []}
                if resp.status != 200:
                    return {"error": f"OpenSky HTTP {resp.status}", "aircraft": []}
                data = await resp.json()

        aircraft = _parse(data.get("states") or [])
        logger.info("OpenSky: %d aircraft for AOI %s", len(aircraft), aoi.id)
        return {"aircraft": aircraft, "fetched_at": datetime.now(timezone.utc).isoformat()}

    except Exception as exc:
        logger.warning("OpenSky fetch failed: %s", exc)
        return {"error": str(exc), "aircraft": []}


def _parse(states: list) -> list[dict]:
    aircraft = []
    for s in states:
        if len(s) < 17:
            continue
        lat, lon = s[6], s[5]
        if lat is None or lon is None:
            continue
        aircraft.append({
            "icao24": s[0] or "",
            "callsign": (s[1] or "").strip(),
            "origin_country": s[2] or "",
            "lat": float(lat),
            "lon": float(lon),
            "baro_altitude": float(s[7]) if s[7] is not None else 0.0,
            "geo_altitude": float(s[13]) if s[13] is not None else 0.0,
            "on_ground": bool(s[8]),
            "velocity": float(s[9]) if s[9] is not None else 0.0,   # m/s
            "heading": float(s[10]) if s[10] is not None else 0.0,
            "vertical_rate": float(s[11]) if s[11] is not None else 0.0,
            "squawk": s[14] or "",
        })
    return aircraft
