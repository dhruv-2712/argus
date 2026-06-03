"""Intelligence brief PDF generation using fpdf2."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

from core.models import AOI, FusedContact, IntelReport

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports" / "output"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

NAVY = (26, 39, 68)
WHITE = (255, 255, 255)
LIGHT_GRAY = (240, 240, 240)

THREAT_COLORS = {
    "critical": (192, 57, 43),
    "high": (230, 126, 34),
    "medium": (243, 156, 18),
    "low": (39, 174, 96),
}

SOURCE_COLORS = {
    "optical": (52, 152, 219),
    "sar": (155, 89, 182),
    "events": (230, 126, 34),
    "thermal": (255, 107, 53),
    "flights": (224, 212, 90),
}


def _safe(text: str) -> str:
    """Strip characters outside latin-1 range so Helvetica doesn't error."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


class ReportGenerator:
    """Generate professional intelligence brief PDFs."""

    def generate(
        self,
        report: IntelReport,
        aoi: AOI,
        fused_contacts: list[FusedContact],
        specter_results: dict | None = None,
    ) -> str:
        """Generate PDF and return file path."""
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.set_margins(15, 15, 15)

        self._page_cover(pdf, report, aoi)
        self._page_executive_summary(pdf, report)
        self._pages_contacts(pdf, fused_contacts, specter_results or {})
        self._page_metadata(pdf, report)

        out_path = REPORTS_DIR / f"{report.id}.pdf"
        pdf.output(str(out_path))
        logger.info("PDF report generated: %s", out_path)
        return str(out_path)

    def _page_cover(self, pdf: FPDF, report: IntelReport, aoi: AOI) -> None:
        """Page 1: Cover page."""
        pdf.add_page()

        # Header bar
        pdf.set_fill_color(*NAVY)
        pdf.rect(0, 0, 210, 45, "F")
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_y(12)
        pdf.cell(0, 10, "ARGUS INTELLIGENCE SYSTEM", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 7, "MULTI-SOURCE GEOSPATIAL ASSESSMENT", align="C", new_x="LMARGIN", new_y="NEXT")

        # Classification
        pdf.set_y(55)
        pdf.set_text_color(100, 100, 100)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, "OPEN SOURCE // UNCLASSIFIED", align="C", new_x="LMARGIN", new_y="NEXT")

        # AOI info
        pdf.set_y(75)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, _safe(aoi.name), align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 7, f"Report Date: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, f"AOI: {aoi.bbox}", align="C", new_x="LMARGIN", new_y="NEXT")

        # Threat level badge
        levels = {fc.threat_level for fc in report.fused_contacts}
        top_threat = "low"
        for t in ("critical", "high", "medium", "low"):
            if t in levels:
                top_threat = t
                break

        pdf.set_y(115)
        color = THREAT_COLORS.get(top_threat, THREAT_COLORS["low"])
        pdf.set_fill_color(*color)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 14)
        badge_text = f"  THREAT LEVEL: {top_threat.upper()}  "
        badge_w = pdf.get_string_width(badge_text) + 10
        pdf.set_x((210 - badge_w) / 2)
        pdf.cell(badge_w, 12, badge_text, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

        # Threat assessment
        pdf.set_y(140)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, _safe(report.threat_assessment))

    def _page_executive_summary(self, pdf: FPDF, report: IntelReport) -> None:
        """Page 2: Executive summary."""
        pdf.add_page()
        self._section_header(pdf, "EXECUTIVE SUMMARY")

        # Key findings
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Key Findings", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for i, finding in enumerate(report.key_findings, 1):
            pdf.multi_cell(0, 5, _safe(f"{i}. {finding}"))
            pdf.ln(2)

        pdf.ln(5)

        # Recommended actions
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Recommended Actions", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for i, action in enumerate(report.recommended_actions, 1):
            pdf.multi_cell(0, 5, _safe(f"{i}. {action}"))
            pdf.ln(2)

    def _pages_contacts(
        self, pdf: FPDF, contacts: list[FusedContact], specter: dict
    ) -> None:
        """Pages 3+: Contact details."""
        if not contacts:
            return

        for fc in contacts:
            pdf.add_page()
            self._section_header(pdf, f"CONTACT: {fc.id[:8]}")

            # Metadata line
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 5, f"Timestamp: {fc.timestamp.strftime('%Y-%m-%d %H:%M UTC')}    Location: ({fc.lat:.4f}, {fc.lon:.4f})", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)

            # Threat badge
            color = THREAT_COLORS.get(fc.threat_level, THREAT_COLORS["low"])
            pdf.set_fill_color(*color)
            pdf.set_text_color(*WHITE)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(35, 7, f" {fc.threat_level.upper()} ", fill=True, new_x="END")
            pdf.set_text_color(0, 0, 0)

            # Sources
            pdf.set_x(55)
            pdf.set_font("Helvetica", "", 9)
            for src in fc.sources:
                sc = SOURCE_COLORS.get(src, (100, 100, 100))
                pdf.set_fill_color(*sc)
                pdf.set_text_color(*WHITE)
                pdf.cell(20, 7, f" {src} ", fill=True, new_x="END")
                pdf.set_x(pdf.get_x() + 2)

            pdf.set_text_color(0, 0, 0)
            pdf.ln(12)

            # Detection types + confidence
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 5, f"Detection Types: {', '.join(fc.detection_types)}", new_x="LMARGIN", new_y="NEXT")
            conf_pct = int(fc.confidence * 100)
            bar = "#" * (conf_pct // 10) + "-" * (10 - conf_pct // 10)
            pdf.cell(0, 5, f"Confidence: [{bar}] {conf_pct}%", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)

            # SPECTER section
            fc_specter = specter.get(fc.id)
            if fc_specter and fc.simulation_run:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_fill_color(*LIGHT_GRAY)
                pdf.cell(0, 7, " SPECTER TERRAIN ASSESSMENT", fill=True, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)
                pdf.set_font("Helvetica", "", 9)

                ocoka = fc_specter.get("ocoka_analysis", {})
                for field in ("observation", "cover_concealment", "obstacles", "key_terrain", "avenues_of_approach"):
                    if field in ocoka:
                        label = field.replace("_", " ").title()
                        pdf.set_font("Helvetica", "B", 9)
                        pdf.cell(40, 5, f"{label}:", new_x="END")
                        pdf.set_font("Helvetica", "", 9)
                        pdf.multi_cell(0, 5, _safe(ocoka[field]))
                        pdf.ln(1)

                threat = fc_specter.get("threat_assessment", {})
                if threat:
                    pdf.ln(2)
                    for field in ("probable_intent", "projected_activity", "recommended_observation"):
                        if field in threat:
                            label = field.replace("_", " ").title()
                            pdf.set_font("Helvetica", "B", 9)
                            pdf.cell(45, 5, f"{label}:", new_x="END")
                            pdf.set_font("Helvetica", "", 9)
                            pdf.multi_cell(0, 5, _safe(threat[field]))
                            pdf.ln(1)

            # Summary
            pdf.ln(3)
            pdf.set_font("Helvetica", "I", 10)
            pdf.multi_cell(0, 5, _safe(fc.summary))

    def _page_metadata(self, pdf: FPDF, report: IntelReport) -> None:
        """Final page: Report metadata."""
        pdf.add_page()
        self._section_header(pdf, "REPORT METADATA")

        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Report ID: {report.id}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Total Fused Contacts: {len(report.fused_contacts)}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"ARGUS Version: 0.1.0", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)

        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 5, "This report was generated using open-source data only.", new_x="LMARGIN", new_y="NEXT")

    def _section_header(self, pdf: FPDF, text: str) -> None:
        """Render a section header with underline."""
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*NAVY)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(5)
        pdf.set_text_color(0, 0, 0)
