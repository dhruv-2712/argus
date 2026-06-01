"""Dempster-Shafer evidence theory for multi-sensor fusion under uncertainty.

Frame of discernment Θ = {THREAT, BENIGN}.
Each sensor contributes a basic probability assignment (BPA) over 2^Θ.
Dempster's orthogonal sum combines BPAs, preserving conflict as a diagnostic.

Used by FusionEngine._score_cluster for multi-source clusters; falls back to
the weighted-mean + corroboration approach for single-source contacts where
DS offers no advantage over simpler math.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BPA:
    """Basic probability assignment over {THREAT}, {BENIGN}, and Θ (ignorance)."""
    threat: float
    benign: float
    uncertain: float  # m(Θ) — epistemic ignorance

    def __post_init__(self) -> None:
        total = self.threat + self.benign + self.uncertain
        if total > 0 and abs(total - 1.0) > 1e-9:
            self.threat /= total
            self.benign /= total
            self.uncertain /= total


def bpa_from_contact(confidence: float, reliability: float) -> BPA:
    """Map a contact's confidence + source reliability to a BPA.

    High confidence, reliable source → high m({THREAT}).
    Low confidence → mass shifts toward ignorance (Θ).
    """
    commitment = reliability * confidence          # how strongly the sensor commits
    uncertain = 1.0 - commitment                  # residual epistemic mass

    # Among committed mass, split threat/benign proportional to confidence.
    if confidence >= 0.5:
        share = 2.0 * (confidence - 0.5)          # 0 → 1 as conf goes 0.5 → 1
        threat = commitment * (0.5 + 0.5 * share)
        benign = commitment * (0.5 - 0.5 * share)
    else:
        share = 2.0 * (0.5 - confidence)
        benign = commitment * (0.5 + 0.5 * share)
        threat = commitment * (0.5 - 0.5 * share)

    return BPA(
        threat=max(0.0, threat),
        benign=max(0.0, benign),
        uncertain=max(0.0, uncertain),
    )


def dempster_combine(m1: BPA, m2: BPA) -> BPA:
    """Dempster's orthogonal sum.  K is the unnormalised conflict mass."""
    # Unnormalised mass for each non-empty focal element
    joint_threat = (
        m1.threat * m2.threat
        + m1.threat * m2.uncertain
        + m1.uncertain * m2.threat
    )
    joint_benign = (
        m1.benign * m2.benign
        + m1.benign * m2.uncertain
        + m1.uncertain * m2.benign
    )
    joint_uncertain = m1.uncertain * m2.uncertain

    # Conflict = mass assigned to ∅ (threat ∩ benign = ∅)
    K = m1.threat * m2.benign + m1.benign * m2.threat

    if K >= 1.0:
        # Total conflict (Yager fallback: dump everything to ignorance)
        logger.debug("DS total conflict K=%.3f — falling back to ignorance BPA", K)
        return BPA(threat=0.0, benign=0.0, uncertain=1.0)

    norm = 1.0 - K
    return BPA(
        threat=joint_threat / norm,
        benign=joint_benign / norm,
        uncertain=joint_uncertain / norm,
    )


def fuse_ds(contacts: list[dict], reliabilities: dict[str, float]) -> dict:
    """Fuse a raw contact cluster with Dempster-Shafer combination.

    ``contacts`` must be dicts with ``source`` and ``confidence`` keys.
    ``reliabilities`` maps source name → reliability weight [0, 1].

    Returns a result dict including:
      ``ds_confidence``  — combined m({THREAT}), used as the DS score
      ``avg_conflict``   — mean pairwise conflict K (diagnostic)
      ``uncertainty``    — residual ignorance mass (calibration quality)
    """
    if not contacts:
        return {"ds_confidence": 0.0, "method": "dempster_shafer", "n_sensors": 0}

    bpas = [
        bpa_from_contact(
            float(c.get("confidence", 0.5)),
            reliabilities.get(c.get("source", ""), 0.8),
        )
        for c in contacts
    ]

    combined = bpas[0]
    total_k = 0.0
    for bpa in bpas[1:]:
        k = combined.threat * bpa.benign + combined.benign * bpa.threat
        total_k += k
        combined = dempster_combine(combined, bpa)

    avg_k = total_k / max(len(bpas) - 1, 1)

    return {
        "ds_confidence": round(combined.threat, 4),
        "benign_belief": round(combined.benign, 4),
        "uncertainty": round(combined.uncertain, 4),
        "avg_conflict": round(avg_k, 4),
        "method": "dempster_shafer",
        "n_sensors": len(contacts),
    }
