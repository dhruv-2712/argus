"""Quick integration test for the optical layer.

Run: python -m layers.optical.test_optical
Requires: GEE authentication (run `python -c "import ee; ee.Authenticate()"` first)
"""

import asyncio
import logging
from datetime import datetime, timezone

from core.models import AOI
from layers.optical import OpticalLayer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


async def main() -> None:
    """Run optical layer on a Ladakh AOI."""
    aoi = AOI(
        id="test-ladakh-001",
        name="Ladakh Monitoring Zone",
        bbox=(77.5, 33.5, 78.5, 34.5),
        domain="land",
        created_at=datetime.now(timezone.utc),
    )

    layer = OpticalLayer()
    print(f"Running optical layer for: {aoi.name}")
    print(f"  bbox:            {aoi.bbox}")
    print(f"  source_type:     {layer.source_type}")
    print(f"  base_confidence: {layer._base_confidence()}")
    print(f"  revisit_hours:   {aoi.revisit_hours}")
    print()

    try:
        contacts = await layer.run(aoi)
    except Exception as exc:
        print(f"Error: {exc}")
        print()
        print("If this is an authentication error:")
        print('  1. python -c "import ee; ee.Authenticate()"')
        print("  2. Set GEE_PROJECT=<your-project> in .env")
        return

    print(f"Detected {len(contacts)} contact(s)")
    for c in contacts:
        print(f"\n--- Contact {c.id[:8]} ---")
        print(f"  Type:        {c.detection_type}")
        print(f"  Location:    ({c.lat}, {c.lon})")
        print(f"  Confidence:  {c.confidence:.2f}")
        print(f"  Source:      {c.source}")
        print(f"  Description: {c.description}")
        for k, v in c.raw_evidence.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
