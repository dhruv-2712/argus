"""Integration test for the maritime layer + four-source fusion test.

Run: python -m layers.maritime.test_maritime
Uses synthetic vessel data (AISHub credentials not expected).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from core.fusion.engine import FusionEngine
from core.models import AOI
from layers.events import EventsLayer
from layers.maritime import MaritimeLayer
from layers.maritime.detect import detect
from layers.optical import OpticalLayer
from layers.sar import SARLayer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


def _make_synthetic_vessels() -> list[dict]:
    """Generate 8 synthetic vessels: 3 in formation, 1 loitering, 1 dark, 3 normal."""
    now = datetime.now(timezone.utc)

    # 3 vessels in formation — heading NE ~045, speed ~12kt, within 3nm
    formation = [
        {
            "mmsi": "211000001", "vessel_name": "CARGO ALPHA",
            "vessel_type": 70, "lat": 20.0, "lon": 65.0,
            "speed": 12.0, "heading": 45.0, "timestamp": now,
            "status": 0, "track": [],
        },
        {
            "mmsi": "211000002", "vessel_name": "CARGO BRAVO",
            "vessel_type": 71, "lat": 20.02, "lon": 65.03,
            "speed": 11.5, "heading": 43.0, "timestamp": now,
            "status": 0, "track": [],
        },
        {
            "mmsi": "211000003", "vessel_name": "TANKER CHARLIE",
            "vessel_type": 80, "lat": 19.98, "lon": 65.01,
            "speed": 12.5, "heading": 47.0, "timestamp": now,
            "status": 0, "track": [],
        },
    ]

    # 1 loitering tanker — speed < 2kt, not near port
    loiterer = {
        "mmsi": "311000004", "vessel_name": "TANKER DELTA",
        "vessel_type": 81, "lat": 18.5, "lon": 67.0,
        "speed": 0.3, "heading": 180.0, "timestamp": now,
        "status": 1,
        "track": [
            {"lat": 18.50, "lon": 67.00, "timestamp": now - timedelta(hours=6), "speed": 0.5},
            {"lat": 18.50, "lon": 67.01, "timestamp": now - timedelta(hours=4), "speed": 0.2},
            {"lat": 18.50, "lon": 67.00, "timestamp": now - timedelta(hours=2), "speed": 0.3},
            {"lat": 18.50, "lon": 67.00, "timestamp": now, "speed": 0.1},
        ],
    }

    # 1 dark vessel — has AIS gap > 4 hours in track
    dark = {
        "mmsi": "411000005", "vessel_name": "CARGO ECHO",
        "vessel_type": 72, "lat": 22.0, "lon": 63.0,
        "speed": 8.0, "heading": 270.0, "timestamp": now,
        "status": 0,
        "track": [
            {"lat": 22.0, "lon": 64.0, "timestamp": now - timedelta(hours=12), "speed": 10.0},
            {"lat": 22.0, "lon": 63.8, "timestamp": now - timedelta(hours=11), "speed": 10.0},
            # 6-hour gap (dark period)
            {"lat": 22.0, "lon": 63.2, "timestamp": now - timedelta(hours=5), "speed": 8.0},
            {"lat": 22.0, "lon": 63.0, "timestamp": now, "speed": 8.0},
        ],
    }

    # 3 normal vessels — different headings/speeds, no anomaly
    normals = [
        {
            "mmsi": "511000006", "vessel_name": "FISHING FOX",
            "vessel_type": 30, "lat": 16.5, "lon": 70.0,
            "speed": 6.0, "heading": 120.0, "timestamp": now,
            "status": 0, "track": [],
        },
        {
            "mmsi": "511000007", "vessel_name": "CARGO GOLF",
            "vessel_type": 70, "lat": 23.0, "lon": 68.0,
            "speed": 14.0, "heading": 90.0, "timestamp": now,
            "status": 0, "track": [],
        },
        {
            "mmsi": "511000008", "vessel_name": "TANKER HOTEL",
            "vessel_type": 80, "lat": 17.0, "lon": 62.0,
            "speed": 10.0, "heading": 315.0, "timestamp": now,
            "status": 0, "track": [],
        },
    ]

    return formation + [loiterer, dark] + normals


async def main() -> None:
    """Run maritime detectors on synthetic data, then four-source fusion."""
    maritime_aoi = AOI(
        id="test-arabian-sea",
        name="Arabian Sea Watch",
        bbox=(60.0, 15.0, 75.0, 25.0),
        domain="maritime",
        created_at=datetime.now(timezone.utc),
    )

    # ── Maritime standalone test with synthetic data ──
    print("=" * 60)
    print("MARITIME LAYER TEST (synthetic data)")
    print("=" * 60)

    vessels = _make_synthetic_vessels()
    raw_data = {
        "vessels": vessels,
        "fetch_timestamp": datetime.now(timezone.utc),
        "vessel_count": len(vessels),
        "error": None,
    }
    print(f"Synthetic vessels: {len(vessels)}")

    contacts = await detect(maritime_aoi, raw_data)
    print(f"\nDetected {len(contacts)} contact(s)")
    for c in contacts:
        atype = c.raw_evidence.get("anomaly_type", "?")
        print(
            f"  [{atype}] conf={c.confidence:.2f} "
            f"| ({c.lat:.2f}, {c.lon:.2f}) | {c.description}"
        )

    # Verify detectors
    anomaly_types = {c.raw_evidence["anomaly_type"] for c in contacts}
    print(f"\nAnomaly types detected: {anomaly_types}")
    assert "loitering" in anomaly_types, "Loitering detector should fire"
    assert "formation" in anomaly_types, "Formation detector should fire"
    assert "dark_vessel" in anomaly_types, "Dark vessel detector should fire"
    print("All three detectors fired correctly!")

    # ── Land AOI domain guard ──
    land_aoi = AOI(
        id="land-only", name="Land Test",
        bbox=(77.5, 33.5, 78.5, 34.5), domain="land",
        created_at=datetime.now(timezone.utc),
    )
    layer = MaritimeLayer()
    land_result = await layer.run(land_aoi)
    assert land_result == [], "Land AOI should return empty list"
    print("\nLand AOI domain guard: passed")

    # ── Four-source fusion test ──
    print(f"\n{'=' * 60}")
    print("FOUR-SOURCE FUSION TEST")
    print("=" * 60)

    mixed_aoi = AOI(
        id="test-ior-mixed",
        name="IOR Combined",
        bbox=(60.0, 15.0, 80.0, 30.0),
        domain="mixed",
        created_at=datetime.now(timezone.utc),
    )

    # Maritime: use synthetic data directly
    maritime_contacts = await detect(mixed_aoi, {
        "vessels": _make_synthetic_vessels(),
        "fetch_timestamp": datetime.now(timezone.utc),
        "vessel_count": 8,
        "error": None,
    })

    # Other layers: run live (will return few/no results but tests the pipeline)
    print("\nRunning optical, events, SAR concurrently on mixed AOI...")
    results = await asyncio.gather(
        OpticalLayer().run(mixed_aoi),
        EventsLayer().run(mixed_aoi),
        SARLayer().run(mixed_aoi),
        return_exceptions=True,
    )

    layer_names = ["optical", "events", "sar"]
    all_contacts = list(maritime_contacts)
    print(f"  maritime: {len(maritime_contacts)} contact(s) (synthetic)")
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
