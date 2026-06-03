"""SSIM + band anomaly change detection for Sentinel-2 imagery.

Ported from IRIS spectral.py — adapted to ARGUS architecture with
Contact output, async interface, and ARGUS detection type taxonomy.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import numpy as np
from scipy.ndimage import label, uniform_filter

from core.models import AOI, Contact

logger = logging.getLogger(__name__)

# ── Thresholds (ported from IRIS spectral.py) ──────────────────────────────
S2_SCALE = 10_000.0
SSIM_CHANGE_THRESHOLD = 0.85
SSIM_STRONG_CHANGE = 0.70
SSIM_WIN_SIZE = 7

NDVI_CHANGE_THRESHOLD = 0.15
SWIR_RISE_THRESHOLD = 0.20

MIN_CHANGED_PIXELS_PCT = 2.0
MIN_COMPONENT_PIXELS = 10

# ── Confidence scoring (adaptation rules) ─────────────────────────────────
BASE_CONFIDENCE = 0.55
SSIM_STRONG_BONUS = 0.15
MULTI_BAND_BONUS = 0.10
LOW_CLOUD_BONUS = 0.05
MAX_CONFIDENCE = 0.85


def _compute_ndvi(bands: dict[str, np.ndarray]) -> np.ndarray:
    """Compute NDVI: (NIR - Red) / (NIR + Red). Ported from IRIS."""
    nir = bands["B8"] / S2_SCALE
    red = bands["B4"] / S2_SCALE
    denom = nir + red
    safe_denom = np.where(denom > 0, denom, 1.0)
    return np.where(denom > 0, (nir - red) / safe_denom, 0.0).astype(np.float32)


def _compute_ssim_map(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Compute local SSIM map between two 2D float arrays in [0, 1] range.

    Uses windowed statistics via uniform_filter, matching the SSIM formula
    from IRIS's skimage call but producing a spatial map instead of a scalar.
    """
    c1 = 0.01 ** 2
    c2 = 0.03 ** 2

    mu_b = uniform_filter(before, SSIM_WIN_SIZE)
    mu_a = uniform_filter(after, SSIM_WIN_SIZE)

    sigma_b_sq = np.maximum(
        uniform_filter(before ** 2, SSIM_WIN_SIZE) - mu_b ** 2, 0
    )
    sigma_a_sq = np.maximum(
        uniform_filter(after ** 2, SSIM_WIN_SIZE) - mu_a ** 2, 0
    )
    sigma_ba = uniform_filter(before * after, SSIM_WIN_SIZE) - mu_b * mu_a

    num = (2 * mu_b * mu_a + c1) * (2 * sigma_ba + c2)
    den = (mu_b ** 2 + mu_a ** 2 + c1) * (sigma_b_sq + sigma_a_sq + c2)

    return num / den


def _pixel_to_latlon(
    row: float, col: float, shape: tuple[int, int], bbox: list[float]
) -> tuple[float, float]:
    """Map pixel centroid to geographic coordinates within the AOI bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox
    h, w = shape
    lon = min_lon + (col / max(w - 1, 1)) * (max_lon - min_lon)
    lat = max_lat - (row / max(h - 1, 1)) * (max_lat - min_lat)
    return round(lat, 6), round(lon, 6)


def _classify_component(
    ssim_mask: np.ndarray,
    swir_mask: np.ndarray,
    ndvi_mask: np.ndarray,
    comp_mask: np.ndarray,
) -> str:
    """Determine ARGUS detection type for a connected component."""
    has_ssim = bool(np.any(ssim_mask & comp_mask))
    has_swir = bool(np.any(swir_mask & comp_mask))
    has_ndvi = bool(np.any(ndvi_mask & comp_mask))
    area = int(np.sum(comp_mask))

    if has_ssim and has_swir:
        return "construction"
    if has_ssim and has_ndvi:
        return "terrain_clearance"
    if has_ssim and area > 100:
        return "force_buildup"
    if has_swir:
        return "construction"
    return "unknown"


def _run_detection(
    before: dict[str, np.ndarray],
    after: dict[str, np.ndarray],
    metadata: dict,
) -> list[dict]:
    """Core spectral analysis: SSIM + SWIR + NDVI. Adapted from IRIS classify_change()."""
    before_vis = np.mean(
        [before[b] / S2_SCALE for b in ("B2", "B3", "B4")], axis=0
    ).astype(np.float32)
    after_vis = np.mean(
        [after[b] / S2_SCALE for b in ("B2", "B3", "B4")], axis=0
    ).astype(np.float32)

    if before_vis.size == 0 or min(before_vis.shape) < SSIM_WIN_SIZE:
        return []

    # ── SSIM spatial map ──
    ssim_map = _compute_ssim_map(before_vis, after_vis)
    ssim_change_mask = ssim_map < SSIM_CHANGE_THRESHOLD

    # ── SWIR relative change (B11) — rise indicates construction / bare earth ──
    b11_before = before["B11"].astype(np.float32)
    b11_after = after["B11"].astype(np.float32)
    swir_rel = np.where(
        b11_before > 0.01 * S2_SCALE,
        (b11_after - b11_before) / (b11_before + 1e-6),
        0.0,
    )
    swir_rise_mask = swir_rel > SWIR_RISE_THRESHOLD

    # ── NDVI change — drop indicates vegetation clearance ──
    ndvi_before = _compute_ndvi(before)
    ndvi_after = _compute_ndvi(after)
    ndvi_delta = ndvi_after - ndvi_before
    ndvi_loss_mask = ndvi_delta < -NDVI_CHANGE_THRESHOLD

    # ── Combined change mask ──
    combined = ssim_change_mask | swir_rise_mask | ndvi_loss_mask
    total_pixels = combined.size
    changed_pct = float(np.sum(combined) / total_pixels * 100)

    if changed_pct < MIN_CHANGED_PIXELS_PCT:
        return []

    # ── Connected component labelling ──
    labeled, n_components = label(combined)
    cloud_pct = max(
        metadata.get("before_cloud_pct", 0),
        metadata.get("after_cloud_pct", 0),
    )

    anomalies: list[dict] = []
    for comp_id in range(1, n_components + 1):
        comp_mask = labeled == comp_id
        if np.sum(comp_mask) < MIN_COMPONENT_PIXELS:
            continue

        detection_type = _classify_component(
            ssim_change_mask, swir_rise_mask, ndvi_loss_mask, comp_mask
        )
        if detection_type == "unknown":
            continue

        rows, cols = np.where(comp_mask)
        lat, lon = _pixel_to_latlon(
            float(np.mean(rows)),
            float(np.mean(cols)),
            combined.shape,
            metadata["bbox"],
        )

        # ── Confidence scoring ──
        confidence = BASE_CONFIDENCE
        comp_ssim = float(np.mean(ssim_map[comp_mask]))
        if comp_ssim < SSIM_STRONG_CHANGE:
            confidence += SSIM_STRONG_BONUS

        signals = sum([
            bool(np.any(ssim_change_mask & comp_mask)),
            bool(np.any(swir_rise_mask & comp_mask)),
            bool(np.any(ndvi_loss_mask & comp_mask)),
        ])
        if signals >= 2:
            confidence += MULTI_BAND_BONUS

        if cloud_pct < 5:
            confidence += LOW_CLOUD_BONUS

        confidence = min(confidence, MAX_CONFIDENCE)

        dominant = "visible"
        if bool(np.any(swir_rise_mask & comp_mask)):
            dominant = "swir"
        elif bool(np.any(ndvi_loss_mask & comp_mask)):
            dominant = "nir"

        anomalies.append({
            "lat": lat,
            "lon": lon,
            "detection_type": detection_type,
            "confidence": round(confidence, 4),
            "ssim_score": round(comp_ssim, 4),
            "changed_pixels_pct": round(
                float(np.sum(comp_mask) / total_pixels * 100), 2
            ),
            "dominant_band": dominant,
            "cloud_cover_pct": round(cloud_pct, 2),
            "image_date_before": metadata["before_date"],
            "image_date_after": metadata["after_date"],
        })

    return anomalies


async def detect(aoi: AOI, raw_data: dict) -> list[Contact]:
    """Run optical change detection and return Contact objects."""
    if "error" in raw_data:
        logger.warning(
            "Skipping detection for AOI %s: %s", aoi.id, raw_data["error"]
        )
        return []

    anomalies = await asyncio.to_thread(
        _run_detection,
        raw_data["before_image"],
        raw_data["after_image"],
        raw_data["metadata"],
    )

    is_natural_noise = getattr(aoi, "terrain_type", None) in ("volcanic", "glacial")

    contacts: list[Contact] = []
    for a in anomalies:
        dt = a["detection_type"]
        if is_natural_noise and dt in ("construction", "terrain_clearance"):
            dt = "geological_activity"
        contacts.append(
            Contact(
                id=str(uuid.uuid4()),
                aoi_id=aoi.id,
                timestamp=datetime.now(timezone.utc),
                source="optical",
                confidence=a["confidence"],
                detection_type=dt,
                lat=a["lat"],
                lon=a["lon"],
                description=(
                    f"Optical {dt.replace('_', ' ')} detected "
                    f"via {a['dominant_band']} analysis "
                    f"(SSIM: {a['ssim_score']:.2f})"
                ),
                raw_evidence={
                    "ssim_score": a["ssim_score"],
                    "changed_pixels_pct": a["changed_pixels_pct"],
                    "dominant_band": a["dominant_band"],
                    "cloud_cover_pct": a["cloud_cover_pct"],
                    "image_date_before": a["image_date_before"],
                    "image_date_after": a["image_date_after"],
                },
            )
        )

    logger.info(
        "Optical layer found %d anomalies for AOI %s", len(contacts), aoi.id
    )
    return contacts
