"""Sentinel-1 SAR coherence change detection layer."""

from core.models import AOI, Contact
from layers.base import BaseLayer
from layers.sar.detect import detect
from layers.sar.ingest import ingest


class SARLayer(BaseLayer):
    """Sentinel-1 GRD amplitude correlation change detection."""

    source_type = "sar"

    async def ingest(self, aoi: AOI) -> dict:
        """Pull before/after Sentinel-1 GRD pair via Planetary Computer."""
        return await ingest(aoi)

    async def detect(self, aoi: AOI, raw_data: dict) -> list[Contact]:
        """Run SAR correlation change detection."""
        return await detect(aoi, raw_data)

    def _base_confidence(self) -> float:
        """Base SAR confidence."""
        return 0.60
