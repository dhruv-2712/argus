"""Tests for the fusion engine — the heart of ARGUS.

These lock in the corroboration scoring contract: single sources are
penalised, multiple agreeing sources are boosted (and capped), contradictory
detections are suppressed, and confidence is reliability-weighted.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.fusion.engine import (
    FusionEngine,
    SOURCE_RELIABILITY,
    assign_threat_level,
    corroboration_multiplier,
    explain_confidence,
)
from core.models import Contact

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_contact(source, conf, det_type, lat=34.5, lon=80.4, ts=None):
    return Contact(
        id=str(uuid.uuid4()),
        aoi_id="test-aoi",
        timestamp=ts or NOW,
        source=source,
        confidence=conf,
        detection_type=det_type,
        lat=lat,
        lon=lon,
        description="test contact",
    )


# ── Threat thresholds ───────────────────────────────────────────

@pytest.mark.parametrize("conf,expected", [
    (0.0, "low"),
    (0.34, "low"),
    (0.35, "medium"),
    (0.6, "medium"),
    (0.61, "high"),
    (0.85, "high"),
    (0.86, "critical"),
    (0.96, "critical"),
])
def test_threat_thresholds(conf, expected):
    assert assign_threat_level(conf) == expected


# ── Corroboration multiplier ────────────────────────────────────

def test_single_source_is_penalised():
    assert corroboration_multiplier(1) == 0.6


def test_two_sources_boosted():
    assert corroboration_multiplier(2) == 1.3


def test_three_plus_sources_boosted_more():
    assert corroboration_multiplier(3) == 1.6
    assert corroboration_multiplier(5) == 1.6


# ── Single-source penalty in the engine ─────────────────────────

def test_single_source_confidence_penalised():
    engine = FusionEngine()
    fused = engine.fuse([make_contact("optical", 0.6, "construction")])
    assert len(fused) == 1
    # 0.6 * reliability(0.95)/0.95 = 0.6, then * 0.6 penalty = 0.36
    assert fused[0].confidence == pytest.approx(0.36, abs=0.01)
    assert fused[0].threat_level == "medium"


# ── Two-source corroboration boost ──────────────────────────────

def test_two_source_corroboration_boosts_confidence():
    engine = FusionEngine()
    # optical + SAR agreeing at the same spot
    fused = engine.fuse([
        make_contact("optical", 0.6, "construction", lat=34.50, lon=80.37),
        make_contact("sar", 0.6, "construction", lat=34.49, lon=80.38),
    ])
    assert len(fused) == 1, "agreeing contacts must cluster into one"
    # DS-blended score: 0.4*ds_conf + 0.6*(weighted*1.3) ≈ 0.67 → high
    assert fused[0].confidence == pytest.approx(0.67, abs=0.03)
    assert fused[0].threat_level == "high"
    assert set(fused[0].sources) == {"optical", "sar"}


def test_corroboration_lifts_threat_band():
    """The headline claim: 2 sources turn MEDIUM into HIGH."""
    engine = FusionEngine()
    single = engine.fuse([make_contact("optical", 0.6, "construction")])
    paired = engine.fuse([
        make_contact("optical", 0.6, "construction", lat=34.50, lon=80.37),
        make_contact("sar", 0.6, "construction", lat=34.49, lon=80.38),
    ])
    assert single[0].threat_level == "medium"
    assert paired[0].threat_level == "high"
    assert paired[0].confidence > single[0].confidence


# ── Confidence cap ──────────────────────────────────────────────

def test_confidence_capped_at_097():
    engine = FusionEngine()
    fused = engine.fuse([
        make_contact("sar", 0.95, "construction", lat=34.50, lon=80.37),
        make_contact("optical", 0.95, "construction", lat=34.50, lon=80.37),
        make_contact("events", 0.95, "construction", lat=34.50, lon=80.37),
    ])
    assert fused[0].confidence <= 0.97


# ── Contradiction suppression ───────────────────────────────────

def test_contradiction_caps_confidence():
    engine = FusionEngine()
    # Same place, different detection types, far apart in time → contradiction
    fused = engine.fuse([
        make_contact("optical", 0.9, "construction", lat=34.5, lon=80.4, ts=NOW),
        make_contact("sar", 0.9, "terrain_clearance", lat=34.5, lon=80.4,
                     ts=NOW + timedelta(hours=72)),
    ])
    assert fused[0].confidence <= 0.4


# ── Clustering ──────────────────────────────────────────────────

def test_distant_contacts_do_not_cluster():
    engine = FusionEngine()
    fused = engine.fuse([
        make_contact("optical", 0.6, "construction", lat=34.5, lon=80.4),
        make_contact("sar", 0.6, "construction", lat=10.0, lon=20.0),
    ])
    assert len(fused) == 2, "far-apart contacts stay separate"


def test_empty_input_returns_empty():
    assert FusionEngine().fuse([]) == []


# ── Reliability weighting ───────────────────────────────────────

def test_reliability_weights_favour_physical_sensors():
    assert SOURCE_RELIABILITY["sar"] > SOURCE_RELIABILITY["events"]
    assert SOURCE_RELIABILITY["optical"] > SOURCE_RELIABILITY["events"]


def test_reliability_weighting_leans_toward_trusted_source_in_mixed_cluster():
    """In a mixed cluster the weighted mean is pulled toward the more
    reliable sensor. SAR(high reliability, high conf) + events(low
    reliability, low conf) should land closer to SAR than a plain average."""
    engine = FusionEngine()
    fused = engine.fuse([
        make_contact("sar", 0.9, "construction", lat=34.5, lon=80.4),
        make_contact("events", 0.5, "construction", lat=34.5, lon=80.4),
    ])
    breakdown = explain_confidence([
        {"source": "sar", "confidence": 0.9},
        {"source": "events", "confidence": 0.5},
    ])
    plain_avg = (0.9 + 0.5) / 2
    assert breakdown["weighted_base"] > plain_avg, "weighting favours SAR"


# ── Explainability ──────────────────────────────────────────────

def test_explain_confidence_reconstructs_score():
    """The breakdown must reproduce the exact score the engine stored —
    including the Dempster-Shafer blend for multi-source clusters."""
    raw = [
        {"source": "optical", "confidence": 0.6},
        {"source": "sar", "confidence": 0.6},
    ]
    engine = FusionEngine()
    fused = engine.fuse([
        make_contact("optical", 0.6, "construction", lat=34.5, lon=80.4),
        make_contact("sar", 0.6, "construction", lat=34.5, lon=80.4),
    ])
    breakdown = explain_confidence(raw)
    assert breakdown["distinct_sources"] == 2
    assert breakdown["corroboration_multiplier"] == 1.3
    assert breakdown["ds_confidence"] is not None
    assert breakdown["final"] == pytest.approx(fused[0].confidence, abs=0.005)
    assert breakdown["threat_level"] == fused[0].threat_level
    assert len(breakdown["contributions"]) == 2


def test_explain_confidence_persistence_bonus():
    """Repeated observation adds the same bonus the TemporalCorrelator applies."""
    raw = [{"source": "sar", "confidence": 0.8}]
    base = explain_confidence(raw)
    boosted = explain_confidence(raw, persistence_score=0.5, observation_count=2)
    assert boosted["persistence_bonus"] == pytest.approx(0.05)
    assert boosted["final"] == pytest.approx(base["final"] + 0.05, abs=0.001)


def test_explain_confidence_empty():
    assert explain_confidence([])["final"] == 0.0
