from layers.base import BaseLayer
from layers.flights.ingest import fetch_flights
from layers.flights.detect import detect as _detect
from core.models import AOI, Contact


class FlightsLayer(BaseLayer):
    """OpenSky Network live aircraft tracking layer."""

    source_type = "flights"

    async def ingest(self, aoi: AOI) -> dict:
        return await fetch_flights(aoi)

    async def detect(self, aoi: AOI, raw_data: dict) -> list[Contact]:
        return await _detect(aoi, raw_data)
