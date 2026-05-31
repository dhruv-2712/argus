"""Integration test for SAR layer + three-source fusion test.

Run: python -m layers.sar.test_sar
No credentials needed — uses Planetary Computer (public STAC).
"""

import asyncio
import logging
from datetime import datetime, timezone

from core.fusion.engine import FusionEngine
from core.models import AOI
from layers.events import EventsLayer
from layers.optical import OpticalLayer
from layers.sar import SARLayer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


async def main() -> None:
    """Run SAR layer on Ladakh, then three-source fusion test."""
    aoi = AOI(
        id="test-ladakh-sar",
        name="Ladakh",
        bbox=(77.5, 33.5, 78.5, 34.5),
        domain="land",
        created_at=datetime.now(timezone.utc),
    )

    # ── SAR standalone test ──
    print("=" * 60)
    print("SAR LAYER TEST")
    print("=" * 60)
    sar = SARLayer()
    print(f"AOI: {aoi.name} | bbox: {aoi.bbox}")
    print(f"source_type: {sar.source_type} | base_confidence: {sar._base_confidence()}")

    sar_contacts = await sar.run(aoi)
    print(f"\nSAR detected {len(sar_contacts)} contact(s)")
    for c in sar_contacts:
        print(
            f"  [{c.detection_type}] conf={c.confidence:.2f} "
            f"| ({c.lat:.4f}, {c.lon:.4f}) "
            f"| pixels={c.raw_evidence['cluster_pixels']} "
            f"| drop={c.raw_evidence['correlation_drop']:.3f}"
        )

    # ── Three-source fusion test ──
    print(f"\n{'=' * 60}")
    print("THREE-SOURCE FUSION TEST")
    print("=" * 60)

    print("\nRunning optical, events, SAR concurrently...")
    optical_task = OpticalLayer().run(aoi)
    events_task = EventsLayer().run(aoi)
    sar_task = SARLayer().run(aoi)

    results = await asyncio.gather(
        optical_task, events_task, sar_task, return_exceptions=True
    )

    layer_names = ["optical", "events", "sar"]
    all_contacts = []
    for name, result in zip(layer_names, results):
        if isinstance(result, Exception):
            print(f"  {name}: FAILED — {result}")
        else:
            print(f"  {name}: {len(result)} contact(s)")
            all_contacts.extend(result)

    print(f"\nTotal contacts: {len(all_contacts)}")
    engine = FusionEngine()
    fused = engine.fuse(all_contacts)

    print(f"Fused into {len(fused)} FusedContact(s)\n")
    for fc in fused:
        print(
            f"  sources={fc.sources} | conf={fc.confidence:.2f} "
            f"| threat={fc.threat_level} | types={fc.detection_types}"
        )
        print(f"  summary: {fc.summary}")
        if len(fc.sources) > 1:
            print("  ** CORROBORATED — multi-source detection **")
        print()


if __name__ == "__main__":
    asyncio.run(main())
