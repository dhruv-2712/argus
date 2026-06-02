"""End-to-end pipeline demonstration — all sources → detection → fusion (DS).

Pushes synthetic raw data from every layer through the REAL detect() functions
and the REAL FusionEngine, at one location (Galwan) so they corroborate.
No network required. Run: python scripts/pipeline_demo.py
"""

import asyncio
from datetime import datetime, timedelta, timezone

import uuid
from core.models import AOI, Contact
from core.fusion.engine import FusionEngine, explain_confidence, SOURCE_RELIABILITY
from core.fusion.dempster_shafer import fuse_ds, bpa_from_contact
from layers.thermal.detect import detect as thermal_detect
from layers.flights.detect import detect as flights_detect


def contact(source, conf, dtype, lat, lon, desc):
    """A detection-pipeline output Contact (what optical/sar/events emit)."""
    return Contact(id=str(uuid.uuid4()), aoi_id="galwan", timestamp=NOW,
                   source=source, confidence=conf, detection_type=dtype,
                   lat=lat, lon=lon, description=desc)

NOW = datetime.now(timezone.utc)
LAT, LON = 34.497, 80.375  # Galwan Valley construction site

AOI_GALWAN = AOI(id="galwan", name="Galwan Valley",
                 bbox=(79.8, 34.2, 80.6, 34.8), domain="land", created_at=NOW)


def bar(title):
    print(f"\n{'=' * 64}\n  {title}\n{'=' * 64}")


async def main():
    bar("STAGE 1-2 — SOURCE DATA → DETECTION PIPELINES")
    contacts = []

    # --- Thermal (FIRMS) + Flights (OpenSky): run the REAL detect() ---
    thermal_raw = {"hotspots": [{"lat": LAT - 0.001, "lon": LON + 0.002,
                                 "bright_ti4": 361.0, "frp": 120.0,
                                 "confidence": "high", "daynight": "N",
                                 "acq_date": "2026-06-01", "acq_time": "2014"}]}
    flights_raw = {"aircraft": [{"icao24": "ae1234", "callsign": "FORTE11",
                                 "origin_country": "United States",
                                 "lat": LAT + 0.01, "lon": LON + 0.01,
                                 "baro_altitude": 11500.0, "geo_altitude": 11500.0,
                                 "on_ground": False, "velocity": 230.0,
                                 "heading": 270.0, "vertical_rate": 0.0, "squawk": "1234"}]}

    for name, fn, raw in [
        ("THERMAL (NASA FIRMS) [real detect()]", thermal_detect, thermal_raw),
        ("FLIGHTS (OpenSky)    [real detect()]", flights_detect, flights_raw),
    ]:
        out = await fn(AOI_GALWAN, raw)
        contacts.extend(out)
        for c in out:
            print(f"  {name} -> conf {c.confidence:.2f}  {c.detection_type}")

    # --- Optical / SAR / Events: detection-pipeline OUTPUT contacts ---
    #     (optical/sar detect() consume raw Sentinel image arrays; here we
    #      show what those pipelines emit so fusion has all 6 sources)
    pipeline_out = [
        ("OPTICAL (Sentinel-2)", contact("optical", 0.62, "construction",
            LAT, LON, "SSIM drop 0.42 + NDVI -0.3 over 4200 m^2")),
        ("SAR     (Sentinel-1)", contact("sar", 0.60, "terrain_clearance",
            LAT + 0.002, LON - 0.001, "amplitude-correlation disturbance, 12d baseline")),
        ("EVENTS  (GDELT/ACLED)", contact("events", 0.55, "event_spike",
            LAT + 0.003, LON, "spike in border-incident reporting")),
    ]
    for name, c in pipeline_out:
        contacts.append(c)
        print(f"  {name} -> conf {c.confidence:.2f}  {c.detection_type}")

    print(f"\n  {len(contacts)} raw single-source contacts entering the fusion engine")

    bar("STAGE 3 — FUSION ENGINE (cluster + Dempster-Shafer + corroboration)")
    engine = FusionEngine()
    fused = engine.fuse(contacts)
    for fc in fused:
        print(f"  FUSED  conf={fc.confidence:.3f}  threat={fc.threat_level.upper()}")
        print(f"         sources={fc.sources}")
        print(f"         {fc.summary}")

    bar("DEMPSTER-SHAFER — the actual evidence math for this cluster")
    raw_dicts = [{"source": c.source, "confidence": c.confidence} for c in contacts]
    print("  Per-sensor Basic Probability Assignments (mass over {THREAT, BENIGN, Θ}):")
    for d in raw_dicts:
        b = bpa_from_contact(d["confidence"], SOURCE_RELIABILITY[d["source"]])
        print(f"    {d['source']:8s} conf={d['confidence']:.2f} rel={SOURCE_RELIABILITY[d['source']]:.2f}"
              f"  → m(THREAT)={b.threat:.3f}  m(BENIGN)={b.benign:.3f}  m(Θ)={b.uncertain:.3f}")

    ds = fuse_ds(raw_dicts, SOURCE_RELIABILITY)
    print(f"\n  Combined via Dempster's rule across all {ds['n_sensors']} sensors:")
    print(f"    DS threat belief m(THREAT) = {ds['ds_confidence']:.4f}")
    print(f"    residual ignorance m(Θ)    = {ds['uncertainty']:.4f}")
    print(f"    mean inter-sensor conflict = {ds['avg_conflict']:.4f}")

    exp = explain_confidence(raw_dicts)
    print(f"\n  Final blended score = 0.4 * DS({ds['ds_confidence']:.3f}) + 0.6 * corroboration")
    print(f"    weighted base      = {exp['weighted_base']:.3f}")
    print(f"    corroboration mult = x{exp['corroboration_multiplier']}  ({exp['corroboration_label']})")
    print(f"    → fused confidence = {fused[0].confidence:.3f}  [{fused[0].threat_level.upper()}]")

    bar("STAGE 4-6 — TERRAIN / REPORT / C2  (downstream consumers)")
    print("  TERRAIN  : GET /intel/terrain?lat&lon → key terrain, avenues of")
    print("             approach, LOS radius (needs Open-Elevation network call)")
    print("  REPORT   : reports/generator.py renders these FusedContacts to PDF")
    print("  C2 UI    : WebSocket pushes the fused contact to the live map")
    print(f"\n  Single SIGINT spike alone would score: {0.55 * SOURCE_RELIABILITY['events'] * 0.6:.2f} (LOW)")
    print(f"  Five corroborating sensors here scored: {fused[0].confidence:.2f} ({fused[0].threat_level.upper()})")


if __name__ == "__main__":
    asyncio.run(main())
