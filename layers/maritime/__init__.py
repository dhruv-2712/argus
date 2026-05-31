"""AIS vessel tracking and anomaly detection layer."""

from core.models import AOI, Contact
from layers.base import BaseLayer
from layers.maritime.detect import detect
from layers.maritime.ingest import ingest


class MaritimeLayer(BaseLayer):
    """AIS-based vessel anomaly detection: loitering, formations, dark vessels."""

    source_type = "maritime"

    async def ingest(self, aoi: AOI) -> dict:
        """Fetch AIS vessel data from AISHub."""
        return await ingest(aoi)

    async def detect(self, aoi: AOI, raw_data: dict) -> list[Contact]:
        """Run loitering, formation, and dark vessel detectors."""
        return await detect(aoi, raw_data)

    def _base_confidence(self) -> float:
        """Base maritime confidence."""
        return 0.55
