"""Sentinel-1 GRD imagery ingestion via Microsoft Planetary Computer STAC."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import planetary_computer
import pystac_client
import rasterio
import numpy as np
from rasterio.enums import Resampling
from rasterio.windows import Window

from core.models import AOI

logger = logging.getLogger(__name__)

PC_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-1-grd"
LOOKBACK_DAYS = 36
MAX_PIXELS_PER_SIDE = 256


def _read_vv_band(
    href: str, aoi_bbox: tuple[float, ...], item_bbox: list[float],
    width: int, height: int,
) -> np.ndarray:
    """Read VV band from a COG, computing the window from geographic bboxes.

    Sentinel-1 GRD COGs on Planetary Computer lack embedded CRS, so we
    map the AOI bbox onto the image grid using the STAC item's geographic bbox.
    """
    with rasterio.open(href) as src:
        img_h, img_w = src.shape

        ib = item_bbox  # [min_lon, min_lat, max_lon, max_lat]
        lon_span = ib[2] - ib[0]
        lat_span = ib[3] - ib[1]

        if lon_span <= 0 or lat_span <= 0:
            return np.zeros((height, width), dtype=np.float64)

        col_start = max(0, (aoi_bbox[0] - ib[0]) / lon_span * img_w)
        col_end = min(img_w, (aoi_bbox[2] - ib[0]) / lon_span * img_w)
        row_start = max(0, (ib[3] - aoi_bbox[3]) / lat_span * img_h)
        row_end = min(img_h, (ib[3] - aoi_bbox[1]) / lat_span * img_h)

        window = Window(
            col_off=int(col_start), row_off=int(row_start),
            width=max(1, int(col_end - col_start)),
            height=max(1, int(row_end - row_start)),
        )

        data = src.read(
            1, window=window, out_shape=(height, width),
            resampling=Resampling.bilinear,
        )
    return data.astype(np.float64)


def _pixel_dims(bbox: tuple[float, ...]) -> tuple[int, int]:
    """Calculate download pixel dimensions, capped at MAX_PIXELS_PER_SIDE."""
    deg_per_m = 1.0 / 111_320
    resolution_m = 10
    w = int((bbox[2] - bbox[0]) / (deg_per_m * resolution_m))
    h = int((bbox[3] - bbox[1]) / (deg_per_m * resolution_m))
    scale = min(1.0, MAX_PIXELS_PER_SIDE / max(w, h, 1))
    return max(64, int(w * scale)), max(64, int(h * scale))


def _fetch_sar_pair(aoi: AOI, date_range: dict | None = None) -> dict:
    """Search Planetary Computer for a same-orbit Sentinel-1 pair."""
    catalog = pystac_client.Client.open(
        PC_STAC_URL, modifier=planetary_computer.sign_inplace
    )
    bbox_list = list(aoi.bbox)
    now = datetime.now(timezone.utc)
    if date_range:
        search_start = date_range["start"]
        search_end = date_range["end"]
    else:
        search_start = now - timedelta(days=LOOKBACK_DAYS)
        search_end = now

    search = catalog.search(
        collections=[COLLECTION],
        bbox=bbox_list,
        datetime=f"{search_start.strftime('%Y-%m-%d')}/{search_end.strftime('%Y-%m-%d')}",
        query={"sar:instrument_mode": {"eq": "IW"}},
        max_items=50,
        sortby=[{"field": "datetime", "direction": "desc"}],
    )
    items = list(search.items())

    if len(items) < 2:
        logger.warning(
            "Only %d Sentinel-1 scenes found for AOI %s (need 2)",
            len(items), aoi.id,
        )
        return {"error": "no_orbit_pair"}

    # Group by relative orbit + pass direction
    orbit_groups: dict[str, list] = {}
    for item in items:
        props = item.properties
        orbit = props.get("sat:relative_orbit")
        pass_dir = props.get("sat:orbit_state", "").upper()
        if orbit is None or not pass_dir:
            continue
        # Only keep items with VV asset
        if "vv" not in item.assets:
            continue
        key = f"{orbit}_{pass_dir}"
        orbit_groups.setdefault(key, []).append(item)

    # Find an orbit group with 2+ scenes, maximise temporal baseline
    best_pair = None
    best_baseline = 0
    for key, group in orbit_groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda it: it.datetime)
        after_item = group[-1]
        before_item = group[0]
        baseline = (after_item.datetime - before_item.datetime).days
        if baseline > best_baseline:
            best_baseline = baseline
            best_pair = (before_item, after_item)

    if best_pair is None:
        logger.warning("No same-orbit pair found for AOI %s", aoi.id)
        return {"error": "no_orbit_pair"}

    before_item, after_item = best_pair
    before_props = before_item.properties
    after_props = after_item.properties

    w, h = _pixel_dims(aoi.bbox)
    bbox_tuple = tuple(aoi.bbox)

    before_href = before_item.assets["vv"].href
    after_href = after_item.assets["vv"].href

    logger.info(
        "Downloading SAR pair: %s -> %s (baseline %dd, orbit %s %s)",
        before_item.datetime.strftime("%Y-%m-%d"),
        after_item.datetime.strftime("%Y-%m-%d"),
        best_baseline,
        before_props.get("sat:relative_orbit"),
        before_props.get("sat:orbit_state", ""),
    )

    before_data = _read_vv_band(
        before_href, bbox_tuple, list(before_item.bbox), w, h
    )
    after_data = _read_vv_band(
        after_href, bbox_tuple, list(after_item.bbox), w, h
    )

    return {
        "before_image": before_data,
        "after_image": after_data,
        "before_scene": {
            "datetime": before_item.datetime.isoformat(),
            "orbit_number": before_props.get("sat:relative_orbit"),
            "pass_direction": before_props.get("sat:orbit_state", ""),
        },
        "after_scene": {
            "datetime": after_item.datetime.isoformat(),
            "orbit_number": after_props.get("sat:relative_orbit"),
            "pass_direction": after_props.get("sat:orbit_state", ""),
        },
        "temporal_baseline_days": best_baseline,
        "bbox": bbox_list,
        "error": None,
    }


async def ingest(aoi: AOI, date_range: dict | None = None) -> dict:
    """Pull Sentinel-1 GRD before/after pair via Planetary Computer STAC."""
    return await asyncio.to_thread(_fetch_sar_pair, aoi, date_range)
