from layers.base import BaseLayer
from layers.thermal.ingest import fetch_thermal
from layers.thermal.detect import detect as _detect
from core.models import AOI, Contact


class ThermalLayer(BaseLayer):
    """NASA FIRMS VIIRS thermal anomaly layer."""

    source_type = "thermal"

    async def ingest(self, aoi: AOI) -> dict:
        return await fetch_thermal(aoi)

    async def detect(self, aoi: AOI, raw_data: dict) -> list[Contact]:
        return await _detect(aoi, raw_data)
