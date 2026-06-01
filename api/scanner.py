"""Scan orchestrator — runs all layers concurrently and fuses results."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.fusion.engine import FusionEngine
from core.fusion.temporal import TemporalCorrelator
from core.models import AOI, Contact, FusedContact
from db.database import ContactRow, FusedContactRow, AOIRow, async_session
from layers.events import EventsLayer
from layers.maritime import MaritimeLayer
from layers.optical import OpticalLayer
from layers.sar import SARLayer

logger = logging.getLogger(__name__)


class ScanOrchestrator:
    """Run intelligence layers concurrently, fuse, and persist results."""

    def __init__(self) -> None:
        self.layers = {
            "optical": OpticalLayer(),
            "sar": SARLayer(),
            "events": EventsLayer(),
            "maritime": MaritimeLayer(),
        }
        self.fusion = FusionEngine()
        self.temporal = TemporalCorrelator()

    async def scan(
        self, aoi: AOI, layers: list[str] | None = None
    ) -> dict:
        """Run selected layers, fuse contacts, persist to DB."""
        active = layers or list(self.layers.keys())
        tasks = {
            name: layer.run(aoi)
            for name, layer in self.layers.items()
            if name in active
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        all_contacts: list[Contact] = []
        layer_errors: dict[str, str] = {}
        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                layer_errors[name] = str(result)
                logger.error("Layer %s failed: %s", name, result)
            else:
                all_contacts.extend(result)

        fused = self.fusion.fuse(all_contacts)

        # Temporal correlation: link this scan's contacts to historical tracks,
        # classify lifecycle, and calibrate confidence by persistence.
        now = datetime.now(timezone.utc)
        history = await self._load_history(aoi.id)
        self.temporal.correlate(fused, history, now)

        # Run SPECTER on contacts above threshold
        specter_results: dict[str, dict] = {}
        from core.simulation.ocoka import Specter
        specter = Specter()
        for fc in fused:
            try:
                result = await specter.analyze(aoi, fc)
                if result:
                    fc.simulation_run = True
                    specter_results[fc.id] = result
            except Exception as exc:
                logger.warning("SPECTER failed for %s: %s", fc.id, exc)

        await self._persist(aoi, all_contacts, fused)

        return {
            "fused_contacts": fused,
            "raw_contact_count": len(all_contacts),
            "layer_errors": layer_errors,
            "layers_run": list(tasks.keys()),
            "specter_results": specter_results,
        }

    async def _load_history(self, aoi_id: str, limit: int = 500) -> list[dict]:
        """Load prior fused-contact records for an AOI for temporal correlation."""
        async with async_session() as session:
            result = await session.execute(
                select(FusedContactRow)
                .where(FusedContactRow.aoi_id == aoi_id)
                .order_by(FusedContactRow.timestamp.desc())
                .limit(limit)
            )
            rows = result.scalars().all()

        return [
            {
                "track_id": r.track_id or r.id,
                "lat": r.lat,
                "lon": r.lon,
                "confidence": r.confidence,
                "first_seen": r.first_seen or r.timestamp,
                "observation_count": r.observation_count or 1,
                "timestamp": r.timestamp,
            }
            for r in rows
        ]

    async def _persist(
        self,
        aoi: AOI,
        contacts: list[Contact],
        fused: list[FusedContact],
    ) -> None:
        """Write raw and fused contacts to DB, update AOI last_scan."""
        async with async_session() as session:
            for c in contacts:
                session.add(ContactRow(
                    id=c.id, aoi_id=c.aoi_id,
                    timestamp=c.timestamp, source=c.source,
                    confidence=c.confidence, detection_type=c.detection_type,
                    lat=c.lat, lon=c.lon, description=c.description,
                    raw_evidence=json.dumps(c.raw_evidence),
                    fused=c.fused, threat_level=c.threat_level,
                ))

            for fc in fused:
                session.add(FusedContactRow(
                    id=fc.id, aoi_id=fc.aoi_id,
                    constituent_contacts=json.dumps(fc.constituent_contacts),
                    sources=json.dumps(fc.sources),
                    confidence=fc.confidence,
                    detection_types=json.dumps(fc.detection_types),
                    lat=fc.lat, lon=fc.lon, timestamp=fc.timestamp,
                    threat_level=fc.threat_level, summary=fc.summary,
                    simulation_run=fc.simulation_run,
                    track_id=fc.track_id, first_seen=fc.first_seen,
                    last_seen=fc.last_seen, observation_count=fc.observation_count,
                    lifecycle=fc.lifecycle, confidence_delta=fc.confidence_delta,
                    persistence_score=fc.persistence_score,
                ))

            await session.execute(
                update(AOIRow)
                .where(AOIRow.id == aoi.id)
                .values(active=True)
            )
            await session.commit()

        logger.info(
            "Persisted %d contacts + %d fused for AOI %s",
            len(contacts), len(fused), aoi.id,
        )
