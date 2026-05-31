"""GDELT + ACLED conflict event ingestion."""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import aiohttp
from dotenv import load_dotenv

from core.models import AOI

load_dotenv()

logger = logging.getLogger(__name__)

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
ACLED_BASE_URL = "https://api.acleddata.com/acled/read"
ACLED_RADIUS_KM = 150


async def _fetch_gdelt(
    aoi: AOI, session: aiohttp.ClientSession, date_range: dict | None = None
) -> list[dict]:
    """Fetch news articles from GDELT DOC API for the AOI region.

    The GDELT GEO API is unavailable, so we use the DOC API which returns
    articles with tone/source metadata. Articles are region-scoped by query
    and mapped to the AOI center for spatial analysis.
    """
    # Extract location keywords — drop generic words like "zone", "area", "monitoring"
    stop_words = {"zone", "area", "monitoring", "region", "sector", "conflict", "test"}
    name_words = [w for w in aoi.name.lower().split() if w not in stop_words]
    location = " ".join(name_words) if name_words else aoi.name
    query = f'"{location}" (conflict OR military OR attack OR protest)'

    params: dict = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": 250,
    }
    if date_range:
        params["startdatetime"] = date_range["start"].strftime("%Y%m%d%H%M%S")
        params["enddatetime"] = date_range["end"].strftime("%Y%m%d%H%M%S")
    else:
        params["timespan"] = "72h"

    async with session.get(
        GDELT_DOC_URL,
        params=params,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        if resp.status == 429:
            raise RuntimeError("GDELT rate limited — retry in 60s")
        if resp.status != 200:
            raise RuntimeError(f"GDELT returned HTTP {resp.status}")
        text = await resp.text()

    if not text or not text.strip().startswith("{"):
        return []

    import json
    data = json.loads(text)
    raw_articles = data.get("articles", [])

    center_lat = (aoi.bbox[1] + aoi.bbox[3]) / 2
    center_lon = (aoi.bbox[0] + aoi.bbox[2]) / 2

    events: list[dict] = []
    for art in raw_articles:
        events.append({
            "lat": center_lat,
            "lon": center_lon,
            "title": art.get("title", ""),
            "url": art.get("url", ""),
            "tone": art.get("tone", 0.0),
            "domain": art.get("domain", ""),
            "seendate": art.get("seendate", ""),
            "language": art.get("language", ""),
            "source_country": art.get("sourcecountry", ""),
        })

    logger.info("GDELT returned %d articles for AOI %s", len(events), aoi.id)
    return events


async def _fetch_acled(aoi: AOI, session: aiohttp.ClientSession) -> list[dict]:
    """Fetch structured conflict events from ACLED."""
    api_key = os.environ.get("ACLED_API_KEY", "")
    email = os.environ.get("ACLED_EMAIL", "")

    if not api_key:
        raise RuntimeError("ACLED_API_KEY not set in environment")

    center_lat = (aoi.bbox[1] + aoi.bbox[3]) / 2
    center_lon = (aoi.bbox[0] + aoi.bbox[2]) / 2
    date_from = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    params = {
        "key": api_key,
        "email": email,
        "latitude": center_lat,
        "longitude": center_lon,
        "radius": ACLED_RADIUS_KM,
        "event_date": f"{date_from}|{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "event_date_where": "BETWEEN",
        "limit": 500,
    }

    async with session.get(
        ACLED_BASE_URL,
        params=params,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"ACLED returned HTTP {resp.status}")
        data = await resp.json(content_type=None)

    if not data or not isinstance(data, dict):
        return []

    raw_events = data.get("data", [])
    events: list[dict] = []
    for ev in raw_events:
        events.append({
            "lat": float(ev.get("latitude", 0)),
            "lon": float(ev.get("longitude", 0)),
            "event_type": ev.get("event_type", ""),
            "sub_event_type": ev.get("sub_event_type", ""),
            "actor1": ev.get("actor1", ""),
            "actor2": ev.get("actor2", ""),
            "fatalities": int(ev.get("fatalities", 0)),
            "geo_precision": int(ev.get("geo_precision", 3)),
            "event_date": ev.get("event_date", ""),
            "source_url": ev.get("source", ""),
            "notes": ev.get("notes", ""),
        })

    logger.info("ACLED returned %d events for AOI %s", len(events), aoi.id)
    return events


async def ingest(aoi: AOI, date_range: dict | None = None) -> dict:
    """Fetch events from GDELT and ACLED concurrently."""
    gdelt_events: list[dict] = []
    acled_events: list[dict] = []
    gdelt_error: str | None = None
    acled_error: str | None = None

    async with aiohttp.ClientSession() as session:
        gdelt_task = asyncio.create_task(_fetch_gdelt(aoi, session, date_range))
        acled_task = asyncio.create_task(_fetch_acled(aoi, session))

        try:
            gdelt_events = await gdelt_task
        except Exception as exc:
            gdelt_error = str(exc)
            logger.warning("GDELT fetch failed for AOI %s: %s", aoi.id, exc)

        try:
            acled_events = await acled_task
        except Exception as exc:
            acled_error = str(exc)
            logger.warning("ACLED fetch failed for AOI %s: %s", aoi.id, exc)

    return {
        "gdelt_events": gdelt_events,
        "acled_events": acled_events,
        "fetch_timestamp": datetime.now(timezone.utc),
        "gdelt_error": gdelt_error,
        "acled_error": acled_error,
    }
