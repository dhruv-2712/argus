"""Sentinel-2 optical change detection layer."""

from core.models import AOI, Contact
from layers.base import BaseLayer
from layers.optical.detect import detect
from layers.optical.ingest import ingest


class OpticalLayer(BaseLayer):
    """Sentinel-2 SSIM + spectral band change detection."""

    source_type = "optical"

    async def ingest(self, aoi: AOI) -> dict:
        """Pull before/after Sentinel-2 imagery via GEE."""
        return await ingest(aoi)

    async def detect(self, aoi: AOI, raw_data: dict) -> list[Contact]:
        """Run SSIM + band anomaly detection on imagery pair."""
        return await detect(aoi, raw_data)

    def _base_confidence(self) -> float:
        """Base optical confidence."""
        return 0.55
