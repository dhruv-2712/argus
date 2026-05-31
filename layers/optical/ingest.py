"""Sentinel-2 imagery ingestion via Element84 Earth Search (open STAC).

Ported from IRIS sentinel_client.py — uses the free, credential-less
Earth Search STAC API backed by Sentinel-2 L2A COGs on AWS.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds

from core.models import AOI

logger = logging.getLogger(__name__)

EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"
SENTINEL2_COLLECTION = "sentinel-2-l2a"

BANDS = ["B02", "B03", "B04", "B08", "B11"]
BAND_ASSETS = {
    "B02": ["blue", "B02"],
    "B03": ["green", "B03"],
    "B04": ["red", "B04"],
    "B08": ["nir", "nir08", "B08"],
    "B11": ["swir16", "B11"],
}
ARGUS_BAND_MAP = {"B02": "B2", "B03": "B3", "B04": "B4", "B08": "B8", "B11": "B11"}

CLOUD_COVER_MAX = 20
LOOKBACK_DAYS = 30
MAX_PIXELS_PER_SIDE = 256


def _asset_href(item: object, band: str) -> str | None:
    """Resolve the COG href for a band from a STAC item."""
    for key in BAND_ASSETS[band]:
        if key in item.assets:
            return item.assets[key].href
    return None


def _read_band(
    href: str, bbox: tuple[float, ...], width: int, height: int, band: str
) -> np.ndarray:
    """Read a single band from a COG, cropped and resampled to target size."""
    rs = Resampling.bilinear
    try:
        with rasterio.open(href) as src:
            native_bbox = transform_bounds("EPSG:4326", src.crs, *bbox)
            window = src.window(*native_bbox)
            data = src.read(
                1, window=window, out_shape=(height, width), resampling=rs
            )
        return data.astype(np.float64)
    except Exception as exc:
        logger.warning("Failed to read %s: %s — filling zeros", band, exc)
        return np.zeros((height, width), dtype=np.float64)


def _pixel_dims(bbox: tuple[float, ...]) -> tuple[int, int]:
    """Calculate download pixel dimensions, capped at MAX_PIXELS_PER_SIDE."""
    deg_per_m = 1.0 / 111_320
    resolution_m = 10
    w = int((bbox[2] - bbox[0]) / (deg_per_m * resolution_m))
    h = int((bbox[3] - bbox[1]) / (deg_per_m * resolution_m))
    scale = min(1.0, MAX_PIXELS_PER_SIDE / max(w, h, 1))
    return max(64, int(w * scale)), max(64, int(h * scale))


def _fetch_image_pair(aoi: AOI, date_range: dict | None = None) -> dict:
    """Search STAC catalog and download before/after band arrays."""
    import pystac_client

    catalog = pystac_client.Client.open(EARTH_SEARCH_URL)
    bbox_list = list(aoi.bbox)
    now = datetime.now(timezone.utc)

    if date_range:
        after_start = date_range["after_start"]
        after_end = date_range["after_end"]
        before_start = date_range["before_start"]
        before_end = date_range["before_end"]
    else:
        after_end = now
        after_start = now - timedelta(days=LOOKBACK_DAYS)
        before_end = now - timedelta(hours=aoi.revisit_hours)
        before_start = before_end - timedelta(days=LOOKBACK_DAYS)

    def _search(start: datetime, end: datetime) -> list:
        """Run a STAC search and return items sorted by cloud cover."""
        results = catalog.search(
            collections=[SENTINEL2_COLLECTION],
            bbox=bbox_list,
            datetime=f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}",
            query={"eo:cloud_cover": {"lt": CLOUD_COVER_MAX}},
            max_items=20,
        )
        items = list(results.items())
        items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100))
        return items

    after_items = _search(after_start, after_end)
    before_items = _search(before_start, before_end)

    if not after_items or not before_items:
        logger.warning("No cloud-free Sentinel-2 imagery for AOI %s", aoi.id)
        return {"error": "no_clear_image"}

    after_item = after_items[0]
    before_item = before_items[0]

    after_cloud = after_item.properties.get("eo:cloud_cover", 0)
    before_cloud = before_item.properties.get("eo:cloud_cover", 0)
    after_date = after_item.datetime.replace(tzinfo=timezone.utc)
    before_date = before_item.datetime.replace(tzinfo=timezone.utc)

    w, h = _pixel_dims(aoi.bbox)
    bbox_tuple = tuple(aoi.bbox)

    after_arrays: dict[str, np.ndarray] = {}
    before_arrays: dict[str, np.ndarray] = {}

    for band in BANDS:
        after_href = _asset_href(after_item, band)
        before_href = _asset_href(before_item, band)
        argus_name = ARGUS_BAND_MAP[band]

        if after_href:
            after_arrays[argus_name] = _read_band(after_href, bbox_tuple, w, h, band)
        else:
            after_arrays[argus_name] = np.zeros((h, w), dtype=np.float64)

        if before_href:
            before_arrays[argus_name] = _read_band(before_href, bbox_tuple, w, h, band)
        else:
            before_arrays[argus_name] = np.zeros((h, w), dtype=np.float64)

    return {
        "before_image": before_arrays,
        "after_image": after_arrays,
        "metadata": {
            "before_date": before_date.isoformat(),
            "after_date": after_date.isoformat(),
            "before_cloud_pct": before_cloud,
            "after_cloud_pct": after_cloud,
            "bbox": bbox_list,
        },
    }


async def ingest(aoi: AOI, date_range: dict | None = None) -> dict:
    """Pull Sentinel-2 before/after imagery for an AOI via Element84 STAC."""
    return await asyncio.to_thread(_fetch_image_pair, aoi, date_range)
