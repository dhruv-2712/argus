"""Flight pattern detection — classifies ADS-B aircraft as high-interest contacts."""

import logging
import uuid
from datetime import datetime, timezone

from core.models import AOI, Contact

logger = logging.getLogger(__name__)

# USAF/USN/USMC/NATO military callsign prefixes
_MIL_PREFIXES = {
    "RCH",    # USAF AMC airlift
    "DUKE",   # USAF tanker
    "SPAR",   # USAF VIP/exec transport
    "IRON",   # USAF fighter
    "GRZLY",  # USMC
    "BDOG",   # USAF
    "JAKE",   # USN
    "STING",  # USN
    "FORTE",  # USAF RC-135 RIVET JOINT (SIGINT collector)
    "COBRA",  # ISR
    "RECON",
    "RRR",    # RAF
    "NATO",
    "UAVGH",  # unmanned
}

# Special squawk codes → (reason_label, confidence)
_SQUAWKS = {
    "7500": ("hijack_or_seizure", 0.90),
    "7600": ("comms_loss", 0.65),
    "7700": ("emergency", 0.70),
    "7777": ("military_intercept", 0.88),
}

# Countries of concern when overflying sensitive AOIs
_CONCERN_COUNTRIES = {
    "Russia", "China", "Iran", "North Korea", "Belarus", "Syria",
}

# High-altitude ISR profile: 45,000–70,000 ft (13,700–21,300 m), slow
_ISR_ALT_MIN = 13_700   # m
_ISR_ALT_MAX = 21_300   # m
_ISR_SPD_MAX = 200      # m/s ≈ 390 kt (ISR platforms cruise slowly)


async def detect(aoi: AOI, raw_data: dict) -> list[Contact]:
    if raw_data.get("error") and not raw_data.get("aircraft"):
        return []

    contacts: list[Contact] = []
    for ac in raw_data.get("aircraft", []):
        if ac.get("on_ground"):
            continue
        c = _classify(ac, aoi.id)
        if c:
            contacts.append(c)

    logger.info("Flights: %d contacts for AOI %s", len(contacts), aoi.id)
    return contacts


def _classify(ac: dict, aoi_id: str) -> Contact | None:
    callsign = ac.get("callsign", "").upper()
    squawk = ac.get("squawk", "")
    country = ac.get("origin_country", "")
    alt_m = ac.get("baro_altitude", 0) or 0
    speed_ms = ac.get("velocity", 0) or 0

    # Priority squawk codes trump everything else
    if squawk in _SQUAWKS:
        label, conf = _SQUAWKS[squawk]
        return _make_contact(ac, aoi_id, conf, f"squawk {squawk} — {label}")

    confidence = 0.0
    reason = ""

    for prefix in _MIL_PREFIXES:
        if callsign.startswith(prefix):
            confidence = max(confidence, 0.72)
            reason = f"military callsign {callsign}"
            break

    if country in _CONCERN_COUNTRIES:
        confidence = max(confidence, 0.60)
        reason = reason or f"{country} aircraft over AOI"

    if _ISR_ALT_MIN <= alt_m <= _ISR_ALT_MAX and speed_ms <= _ISR_SPD_MAX:
        confidence = max(confidence, 0.68)
        reason = reason or (
            f"ISR profile — {alt_m/1000:.0f}km alt, "
            f"{speed_ms:.0f}m/s ({speed_ms*1.944:.0f}kt)"
        )

    if confidence < 0.40:
        return None

    return _make_contact(ac, aoi_id, min(confidence, 0.88), reason)


def _make_contact(ac: dict, aoi_id: str, confidence: float, reason: str) -> Contact:
    alt_ft = (ac.get("baro_altitude") or 0) * 3.281
    callsign = ac.get("callsign", ac.get("icao24", "UNKNOWN"))
    return Contact(
        id=str(uuid.uuid4()),
        aoi_id=aoi_id,
        timestamp=datetime.now(timezone.utc),
        source="flights",
        confidence=round(confidence, 4),
        detection_type="force_buildup",
        lat=ac["lat"],
        lon=ac["lon"],
        description=(
            f"Aircraft {callsign} ({ac.get('origin_country', '?')}): "
            f"{alt_ft:.0f}ft hdg {ac.get('heading', 0):.0f}° — {reason}"
        ),
        raw_evidence={
            "source": "flights",
            "icao24": ac.get("icao24"),
            "callsign": callsign,
            "origin_country": ac.get("origin_country"),
            "baro_altitude": ac.get("baro_altitude"),
            "velocity": ac.get("velocity"),
            "heading": ac.get("heading"),
            "squawk": ac.get("squawk"),
            "detection_reason": reason,
        },
    )
