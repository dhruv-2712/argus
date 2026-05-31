"""Abstract base class that all intelligence layers implement."""

from abc import ABC, abstractmethod

from core.models import AOI, Contact


class BaseLayer(ABC):
    """Base layer interface for data ingestion and detection."""

    source_type: str

    @abstractmethod
    async def ingest(self, aoi: AOI) -> dict:
        """Pull raw data for this AOI. Returns raw source data."""

    @abstractmethod
    async def detect(self, aoi: AOI, raw_data: dict) -> list[Contact]:
        """Run detection on raw data. Returns list of Contact objects."""

    async def run(self, aoi: AOI) -> list[Contact]:
        """Full pipeline: ingest -> detect -> return contacts."""
        raw = await self.ingest(aoi)
        contacts = await self.detect(aoi, raw)
        return contacts

    def _base_confidence(self) -> float:
        """Base confidence weight for this source. Override per layer."""
        return 0.5
