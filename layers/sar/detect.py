"""SAR amplitude correlation change detection for Sentinel-1 GRD."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import numpy as np
from scipy.ndimage import label, uniform_filter

from core.models import AOI, Contact

logger = logging.getLogger(__name__)

# ── Correlation parameters ────────────────────────────────────────────────
CORR_WINDOW = 5
DISTURBANCE_SIGMA = 1.5
MIN_CLUSTER_PIXELS = 50

# ── Cluster size → detection type ─────────────────────────────────────────
SIZE_UNKNOWN = 200
SIZE_CLEARANCE = 1000
SIZE_CONSTRUCTION = 5000

# ── Confidence scoring ───────────────────────────────────────────────────
BASE_CONFIDENCE = 0.60
SEVERE_DROP_BONUS = 0.10
VERY_SEVERE_DROP_BONUS = 0.15
CONTIGUOUS_BONUS = 0.08
CLEAN_BASELINE_BONUS = 0.05
MAX_CONFIDENCE = 0.85
SEVERE_SIGMA = 2.0
VERY_SEVERE_SIGMA = 2.5
CONTIGUOUS_THRESHOLD = 0.70
CLEAN_BASELINE_DAYS = 12


def _compute_correlation_map(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Compute local Pearson correlation over sliding windows.

    Approximates SAR coherence using GRD amplitude correlation.
    """
    b = before.astype(np.float64)
    a = after.astype(np.float64)

    mean_b = uniform_filter(b, CORR_WINDOW)
    mean_a = uniform_filter(a, CORR_WINDOW)
    mean_ba = uniform_filter(b * a, CORR_WINDOW)
    mean_b2 = uniform_filter(b ** 2, CORR_WINDOW)
    mean_a2 = uniform_filter(a ** 2, CORR_WINDOW)

    var_b = np.maximum(mean_b2 - mean_b ** 2, 0)
    var_a = np.maximum(mean_a2 - mean_a ** 2, 0)
    cov_ba = mean_ba - mean_b * mean_a

    denom = np.sqrt(var_b * var_a)
    safe_denom = np.where(denom > 0, denom, 1.0)
    corr = np.where(denom > 0, cov_ba / safe_denom, 1.0)

    return np.clip(corr, -1.0, 1.0)


def _pixel_to_latlon(
    row: float, col: float, shape: tuple[int, int], bbox: list[float]
) -> tuple[float, float]:
    """Map pixel centroid to geographic coordinates."""
    min_lon, min_lat, max_lon, max_lat = bbox
    h, w = shape
    lon = min_lon + (col / max(w - 1, 1)) * (max_lon - min_lon)
    lat = max_lat - (row / max(h - 1, 1)) * (max_lat - min_lat)
    return round(lat, 6), round(lon, 6)


def _classify_by_size(n_pixels: int) -> str:
    """Map cluster size to ARGUS detection type."""
    if n_pixels < SIZE_UNKNOWN:
        return "unknown"
    if n_pixels < SIZE_CLEARANCE:
        return "terrain_clearance"
    if n_pixels < SIZE_CONSTRUCTION:
        return "construction"
    return "force_buildup"


def _contiguity_ratio(comp_mask: np.ndarray) -> float:
    """Fraction of cluster pixels that have at least one adjacent neighbor."""
    from scipy.ndimage import binary_dilation, generate_binary_structure

    struct = generate_binary_structure(2, 1)
    dilated = binary_dilation(comp_mask, structure=struct)
    interior = dilated & comp_mask
    neighbor_count = binary_dilation(comp_mask, structure=struct, iterations=1)
    contiguous = np.sum(neighbor_count[comp_mask] > 0)
    total = np.sum(comp_mask)
    return float(contiguous / max(total, 1))


def _run_detection(
    before: np.ndarray, after: np.ndarray, metadata: dict
) -> list[dict]:
    """Core SAR disturbance detection pipeline."""
    if before.size == 0 or min(before.shape) < CORR_WINDOW:
        return []

    corr_map = _compute_correlation_map(before, after)

    scene_mean = float(np.mean(corr_map))
    scene_std = float(np.std(corr_map))

    if scene_std < 1e-6:
        return []

    threshold = scene_mean - DISTURBANCE_SIGMA * scene_std
    disturbed = corr_map < threshold

    labeled, n_components = label(disturbed)

    baseline_days = metadata.get("temporal_baseline_days", 0)
    bbox = metadata.get("bbox", [0, 0, 0, 0])

    anomalies: list[dict] = []
    for comp_id in range(1, n_components + 1):
        comp_mask = labeled == comp_id
        n_pixels = int(np.sum(comp_mask))

        if n_pixels < MIN_CLUSTER_PIXELS:
            continue

        detection_type = _classify_by_size(n_pixels)
        if detection_type == "unknown":
            continue

        rows, cols = np.where(comp_mask)
        lat, lon = _pixel_to_latlon(
            float(np.mean(rows)), float(np.mean(cols)), corr_map.shape, bbox
        )

        cluster_corr = float(np.mean(corr_map[comp_mask]))
        drop = scene_mean - cluster_corr
        drop_sigma = drop / scene_std if scene_std > 0 else 0

        # Confidence scoring
        confidence = BASE_CONFIDENCE
        if drop_sigma >= VERY_SEVERE_SIGMA:
            confidence += VERY_SEVERE_DROP_BONUS
        elif drop_sigma >= SEVERE_SIGMA:
            confidence += SEVERE_DROP_BONUS

        contig = _contiguity_ratio(comp_mask)
        if contig >= CONTIGUOUS_THRESHOLD:
            confidence += CONTIGUOUS_BONUS

        if baseline_days <= CLEAN_BASELINE_DAYS:
            confidence += CLEAN_BASELINE_BONUS

        confidence = min(confidence, MAX_CONFIDENCE)

        anomalies.append({
            "lat": lat,
            "lon": lon,
            "detection_type": detection_type,
            "confidence": round(confidence, 4),
            "correlation_mean": round(scene_mean, 4),
            "correlation_drop": round(drop, 4),
            "cluster_pixels": n_pixels,
            "temporal_baseline_days": baseline_days,
            "orbit_number": metadata.get("orbit_number", 0),
            "pass_direction": metadata.get("pass_direction", ""),
            "before_date": metadata.get("before_date", ""),
            "after_date": metadata.get("after_date", ""),
        })

    return anomalies


async def detect(aoi: AOI, raw_data: dict) -> list[Contact]:
    """Run SAR disturbance detection and return Contact objects."""
    if raw_data.get("error"):
        logger.warning(
            "Skipping SAR detection for AOI %s: %s", aoi.id, raw_data["error"]
        )
        return []

    metadata = {
        "bbox": raw_data.get("bbox", list(aoi.bbox)),
        "temporal_baseline_days": raw_data.get("temporal_baseline_days", 0),
        "orbit_number": raw_data.get("before_scene", {}).get("orbit_number", 0),
        "pass_direction": raw_data.get("before_scene", {}).get("pass_direction", ""),
        "before_date": raw_data.get("before_scene", {}).get("datetime", ""),
        "after_date": raw_data.get("after_scene", {}).get("datetime", ""),
    }

    anomalies = await asyncio.to_thread(
        _run_detection,
        raw_data["before_image"],
        raw_data["after_image"],
        metadata,
    )

    contacts: list[Contact] = []
    for a in anomalies:
        contacts.append(Contact(
            id=str(uuid.uuid4()),
            aoi_id=aoi.id,
            timestamp=datetime.now(timezone.utc),
            source="sar",
            confidence=a["confidence"],
            detection_type=a["detection_type"],
            lat=a["lat"],
            lon=a["lon"],
            description=(
                f"SAR coherence drop: {a['correlation_drop']:.3f} below mean "
                f"({a['cluster_pixels']} pixels, {a['temporal_baseline_days']}d baseline)"
            ),
            raw_evidence={
                "source": "sar",
                "correlation_mean": a["correlation_mean"],
                "correlation_drop": a["correlation_drop"],
                "cluster_pixels": a["cluster_pixels"],
                "temporal_baseline_days": a["temporal_baseline_days"],
                "orbit_number": a["orbit_number"],
                "pass_direction": a["pass_direction"],
                "before_date": a["before_date"],
                "after_date": a["after_date"],
            },
        ))

    logger.info(
        "SAR layer found %d disturbances for AOI %s", len(contacts), aoi.id
    )
    return contacts
