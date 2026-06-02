"""Tests for the NASA FIRMS thermal anomaly layer.

Pure-logic tests over synthetic hotspot data — no network. Verify the
scoring thresholds (brightness / FRP / confidence / day-night) and the
graceful-degradation paths (no API key, upstream error).
"""

import asyncio

import pytest

from core.models import AOI
from datetime import datetime, timezone
from layers.thermal.detect import detect, _score


def make_aoi() -> AOI:
    return AOI(
        id="test-aoi",
        name="Thermal Test",
        bbox=(79.8, 34.2, 80.6, 34.8),
        domain="land",
        created_at=datetime.now(timezone.utc),
    )


def hotspot(bright=340.0, frp=30.0, confidence="nominal", daynight="D", **kw):
    return {
        "lat": kw.get("lat", 34.5),
        "lon": kw.get("lon", 80.2),
        "bright_ti4": bright,
        "frp": frp,
        "confidence": confidence,
        "daynight": daynight,
        "acq_date": "2026-06-01",
        "acq_time": "0712",
    }


# ── Scoring ──────────────────────────────────────────────────────

def test_high_brightness_high_frp_scores_high():
    score = _score(hotspot(bright=370.0, frp=150.0, confidence="high", daynight="N"))
    assert score >= 0.85


def test_low_signal_scores_below_threshold():
    # Cool, low-power, low-confidence day reading → discarded
    score = _score(hotspot(bright=310.0, frp=5.0, confidence="low", daynight="D"))
    assert score < 0.35


def test_night_fire_gets_bonus_over_day():
    day = _score(hotspot(daynight="D"))
    night = _score(hotspot(daynight="N"))
    assert night > day


def test_score_never_exceeds_cap():
    score = _score(hotspot(bright=500.0, frp=999.0, confidence="high", daynight="N"))
    assert score <= 0.90


# ── Detection pipeline ───────────────────────────────────────────

def test_detect_filters_weak_hotspots():
    raw = {"hotspots": [
        hotspot(bright=370.0, frp=150.0, confidence="high", daynight="N"),  # strong
        hotspot(bright=305.0, frp=2.0, confidence="low", daynight="D"),     # weak
    ]}
    contacts = asyncio.run(detect(make_aoi(), raw))
    assert len(contacts) == 1
    assert contacts[0].source == "thermal"
    assert contacts[0].detection_type == "force_buildup"


def test_detect_skips_when_no_api_key():
    raw = {"skipped": True, "reason": "no_api_key", "hotspots": []}
    assert asyncio.run(detect(make_aoi(), raw)) == []


def test_detect_skips_on_upstream_error():
    raw = {"error": "FIRMS HTTP 500", "hotspots": []}
    assert asyncio.run(detect(make_aoi(), raw)) == []


def test_detect_carries_evidence():
    raw = {"hotspots": [hotspot(bright=365.0, frp=120.0, confidence="high", daynight="N")]}
    contacts = asyncio.run(detect(make_aoi(), raw))
    ev = contacts[0].raw_evidence
    assert ev["source"] == "thermal"
    assert ev["frp"] == 120.0
    assert ev["daynight"] == "N"
