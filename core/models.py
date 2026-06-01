"""Shared Pydantic v2 data models for the ARGUS platform."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


SourceType = Literal["optical", "sar", "maritime", "events", "thermal", "flights"]

DetectionType = Literal[
    "force_buildup",
    "construction",
    "terrain_clearance",
    "vessel_anomaly",
    "event_spike",
    "hydrology_change",
    "unknown",
]


class AOI(BaseModel):
    """Area of Interest definition."""

    id: str
    name: str
    bbox: tuple[float, float, float, float]
    domain: Literal["land", "maritime", "mixed"]
    active: bool = True
    created_at: datetime
    revisit_hours: int = 24


class Contact(BaseModel):
    """Single-source detection event."""

    id: str
    aoi_id: str
    timestamp: datetime
    source: SourceType
    confidence: float
    corroborated_by: list[SourceType] = []
    detection_type: DetectionType
    lat: float
    lon: float
    bbox: tuple[float, float, float, float] | None = None
    description: str
    raw_evidence: dict = {}
    fused: bool = False
    threat_level: Literal["low", "medium", "high", "critical"] | None = None


LifecycleState = Literal[
    "new", "persistent", "escalating", "deescalating", "resolved"
]


class FusedContact(BaseModel):
    """Output of the fusion engine — one FusedContact per geographic cluster."""

    id: str
    aoi_id: str
    constituent_contacts: list[str]
    sources: list[SourceType]
    confidence: float
    detection_types: list[DetectionType]
    lat: float
    lon: float
    timestamp: datetime
    threat_level: Literal["low", "medium", "high", "critical"]
    summary: str
    simulation_run: bool = False

    # ── Temporal intelligence (populated by TemporalCorrelator) ──
    track_id: str | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    observation_count: int = 1
    lifecycle: LifecycleState = "new"
    confidence_delta: float = 0.0
    persistence_score: float = 0.0


class IntelReport(BaseModel):
    """Structured intelligence brief covering an AOI."""

    id: str
    aoi_id: str
    generated_at: datetime
    fused_contacts: list[FusedContact]
    threat_assessment: str
    key_findings: list[str]
    recommended_actions: list[str]
    pdf_path: str | None = None
