"""Galwan Valley retrospective demo — May/June 2020.

Demonstrates ARGUS would have detected the PLA buildup prior to the
June 15 2020 clash using exclusively open-source satellite and OSINT data.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Ensure C:\argus is on path regardless of where the script is invoked from
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

from core.models import AOI, FusedContact, IntelReport
from core.fusion.engine import FusionEngine
from core.simulation.ocoka import Specter
from reports.generator import ReportGenerator

from layers.optical.ingest import ingest as optical_ingest
from layers.optical.detect import detect as optical_detect
from layers.sar.ingest import ingest as sar_ingest
from layers.sar.detect import detect as sar_detect
from layers.events.ingest import ingest as events_ingest
from layers.events.detect import detect as events_detect


GALWAN_AOI = AOI(
    id=str(uuid4()),
    name="Galwan Valley — Retrospective 2020",
    bbox=(79.8, 34.2, 80.6, 34.8),
    domain="land",
    created_at=datetime.now(timezone.utc),
    revisit_hours=24,
)

# Historical date windows around the buildup
OPTICAL_DATE_RANGE = {
    "before_start": datetime(2020, 5, 1, tzinfo=timezone.utc),
    "before_end":   datetime(2020, 5, 31, tzinfo=timezone.utc),
    "after_start":  datetime(2020, 6, 1, tzinfo=timezone.utc),
    "after_end":    datetime(2020, 6, 10, tzinfo=timezone.utc),
}

SAR_DATE_RANGE = {
    "start": datetime(2020, 5, 1, tzinfo=timezone.utc),
    "end":   datetime(2020, 6, 15, tzinfo=timezone.utc),
}

EVENTS_DATE_RANGE = {
    "start": datetime(2020, 5, 1, tzinfo=timezone.utc),
    "end":   datetime(2020, 6, 14, tzinfo=timezone.utc),
}


def _banner(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


async def run_layer(name: str, ingest_fn, detect_fn, aoi: AOI, date_range: dict) -> list:
    """Run a single layer's ingest + detect pipeline."""
    print(f"[{name.upper()}] ingesting...")
    try:
        raw = await ingest_fn(aoi, date_range)
        if raw.get("error"):
            print(f"[{name.upper()}] ingest returned: {raw['error']}")
            return []
        contacts = await detect_fn(aoi, raw)
        print(f"[{name.upper()}] {len(contacts)} contact(s) detected")
        return contacts
    except Exception as exc:
        print(f"[{name.upper()}] FAILED: {exc}")
        return []


async def main() -> None:
    aoi = GALWAN_AOI
    _banner("ARGUS — GALWAN VALLEY RETROSPECTIVE DEMO")
    print(f"AOI     : {aoi.name}")
    print(f"BBox    : {aoi.bbox}")
    print(f"Period  : May 1 – June 14, 2020")
    print(f"Goal    : Detect PLA buildup before June 15 clash")

    # ── Run layers concurrently ────────────────────────────────────────────
    _banner("LAYER EXECUTION")
    optical_task = asyncio.create_task(
        run_layer("optical", optical_ingest, optical_detect, aoi, OPTICAL_DATE_RANGE)
    )
    sar_task = asyncio.create_task(
        run_layer("sar", sar_ingest, sar_detect, aoi, SAR_DATE_RANGE)
    )
    events_task = asyncio.create_task(
        run_layer("events", events_ingest, events_detect, aoi, EVENTS_DATE_RANGE)
    )

    optical_contacts, sar_contacts, events_contacts = await asyncio.gather(
        optical_task, sar_task, events_task
    )

    all_contacts = optical_contacts + sar_contacts + events_contacts

    print(f"\nLayer summary:")
    print(f"  Optical  : {len(optical_contacts)} contact(s)")
    print(f"  SAR      : {len(sar_contacts)} contact(s)")
    print(f"  Events   : {len(events_contacts)} contact(s)")
    print(f"  Total raw: {len(all_contacts)} contact(s)")

    if not all_contacts:
        print("\n[WARN] No raw contacts detected — check API connectivity and data availability for 2020.")
        print("       GDELT coverage for Galwan June 2020 should be strong; optical may have cloud cover.")
        return

    # ── Fusion ────────────────────────────────────────────────────────────
    _banner("FUSION ENGINE")
    engine = FusionEngine()
    fused = engine.fuse(all_contacts)
    print(f"Fused {len(all_contacts)} raw contacts -> {len(fused)} fused contact(s)")

    for fc in sorted(fused, key=lambda x: x.confidence, reverse=True):
        src_str = "+".join(fc.sources)
        print(
            f"  [{fc.threat_level.upper():8s}] conf={fc.confidence:.2f}  "
            f"sources={src_str}  types={','.join(fc.detection_types)}  "
            f"lat={fc.lat:.3f} lon={fc.lon:.3f}"
        )

    # ── SPECTER on highest-confidence contact ──────────────────────────────
    top = max(fused, key=lambda x: x.confidence)
    _banner("SPECTER ANALYSIS")
    print(f"Running SPECTER on contact {top.id[:8]}  (conf={top.confidence:.2f}  threat={top.threat_level})")

    specter_result = None
    if top.confidence >= 0.5:
        specter = Specter()
        try:
            specter_result = await specter.analyze(aoi, top)
            if specter_result:
                top.simulation_run = True
                td = specter_result["terrain_data"]
                oc = specter_result["ocoka_analysis"]
                th = specter_result["threat_assessment"]
                print(f"  Terrain type      : {td.get('terrain_type')} (slope={td.get('dominant_slope')})")
                print(f"  Elevation range   : {td.get('elevation_min'):.0f}–{td.get('elevation_max'):.0f}m")
                print(f"  Tactical sig.     : {oc.get('tactical_significance')}")
                print(f"  Probable intent   : {th.get('probable_intent')}")
                print(f"  Projected activity: {th.get('projected_activity')}")
                print(f"\n  Synthesis:")
                for line in specter_result["final_report"].split(". "):
                    print(f"    {line.strip()}.")
        except Exception as exc:
            print(f"  SPECTER error: {exc}")
    else:
        print(f"  Confidence {top.confidence:.2f} below 0.5 threshold — SPECTER skipped")

    # ── PDF report ────────────────────────────────────────────────────────
    _banner("PDF REPORT")
    report_id = str(uuid4())
    now = datetime.now(timezone.utc)

    levels = {fc.threat_level for fc in fused}
    def _threat_assessment(lvls: set) -> str:
        if "critical" in lvls:
            return "CRITICAL: Multi-source corroborated buildup detected. Immediate attention required."
        if "high" in lvls:
            return "HIGH: Significant activity detected across multiple indicators."
        if "medium" in lvls:
            return "MONITORING: Activity detected. Continued observation recommended."
        return "CLEAR: No significant activity detected."

    key_findings = []
    for fc in sorted(fused, key=lambda x: x.confidence, reverse=True)[:5]:
        key_findings.append(
            f"[{fc.threat_level.upper()}] {fc.summary} at ({fc.lat:.4f},{fc.lon:.4f}), "
            f"confidence {fc.confidence:.0%}, sources: {'+'.join(fc.sources)}"
        )

    intel_report = IntelReport(
        id=report_id,
        aoi_id=aoi.id,
        generated_at=now,
        fused_contacts=fused,
        threat_assessment=_threat_assessment(levels),
        key_findings=key_findings,
        recommended_actions=[
            "Review satellite imagery from May–June 2020 for infrastructure changes",
            "Cross-reference with diplomatic cables and news reporting",
            "Assess river valley chokepoints as primary avenues of approach",
        ],
        pdf_path=None,
    )

    specter_map = {top.id: specter_result} if specter_result else {}
    gen = ReportGenerator()
    out_dir = Path(__file__).resolve().parent.parent / "reports" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = gen.generate(intel_report, aoi, fused, specter_results=specter_map)
    demo_path = out_dir.parent / "galwan_2020_demo.pdf"
    import shutil
    shutil.copy(pdf_path, demo_path)

    print(f"PDF saved : {demo_path}")
    print(f"File size : {demo_path.stat().st_size:,} bytes")

    # ── Final summary ─────────────────────────────────────────────────────
    _banner("SUMMARY")
    top_threat = max(levels, key=lambda t: {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(t, 0))
    sources_hit = set()
    for fc in fused:
        sources_hit.update(fc.sources)
    print(f"Overall threat level  : {top_threat.upper()}")
    print(f"Sources with signal   : {', '.join(sorted(sources_hit))}")
    print(f"Fused contacts        : {len(fused)}")
    print(f"Max confidence        : {max(fc.confidence for fc in fused):.2f}")
    multi_source = [fc for fc in fused if len(fc.sources) > 1]
    print(f"Multi-source contacts : {len(multi_source)}")
    if multi_source:
        print(f"\n>> ARGUS detected {len(multi_source)} corroborated contact(s) (2+ sources) in Galwan Valley")
        print("   using open-source data only, before the June 15 clash.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
