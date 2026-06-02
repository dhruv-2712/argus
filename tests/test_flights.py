"""Tests for the OpenSky Network flight-pattern layer.

Pure-logic tests over synthetic aircraft state vectors — no network.
Verify military-callsign, ISR-profile, concern-country, and emergency-squawk
classification, plus on-ground filtering and rate-limit degradation.
"""

import asyncio

from datetime import datetime, timezone

from core.models import AOI
from layers.flights.detect import detect, _classify


def make_aoi() -> AOI:
    return AOI(
        id="test-aoi",
        name="Flights Test",
        bbox=(126.5, 37.5, 129.0, 38.5),
        domain="land",
        created_at=datetime.now(timezone.utc),
    )


def aircraft(callsign="", country="United States", alt=10000.0, speed=250.0,
             squawk="", on_ground=False, **kw):
    return {
        "icao24": kw.get("icao24", "abc123"),
        "callsign": callsign,
        "origin_country": country,
        "lat": kw.get("lat", 38.0),
        "lon": kw.get("lon", 127.5),
        "baro_altitude": alt,
        "geo_altitude": alt,
        "on_ground": on_ground,
        "velocity": speed,
        "heading": 90.0,
        "vertical_rate": 0.0,
        "squawk": squawk,
    }


# ── Classification ───────────────────────────────────────────────

def test_military_callsign_flagged():
    c = _classify(aircraft(callsign="RCH445"), "aoi")
    assert c is not None
    assert c.confidence >= 0.70
    assert "military callsign" in c.raw_evidence["detection_reason"]


def test_emergency_squawk_high_confidence():
    c = _classify(aircraft(squawk="7700"), "aoi")
    assert c is not None
    assert c.confidence >= 0.70


def test_hijack_squawk_top_priority():
    c = _classify(aircraft(callsign="UAL123", squawk="7500"), "aoi")
    assert c is not None
    assert c.confidence >= 0.90


def test_isr_altitude_profile_flagged():
    # High altitude (18 km), slow (150 m/s) → ISR loiter profile
    c = _classify(aircraft(callsign="", alt=18000.0, speed=150.0), "aoi")
    assert c is not None
    assert "ISR profile" in c.raw_evidence["detection_reason"]


def test_concern_country_flagged():
    c = _classify(aircraft(callsign="", country="Russia"), "aoi")
    assert c is not None
    assert c.confidence >= 0.60


def test_ordinary_airliner_ignored():
    # Civil callsign, friendly country, normal cruise → no contact
    c = _classify(aircraft(callsign="DLH400", country="Germany",
                           alt=11000.0, speed=250.0), "aoi")
    assert c is None


# ── Detection pipeline ───────────────────────────────────────────

def test_on_ground_aircraft_skipped():
    raw = {"aircraft": [aircraft(callsign="RCH445", on_ground=True)]}
    assert asyncio.run(detect(make_aoi(), raw)) == []


def test_detect_returns_military_contact():
    raw = {"aircraft": [
        aircraft(callsign="FORTE11", country="United States"),  # RC-135 SIGINT
        aircraft(callsign="DLH400", country="Germany", alt=11000.0, speed=250.0),
    ]}
    contacts = asyncio.run(detect(make_aoi(), raw))
    assert len(contacts) == 1
    assert contacts[0].source == "flights"
    assert contacts[0].detection_type == "force_buildup"


def test_detect_degrades_on_rate_limit():
    raw = {"error": "OpenSky rate limited", "aircraft": []}
    assert asyncio.run(detect(make_aoi(), raw)) == []
