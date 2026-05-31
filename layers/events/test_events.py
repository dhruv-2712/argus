"""Integration test for the events layer + first fusion test.

Run: python -m layers.events.test_events
No GEE auth needed — uses GDELT (free) and ACLED (key in .env).
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from core.fusion.engine import FusionEngine
from core.models import AOI
from layers.events import EventsLayer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def run_events_layer(aoi: AOI) -> list:
    """Run the events layer and print results."""
    layer = EventsLayer()
    print(f"\n{'='*60}")
    print(f"Running events layer for: {aoi.name}")
    print(f"  bbox: {aoi.bbox}")
    print(f"  source_type: {layer.source_type}")
    print(f"  base_confidence: {layer._base_confidence()}")

    raw_data = await layer.ingest(aoi)

    gdelt_count = len(raw_data.get("gdelt_events", []))
    acled_count = len(raw_data.get("acled_events", []))
    print(f"\n  Raw events: {gdelt_count} GDELT, {acled_count} ACLED")

    if raw_data.get("gdelt_error"):
        print(f"  GDELT error: {raw_data['gdelt_error']}")
    if raw_data.get("acled_error"):
        print(f"  ACLED error: {raw_data['acled_error']}")

    if raw_data["gdelt_events"]:
        print(f"\n  Sample GDELT event:")
        print(f"    {json.dumps(raw_data['gdelt_events'][0], indent=4, default=str)}")

    if raw_data["acled_events"]:
        print(f"\n  Sample ACLED event:")
        print(f"    {json.dumps(raw_data['acled_events'][0], indent=4, default=str)}")

    contacts = await layer.detect(aoi, raw_data)
    print(f"\n  Detected {len(contacts)} contact(s)")
    for c in contacts:
        src = c.raw_evidence.get("source", "?")
        print(
            f"    [{src}] {c.detection_type} | conf={c.confidence:.2f} "
            f"| ({c.lat:.2f}, {c.lon:.2f}) | {c.description[:80]}"
        )

    return contacts


async def main() -> None:
    """Test two AOIs then run the fusion engine."""
    # AOI 1: Ladakh
    ladakh = AOI(
        id="test-ladakh-events",
        name="Ladakh Monitoring Zone",
        bbox=(77.5, 33.5, 78.5, 34.5),
        domain="land",
        created_at=datetime.now(timezone.utc),
    )

    # AOI 2: Eastern Ukraine (known conflict zone)
    ukraine = AOI(
        id="test-ukraine-events",
        name="Eastern Ukraine Conflict Zone",
        bbox=(36.0, 47.0, 39.0, 49.5),
        domain="land",
        created_at=datetime.now(timezone.utc),
    )

    ladakh_contacts = await run_events_layer(ladakh)
    ukraine_contacts = await run_events_layer(ukraine)

    # ── Fusion test ──
    print(f"\n{'='*60}")
    print("FUSION ENGINE TEST")
    print(f"{'='*60}")

    # Optionally add optical contacts
    optical_contacts = []
    try:
        from layers.optical import OpticalLayer
        print("\nFetching optical contacts for Ladakh (STAC)...")
        optical_contacts = await OpticalLayer().run(ladakh)
        print(f"  Optical contacts: {len(optical_contacts)}")
    except Exception as exc:
        print(f"  Optical layer skipped: {exc}")

    all_contacts = ladakh_contacts + optical_contacts
    print(f"\nFusing {len(all_contacts)} total contacts...")

    engine = FusionEngine()
    fused = engine.fuse(all_contacts)

    print(f"Produced {len(fused)} FusedContact(s)\n")
    for fc in fused:
        print(
            f"  FusedContact | sources={fc.sources} | conf={fc.confidence:.2f} "
            f"| threat={fc.threat_level} | types={fc.detection_types}"
        )
        print(f"    summary: {fc.summary}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
