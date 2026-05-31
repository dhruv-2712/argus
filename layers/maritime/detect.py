"""AIS anomaly detection: loitering, formation movement, dark vessels."""

import logging
import uuid
from datetime import datetime, timezone
from math import radians, sin, cos, sqrt, atan2

from core.models import AOI, Contact

logger = logging.getLogger(__name__)

# ── Port exclusion zones (lat, lon) with 10 nm radius ────────────────────
PORTS = [
    (18.93, 72.84),   # Mumbai
    (6.95, 79.84),    # Colombo
    (13.08, 80.29),   # Chennai
    (1.27, 103.82),   # Singapore
    (24.86, 66.99),   # Karachi
    (12.78, 44.98),   # Aden
]
PORT_EXCLUSION_NM = 10.0

# ── Vessel type codes ────────────────────────────────────────────────────
CARGO_TYPES = range(70, 80)
TANKER_TYPES = range(80, 90)
FISHING_TYPES = (30,)
MILITARY_TYPES = (35, 36)

# ── Loitering thresholds ────────────────────────────────────────────────
LOITER_SPEED_MAX_KT = 2.0
LOITER_DISPLACEMENT_NM = 2.0
LOITER_MIN_HOURS = 2.0

# ── Formation thresholds ────────────────────────────────────────────────
FORMATION_RANGE_NM = 5.0
FORMATION_HEADING_TOL = 15.0
FORMATION_SPEED_TOL = 3.0
FORMATION_MIN_VESSELS = 3

# ── Dark vessel thresholds ──────────────────────────────────────────────
DARK_GAP_HOURS = 4.0


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in nautical miles."""
    r = 3440.065  # Earth radius in nm
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


def _near_port(lat: float, lon: float) -> bool:
    """Check if position is within PORT_EXCLUSION_NM of a known port."""
    return any(
        _haversine_nm(lat, lon, plat, plon) < PORT_EXCLUSION_NM
        for plat, plon in PORTS
    )


def _is_high_interest(vessel_type: int) -> bool:
    """Check if vessel type is cargo or tanker (higher anomaly significance)."""
    return vessel_type in CARGO_TYPES or vessel_type in TANKER_TYPES


def _vessel_type_label(vessel_type: int) -> str:
    """Human-readable vessel type."""
    if vessel_type in CARGO_TYPES:
        return "cargo"
    if vessel_type in TANKER_TYPES:
        return "tanker"
    if vessel_type in FISHING_TYPES:
        return "fishing"
    if vessel_type in MILITARY_TYPES:
        return "military"
    return "other"


def _detect_loitering(vessels: list[dict], aoi_id: str) -> list[Contact]:
    """Detect vessels loitering in the AOI."""
    contacts: list[Contact] = []

    for v in vessels:
        speed = v.get("speed", 0)
        track = v.get("track", [])

        if speed > LOITER_SPEED_MAX_KT:
            continue

        if _near_port(v["lat"], v["lon"]):
            continue

        # With track history, check displacement
        duration_hours = 0.0
        if len(track) >= 2:
            first = track[0]
            last = track[-1]
            displacement = _haversine_nm(
                first["lat"], first["lon"], last["lat"], last["lon"]
            )
            if displacement > LOITER_DISPLACEMENT_NM:
                continue
            if isinstance(first.get("timestamp"), datetime) and isinstance(last.get("timestamp"), datetime):
                duration_hours = (last["timestamp"] - first["timestamp"]).total_seconds() / 3600
            if duration_hours < LOITER_MIN_HOURS:
                continue
        else:
            # No track: flag based on current speed alone, shorter duration
            duration_hours = 1.0
            if speed > 0.5:
                continue

        confidence = 0.50
        vtype = v.get("vessel_type", 0)
        if _is_high_interest(vtype):
            confidence += 0.10
        if duration_hours > 4:
            confidence += 0.10
        confidence = min(confidence, 0.75)

        contacts.append(Contact(
            id=str(uuid.uuid4()),
            aoi_id=aoi_id,
            timestamp=datetime.now(timezone.utc),
            source="maritime",
            confidence=round(confidence, 4),
            detection_type="vessel_anomaly",
            lat=v["lat"],
            lon=v["lon"],
            description=(
                f"Vessel {v['vessel_name']} ({_vessel_type_label(vtype)}) "
                f"loitering at {speed:.1f}kt for {duration_hours:.1f}h"
            ),
            raw_evidence={
                "source": "maritime",
                "mmsi": v["mmsi"],
                "vessel_name": v["vessel_name"],
                "vessel_type_code": vtype,
                "anomaly_type": "loitering",
                "duration_hours": round(duration_hours, 1),
                "speed_knots": round(speed, 1),
                "heading": v.get("heading", 0),
                "formation_size": None,
                "formation_mmsi_list": None,
            },
        ))

    return contacts


def _detect_formations(vessels: list[dict], aoi_id: str) -> list[Contact]:
    """Detect coordinated vessel formations."""
    contacts: list[Contact] = []
    n = len(vessels)
    used = set()

    for i in range(n):
        if i in used:
            continue
        group = [i]
        vi = vessels[i]

        for j in range(i + 1, n):
            if j in used:
                continue
            vj = vessels[j]

            dist = _haversine_nm(vi["lat"], vi["lon"], vj["lat"], vj["lon"])
            if dist > FORMATION_RANGE_NM:
                continue

            heading_diff = abs(vi.get("heading", 0) - vj.get("heading", 0))
            if heading_diff > 180:
                heading_diff = 360 - heading_diff
            if heading_diff > FORMATION_HEADING_TOL:
                continue

            speed_diff = abs(vi.get("speed", 0) - vj.get("speed", 0))
            if speed_diff > FORMATION_SPEED_TOL:
                continue

            group.append(j)

        if len(group) < FORMATION_MIN_VESSELS:
            continue

        for idx in group:
            used.add(idx)

        group_vessels = [vessels[idx] for idx in group]
        avg_lat = sum(v["lat"] for v in group_vessels) / len(group_vessels)
        avg_lon = sum(v["lon"] for v in group_vessels) / len(group_vessels)
        avg_heading = sum(v.get("heading", 0) for v in group_vessels) / len(group_vessels)
        avg_speed = sum(v.get("speed", 0) for v in group_vessels) / len(group_vessels)

        confidence = 0.55 + min(0.10 * (len(group) - FORMATION_MIN_VESSELS), 0.20)
        confidence = min(confidence, 0.80)

        mmsi_list = [v["mmsi"] for v in group_vessels]

        contacts.append(Contact(
            id=str(uuid.uuid4()),
            aoi_id=aoi_id,
            timestamp=datetime.now(timezone.utc),
            source="maritime",
            confidence=round(confidence, 4),
            detection_type="vessel_anomaly",
            lat=round(avg_lat, 6),
            lon=round(avg_lon, 6),
            description=(
                f"Formation of {len(group)} vessels, "
                f"heading {avg_heading:.0f}°, {avg_speed:.1f}kt"
            ),
            raw_evidence={
                "source": "maritime",
                "mmsi": mmsi_list[0],
                "vessel_name": group_vessels[0]["vessel_name"],
                "vessel_type_code": group_vessels[0].get("vessel_type", 0),
                "anomaly_type": "formation",
                "duration_hours": 0,
                "speed_knots": round(avg_speed, 1),
                "heading": round(avg_heading, 1),
                "formation_size": len(group),
                "formation_mmsi_list": mmsi_list,
            },
        ))

    return contacts


def _detect_dark_vessels(vessels: list[dict], aoi_id: str) -> list[Contact]:
    """Detect vessels with AIS transmission gaps."""
    contacts: list[Contact] = []

    for v in vessels:
        track = v.get("track", [])
        if len(track) < 3:
            continue

        max_gap_hours = 0.0
        for k in range(1, len(track)):
            t0 = track[k - 1].get("timestamp")
            t1 = track[k].get("timestamp")
            if not isinstance(t0, datetime) or not isinstance(t1, datetime):
                continue
            gap = (t1 - t0).total_seconds() / 3600
            if gap > max_gap_hours:
                max_gap_hours = gap

        if max_gap_hours < DARK_GAP_HOURS:
            continue

        confidence = 0.70
        vtype = v.get("vessel_type", 0)
        if _is_high_interest(vtype):
            confidence += 0.10
        confidence = min(confidence, 0.85)

        contacts.append(Contact(
            id=str(uuid.uuid4()),
            aoi_id=aoi_id,
            timestamp=datetime.now(timezone.utc),
            source="maritime",
            confidence=round(confidence, 4),
            detection_type="vessel_anomaly",
            lat=v["lat"],
            lon=v["lon"],
            description=(
                f"Vessel {v['vessel_name']} went dark for {max_gap_hours:.1f}h "
                f"({_vessel_type_label(vtype)})"
            ),
            raw_evidence={
                "source": "maritime",
                "mmsi": v["mmsi"],
                "vessel_name": v["vessel_name"],
                "vessel_type_code": vtype,
                "anomaly_type": "dark_vessel",
                "duration_hours": round(max_gap_hours, 1),
                "speed_knots": round(v.get("speed", 0), 1),
                "heading": v.get("heading", 0),
                "formation_size": None,
                "formation_mmsi_list": None,
            },
        ))

    return contacts


async def detect(aoi: AOI, raw_data: dict) -> list[Contact]:
    """Run all maritime anomaly detectors."""
    if raw_data.get("skipped"):
        return []

    if raw_data.get("error") and not raw_data.get("vessels"):
        logger.warning(
            "Skipping maritime detection for AOI %s: %s",
            aoi.id, raw_data["error"],
        )
        return []

    vessels = raw_data.get("vessels", [])
    if not vessels:
        return []

    loitering = _detect_loitering(vessels, aoi.id)
    formations = _detect_formations(vessels, aoi.id)
    dark = _detect_dark_vessels(vessels, aoi.id)

    all_contacts = loitering + formations + dark
    logger.info(
        "Maritime layer: %d loitering + %d formation + %d dark = %d contacts for AOI %s",
        len(loitering), len(formations), len(dark), len(all_contacts), aoi.id,
    )
    return all_contacts
