"""GDELT + ACLED conflict event detection layer."""

from core.models import AOI, Contact
from layers.base import BaseLayer
from layers.events.detect import detect
from layers.events.ingest import ingest


class EventsLayer(BaseLayer):
    """Multi-source conflict event detection from GDELT and ACLED."""

    source_type = "events"

    async def ingest(self, aoi: AOI) -> dict:
        """Fetch events from GDELT and ACLED concurrently."""
        return await ingest(aoi)

    async def detect(self, aoi: AOI, raw_data: dict) -> list[Contact]:
        """Run event spike detection on fetched data."""
        return await detect(aoi, raw_data)

    def _base_confidence(self) -> float:
        """Base events confidence — softer signal than optical."""
        return 0.45
