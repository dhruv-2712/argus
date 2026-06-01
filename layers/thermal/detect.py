"""Thermal anomaly detection — classifies NASA FIRMS hotspots as military contacts."""

import logging
import uuid
from datetime import datetime, timezone

from core.models import AOI, Contact

logger = logging.getLogger(__name__)

# Brightness temperature thresholds (Kelvin, VIIRS band I-4)
_BRIGHT_HIGH = 360.0
_BRIGHT_MED = 330.0

# Fire Radiative Power thresholds (MW)
_FRP_HIGH = 100.0
_FRP_MED = 20.0

_HIGH_CONF = {"high", "h"}
_NOM_CONF = {"nominal", "n"}


async def detect(aoi: AOI, raw_data: dict) -> list[Contact]:
    if raw_data.get("skipped") or (raw_data.get("error") and not raw_data.get("hotspots")):
        return []

    hotspots = raw_data.get("hotspots", [])
    contacts: list[Contact] = []

    for hs in hotspots:
        conf = _score(hs)
        if conf < 0.35:
            continue

        bright = hs.get("bright_ti4", 0)
        frp = hs.get("frp", 0)
        night = hs.get("daynight", "D") == "N"

        contacts.append(Contact(
            id=str(uuid.uuid4()),
            aoi_id=aoi.id,
            timestamp=datetime.now(timezone.utc),
            source="thermal",
            confidence=round(conf, 4),
            detection_type="force_buildup",
            lat=hs["lat"],
            lon=hs["lon"],
            description=(
                f"Thermal anomaly {'[NIGHT]' if night else '[DAY]'}: "
                f"T={bright:.0f}K FRP={frp:.0f}MW"
            ),
            raw_evidence={
                "source": "thermal",
                "bright_ti4": bright,
                "frp": frp,
                "daynight": hs.get("daynight"),
                "firms_confidence": hs.get("confidence"),
                "acq_date": hs.get("acq_date"),
                "acq_time": hs.get("acq_time"),
            },
        ))

    logger.info("Thermal: %d contacts for AOI %s", len(contacts), aoi.id)
    return contacts


def _score(hs: dict) -> float:
    score = 0.0
    bright = hs.get("bright_ti4", 0)
    frp = hs.get("frp", 0)
    label = str(hs.get("confidence", "")).lower()
    night = hs.get("daynight", "D") == "N"

    if bright >= _BRIGHT_HIGH:
        score += 0.45
    elif bright >= _BRIGHT_MED:
        score += 0.25
    else:
        score += 0.10

    if frp >= _FRP_HIGH:
        score += 0.30
    elif frp >= _FRP_MED:
        score += 0.15

    if label in _HIGH_CONF:
        score += 0.15
    elif label in _NOM_CONF:
        score += 0.08

    if night:
        score += 0.10  # night fires have less background clutter

    return min(score, 0.90)
