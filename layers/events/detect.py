"""Event spike detection from GDELT + ACLED data."""

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from core.models import AOI, Contact

logger = logging.getLogger(__name__)

# ── GDELT thresholds ──────────────────────────────────────────────────────
GDELT_GRID_SIZE = 0.5
GDELT_SPIKE_MIN_EVENTS = 3
GDELT_NEGATIVE_TONE_THRESHOLD = -5.0
GDELT_VERY_NEGATIVE_TONE = -7.0

GDELT_BASE_CONFIDENCE = 0.35
GDELT_CLUSTER_BONUS = 0.10
GDELT_MILITARY_BONUS = 0.15
GDELT_TONE_BONUS = 0.05
GDELT_MULTI_SOURCE_BONUS = 0.10
GDELT_MAX_CONFIDENCE = 0.65

MILITARY_CAMEO_PREFIXES = ("18", "19", "20", "17", "15")
FORCE_CAMEO_PREFIXES = ("18", "19", "20", "17", "15")

# ── ACLED thresholds ──────────────────────────────────────────────────────
ACLED_VIOLENT_TYPES = {"Battles", "Explosions/Remote violence", "Violence against civilians"}
ACLED_FORCE_TYPES = {"Battles", "Explosions/Remote violence"}

ACLED_BASE_CONFIDENCE = 0.55
ACLED_FATALITIES_BONUS = 0.15
ACLED_HIGH_FATALITIES_BONUS = 0.10
ACLED_PRECISION_BONUS = 0.10
ACLED_MAX_CONFIDENCE = 0.85


def _snap_to_grid(lat: float, lon: float) -> str:
    """Snap coordinates to a 0.5-degree grid cell identifier."""
    cell_lat = round(lat / GDELT_GRID_SIZE) * GDELT_GRID_SIZE
    cell_lon = round(lon / GDELT_GRID_SIZE) * GDELT_GRID_SIZE
    return f"{cell_lat:.1f}_{cell_lon:.1f}"


def _title_has_military_signal(title: str) -> bool:
    """Check if an article title contains military/force-related keywords."""
    keywords = {"military", "troops", "soldiers", "army", "artillery", "airstrike",
                "bombing", "missile", "weapon", "tank", "deploy", "offensive"}
    title_lower = title.lower()
    return any(kw in title_lower for kw in keywords)


def _acled_detection_type(event_type: str) -> str:
    """Map ACLED event type to ARGUS detection type."""
    if event_type in ACLED_FORCE_TYPES:
        return "force_buildup"
    return "event_spike"


def _detect_gdelt(events: list[dict], aoi_id: str) -> list[Contact]:
    """Detect event spikes from GDELT article data.

    Articles are region-scoped (assigned to AOI center by ingest). We detect
    spikes based on article density, tone, and military keyword signals.
    """
    if not events:
        return []

    cell_key = _snap_to_grid(events[0]["lat"], events[0]["lon"])

    is_cluster = len(events) >= GDELT_SPIKE_MIN_EVENTS
    has_negative = any(
        ev.get("tone", 0) < GDELT_NEGATIVE_TONE_THRESHOLD for ev in events
    )

    if not is_cluster and not has_negative:
        return []

    has_military = any(
        _title_has_military_signal(ev.get("title", "")) for ev in events
    )
    tones = [ev.get("tone", 0) for ev in events if ev.get("tone", 0) != 0]
    avg_tone = sum(tones) / len(tones) if tones else 0.0
    distinct_sources = len({ev.get("domain", "") for ev in events})

    confidence = GDELT_BASE_CONFIDENCE
    if is_cluster:
        confidence += GDELT_CLUSTER_BONUS
    if has_military:
        confidence += GDELT_MILITARY_BONUS
    if avg_tone < GDELT_VERY_NEGATIVE_TONE:
        confidence += GDELT_TONE_BONUS
    if distinct_sources >= 3:
        confidence += GDELT_MULTI_SOURCE_BONUS
    confidence = min(confidence, GDELT_MAX_CONFIDENCE)

    detection_type = "force_buildup" if has_military else "event_spike"
    center_lat = events[0]["lat"]
    center_lon = events[0]["lon"]
    top_urls = [ev.get("url", "") for ev in events if ev.get("url")][:3]

    return [Contact(
        id=str(uuid.uuid4()),
        aoi_id=aoi_id,
        timestamp=datetime.now(timezone.utc),
        source="events",
        confidence=round(confidence, 4),
        detection_type=detection_type,
        lat=round(center_lat, 6),
        lon=round(center_lon, 6),
        description=(
            f"GDELT event spike: {len(events)} articles in region "
            f"(avg tone {avg_tone:.1f}, {distinct_sources} sources)"
        ),
        raw_evidence={
            "source": "gdelt",
            "event_count": len(events),
            "avg_tone": round(avg_tone, 2),
            "cameo_codes": [],
            "top_source_urls": top_urls,
            "grid_cell": cell_key,
        },
    )]


def _detect_acled(events: list[dict], aoi_id: str) -> list[Contact]:
    """Create contacts from significant ACLED events."""
    if not events:
        return []

    contacts: list[Contact] = []
    for ev in events:
        event_type = ev.get("event_type", "")
        fatalities = ev.get("fatalities", 0)

        is_violent = event_type in ACLED_VIOLENT_TYPES
        has_fatalities = fatalities > 0

        if not is_violent and not has_fatalities:
            continue

        confidence = ACLED_BASE_CONFIDENCE
        if has_fatalities:
            confidence += ACLED_FATALITIES_BONUS
        if fatalities > 10:
            confidence += ACLED_HIGH_FATALITIES_BONUS
        if ev.get("geo_precision", 3) == 1:
            confidence += ACLED_PRECISION_BONUS
        confidence = min(confidence, ACLED_MAX_CONFIDENCE)

        detection_type = _acled_detection_type(event_type)

        contacts.append(Contact(
            id=str(uuid.uuid4()),
            aoi_id=aoi_id,
            timestamp=datetime.now(timezone.utc),
            source="events",
            confidence=round(confidence, 4),
            detection_type=detection_type,
            lat=ev["lat"],
            lon=ev["lon"],
            description=(
                f"ACLED {event_type}: {ev.get('sub_event_type', '')} "
                f"({fatalities} fatalities)"
            ),
            raw_evidence={
                "source": "acled",
                "event_type": event_type,
                "sub_event_type": ev.get("sub_event_type", ""),
                "actor1": ev.get("actor1", ""),
                "actor2": ev.get("actor2"),
                "fatalities": fatalities,
                "geo_precision": ev.get("geo_precision", 3),
                "source_url": ev.get("source_url", ""),
            },
        ))

    return contacts


async def detect(aoi: AOI, raw_data: dict) -> list[Contact]:
    """Run event spike detection on GDELT + ACLED data."""
    gdelt_contacts = _detect_gdelt(raw_data.get("gdelt_events", []), aoi.id)
    acled_contacts = _detect_acled(raw_data.get("acled_events", []), aoi.id)

    all_contacts = gdelt_contacts + acled_contacts
    logger.info(
        "Events layer: %d GDELT + %d ACLED = %d contacts for AOI %s",
        len(gdelt_contacts), len(acled_contacts), len(all_contacts), aoi.id,
    )
    return all_contacts
