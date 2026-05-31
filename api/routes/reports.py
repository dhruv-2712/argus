"""Intelligence report generation endpoints."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import AOI, FusedContact, IntelReport
from db.database import FusedContactRow, IntelReportRow, AOIRow, async_session
from reports.generator import ReportGenerator

router = APIRouter(tags=["reports"])

THREAT_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class ReportRequest(BaseModel):
    """Request body for report generation."""
    include_fused_contacts: bool = True
    threat_threshold: str = "medium"


def _threat_assessment(levels: set[str]) -> str:
    """Generate rule-based threat assessment string."""
    if "critical" in levels:
        return (
            "CRITICAL: Multi-source corroborated activity detected. "
            "Immediate attention required."
        )
    if "high" in levels:
        return (
            "HIGH: Significant activity detected across multiple indicators."
        )
    if "medium" in levels:
        return (
            "MONITORING: Activity detected, single-source. "
            "Continued observation recommended."
        )
    return "CLEAR: No significant activity detected in this AOI."


def _recommended_actions(levels: set[str]) -> list[str]:
    """Generate rule-based recommended actions."""
    if "critical" in levels:
        return [
            "Increase monitoring frequency to 6h",
            "Cross-reference with additional HUMINT sources",
            "Flag for analyst review",
        ]
    if "high" in levels:
        return [
            "Increase monitoring frequency to 12h",
            "Request additional imagery pass",
        ]
    if "medium" in levels:
        return [
            "Continue standard monitoring",
            "Note for weekly review",
        ]
    return ["No action required"]


def _key_findings(fused_contacts: list[dict], limit: int = 5) -> list[str]:
    """Summarize the top contacts as key findings."""
    sorted_fc = sorted(
        fused_contacts,
        key=lambda fc: THREAT_ORDER.get(fc.get("threat_level", "low"), 3),
    )
    findings: list[str] = []
    for fc in sorted_fc[:limit]:
        findings.append(
            f"[{fc['threat_level'].upper()}] {fc['summary']} "
            f"at ({fc['lat']:.4f}, {fc['lon']:.4f}), "
            f"confidence {fc['confidence']:.0%}"
        )
    return findings


def _fused_row_to_dict(row: FusedContactRow) -> dict:
    """Convert FusedContactRow to dict."""
    return {
        "id": row.id,
        "aoi_id": row.aoi_id,
        "constituent_contacts": json.loads(row.constituent_contacts),
        "sources": json.loads(row.sources),
        "confidence": row.confidence,
        "detection_types": json.loads(row.detection_types),
        "lat": row.lat,
        "lon": row.lon,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "threat_level": row.threat_level,
        "summary": row.summary,
        "simulation_run": row.simulation_run,
    }


@router.post("/aoi/{aoi_id}/report")
async def generate_report(aoi_id: str, body: ReportRequest | None = None) -> dict:
    """Generate an intelligence report for an AOI."""
    if body is None:
        body = ReportRequest()

    threshold_rank = THREAT_ORDER.get(body.threat_threshold, 2)

    async with async_session() as session:
        aoi_row = await session.get(AOIRow, aoi_id)
        if not aoi_row:
            raise HTTPException(status_code=404, detail="AOI not found")

        result = await session.execute(
            select(FusedContactRow)
            .where(FusedContactRow.aoi_id == aoi_id)
            .order_by(FusedContactRow.timestamp.desc())
        )
        all_rows = result.scalars().all()

    fused_dicts = [_fused_row_to_dict(r) for r in all_rows]
    filtered = [
        fc for fc in fused_dicts
        if THREAT_ORDER.get(fc["threat_level"], 3) <= threshold_rank
    ]

    levels = {fc["threat_level"] for fc in filtered}

    report_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    report = {
        "id": report_id,
        "aoi_id": aoi_id,
        "generated_at": now.isoformat(),
        "fused_contacts": filtered if body.include_fused_contacts else [],
        "threat_assessment": _threat_assessment(levels),
        "key_findings": _key_findings(filtered),
        "recommended_actions": _recommended_actions(levels),
        "pdf_path": None,
    }

    # Build Pydantic models for PDF generation
    aoi_model = AOI(
        id=aoi_row.id, name=aoi_row.name,
        bbox=(aoi_row.min_lon, aoi_row.min_lat, aoi_row.max_lon, aoi_row.max_lat),
        domain=aoi_row.domain, active=aoi_row.active,
        created_at=aoi_row.created_at, revisit_hours=aoi_row.revisit_hours,
    )
    fc_models = [
        FusedContact(
            id=fc["id"], aoi_id=fc["aoi_id"],
            constituent_contacts=fc["constituent_contacts"],
            sources=fc["sources"], confidence=fc["confidence"],
            detection_types=fc["detection_types"],
            lat=fc["lat"], lon=fc["lon"],
            timestamp=fc["timestamp"] if isinstance(fc["timestamp"], datetime)
            else datetime.fromisoformat(fc["timestamp"]),
            threat_level=fc["threat_level"], summary=fc["summary"],
            simulation_run=fc.get("simulation_run", False),
        )
        for fc in filtered
    ]
    intel_report = IntelReport(
        id=report_id, aoi_id=aoi_id, generated_at=now,
        fused_contacts=fc_models,
        threat_assessment=report["threat_assessment"],
        key_findings=report["key_findings"],
        recommended_actions=report["recommended_actions"],
        pdf_path=None,
    )

    # Generate PDF
    generator = ReportGenerator()
    pdf_path = generator.generate(intel_report, aoi_model, fc_models)
    report["pdf_path"] = pdf_path

    async with async_session() as session:
        session.add(IntelReportRow(
            id=report_id,
            aoi_id=aoi_id,
            generated_at=now,
            fused_contacts=json.dumps(filtered, default=str),
            threat_assessment=report["threat_assessment"],
            key_findings=json.dumps(report["key_findings"]),
            recommended_actions=json.dumps(report["recommended_actions"]),
            pdf_path=pdf_path,
        ))
        await session.commit()

    return report


@router.get("/aoi/{aoi_id}/reports")
async def list_reports(aoi_id: str) -> list[dict]:
    """List all reports for an AOI."""
    async with async_session() as session:
        aoi_row = await session.get(AOIRow, aoi_id)
        if not aoi_row:
            raise HTTPException(status_code=404, detail="AOI not found")

        result = await session.execute(
            select(IntelReportRow)
            .where(IntelReportRow.aoi_id == aoi_id)
            .order_by(IntelReportRow.generated_at.desc())
        )
        rows = result.scalars().all()

    return [
        {
            "id": r.id,
            "aoi_id": r.aoi_id,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            "threat_assessment": r.threat_assessment,
            "key_findings": json.loads(r.key_findings),
            "recommended_actions": json.loads(r.recommended_actions),
            "pdf_path": r.pdf_path,
        }
        for r in rows
    ]


@router.get("/reports/{report_id}")
async def get_report(report_id: str) -> dict:
    """Get a single report by id."""
    async with async_session() as session:
        row = await session.get(IntelReportRow, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "id": row.id,
        "aoi_id": row.aoi_id,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "fused_contacts": json.loads(row.fused_contacts) if row.fused_contacts else [],
        "threat_assessment": row.threat_assessment,
        "key_findings": json.loads(row.key_findings),
        "recommended_actions": json.loads(row.recommended_actions),
        "pdf_path": row.pdf_path,
    }


@router.get("/reports/{report_id}/pdf")
async def download_pdf(report_id: str) -> FileResponse:
    """Download the PDF file for a report."""
    async with async_session() as session:
        row = await session.get(IntelReportRow, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    if not row.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not generated for this report")

    path = Path(row.pdf_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"argus_report_{report_id[:8]}.pdf",
    )
