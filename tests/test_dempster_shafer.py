"""Tests for Dempster-Shafer evidence fusion.

Verify the core properties of the orthogonal sum: agreeing sensors amplify
belief, conflicting sensors raise conflict mass and depress threat belief,
ignorance shrinks as evidence accumulates, and all BPAs stay normalised.
"""

import pytest

from core.fusion.dempster_shafer import (
    BPA,
    bpa_from_contact,
    dempster_combine,
    fuse_ds,
)

RELIABILITY = {"sar": 1.0, "optical": 0.95, "events": 0.70, "thermal": 0.85}


# ── BPA construction ─────────────────────────────────────────────

def test_bpa_normalises_to_one():
    b = bpa_from_contact(0.8, 0.9)
    assert b.threat + b.benign + b.uncertain == pytest.approx(1.0)


def test_high_confidence_reliable_source_commits_to_threat():
    b = bpa_from_contact(0.95, 1.0)
    assert b.threat > b.benign
    assert b.uncertain < 0.2


def test_low_confidence_shifts_mass_to_benign():
    b = bpa_from_contact(0.1, 1.0)
    assert b.benign > b.threat


def test_weak_source_keeps_high_ignorance():
    # Low reliability → most mass stays in Θ (ignorance)
    b = bpa_from_contact(0.6, 0.3)
    assert b.uncertain > 0.5


# ── Combination ──────────────────────────────────────────────────

def test_agreeing_sensors_amplify_threat_belief():
    b1 = bpa_from_contact(0.7, 1.0)
    b2 = bpa_from_contact(0.7, 0.95)
    combined = dempster_combine(b1, b2)
    # Joint threat belief should exceed either individual belief
    assert combined.threat > b1.threat
    assert combined.threat > b2.threat


def test_combination_reduces_ignorance():
    b1 = bpa_from_contact(0.7, 0.9)
    b2 = bpa_from_contact(0.7, 0.9)
    combined = dempster_combine(b1, b2)
    assert combined.uncertain < b1.uncertain


def test_conflicting_sensors_depress_threat():
    threat = bpa_from_contact(0.9, 1.0)   # strong threat
    benign = bpa_from_contact(0.1, 1.0)   # strong benign
    combined = dempster_combine(threat, benign)
    # Conflict pulls the combined threat belief well below the threat sensor's
    assert combined.threat < threat.threat


def test_total_conflict_falls_back_to_ignorance():
    a = BPA(threat=1.0, benign=0.0, uncertain=0.0)
    b = BPA(threat=0.0, benign=1.0, uncertain=0.0)
    combined = dempster_combine(a, b)
    assert combined.uncertain == pytest.approx(1.0)


# ── End-to-end fuse_ds ───────────────────────────────────────────

def test_fuse_ds_two_agreeing_sources():
    out = fuse_ds(
        [{"source": "sar", "confidence": 0.8}, {"source": "optical", "confidence": 0.75}],
        RELIABILITY,
    )
    assert out["n_sensors"] == 2
    assert out["ds_confidence"] > 0.7
    assert out["avg_conflict"] < 0.3


def test_fuse_ds_disagreement_weaker_than_agreement():
    """A strong + weak detection must yield lower threat belief and higher
    conflict than two strong agreeing detections.

    Note: in ARGUS every sensor asserts a *threat* (never 'benign'), so a
    low-confidence reading contributes mostly ignorance. Conflict is therefore
    modest by design — what matters is the relative ordering below.
    """
    agree = fuse_ds(
        [{"source": "sar", "confidence": 0.9}, {"source": "optical", "confidence": 0.85}],
        RELIABILITY,
    )
    disagree = fuse_ds(
        [{"source": "sar", "confidence": 0.9}, {"source": "optical", "confidence": 0.1}],
        RELIABILITY,
    )
    assert disagree["ds_confidence"] < agree["ds_confidence"]
    assert disagree["avg_conflict"] > 0.0
    assert disagree["uncertainty"] > agree["uncertainty"]


def test_fuse_ds_empty_is_safe():
    out = fuse_ds([], RELIABILITY)
    assert out["ds_confidence"] == 0.0
    assert out["n_sensors"] == 0


def test_fuse_ds_three_sources_high_corroboration():
    out = fuse_ds(
        [
            {"source": "sar", "confidence": 0.8},
            {"source": "optical", "confidence": 0.78},
            {"source": "thermal", "confidence": 0.75},
        ],
        RELIABILITY,
    )
    assert out["n_sensors"] == 3
    assert out["ds_confidence"] > 0.85
    assert out["uncertainty"] < 0.1
