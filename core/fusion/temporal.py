"""Temporal correlation — links fused contacts into persistent tracks over time.

Each scan produces a fresh set of FusedContacts with new UUIDs. On its own
that is stateless: the system cannot tell a one-off glint from a target that
has been building for weeks. The TemporalCorrelator matches each new fused
contact against the AOI's history, assigns it to a stable *track*, classifies
its lifecycle (new / persistent / escalating / deescalating), and calibrates
its confidence upward the more independent times it has been observed.
"""

import logging
import uuid
from datetime import datetime

from geopy.distance import geodesic

from core.fusion.engine import assign_threat_level
from core.models import FusedContact

logger = logging.getLogger(__name__)

# Two observations within this distance are considered the same track.
_TRACK_RADIUS_KM = 11.0  # ~0.1 deg, matches the fusion cluster radius

# Confidence change thresholds for lifecycle classification.
_ESCALATE_DELTA = 0.05
_DEESCALATE_DELTA = -0.05

# Maximum confidence bonus awarded for repeated independent confirmation.
_MAX_PERSISTENCE_BONUS = 0.10


class TemporalCorrelator:
    """Stateful correlation of fused contacts across scans for one AOI."""

    def __init__(self, track_radius_km: float = _TRACK_RADIUS_KM) -> None:
        self.track_radius_km = track_radius_km

    def correlate(
        self,
        new_contacts: list[FusedContact],
        history: list[dict],
        now: datetime,
    ) -> list[FusedContact]:
        """Enrich ``new_contacts`` in place with temporal track intelligence.

        ``history`` is a list of prior fused-contact records (dicts) for the
        same AOI, each with at least: track_id, lat, lon, confidence,
        first_seen, observation_count, timestamp. Returns the same list for
        convenience.
        """
        # Most-recent observation per track, so escalation compares like-for-like.
        latest_by_track: dict[str, dict] = {}
        for h in sorted(history, key=lambda r: r.get("timestamp") or now):
            tid = h.get("track_id")
            if tid:
                latest_by_track[tid] = h

        for fc in new_contacts:
            match = self._nearest_track(fc, latest_by_track.values())

            if match:
                prior_conf = float(match.get("confidence", fc.confidence))
                fc.track_id = match.get("track_id") or str(uuid.uuid4())
                fc.first_seen = match.get("first_seen") or match.get("timestamp") or now
                fc.observation_count = int(match.get("observation_count", 1)) + 1
                fc.confidence_delta = round(fc.confidence - prior_conf, 4)
                fc.lifecycle = self._classify(fc.confidence_delta)
            else:
                fc.track_id = str(uuid.uuid4())
                fc.first_seen = now
                fc.observation_count = 1
                fc.confidence_delta = 0.0
                fc.lifecycle = "new"

            fc.last_seen = now
            fc.persistence_score = self._persistence(fc.observation_count)

            # Confidence calibration: a target re-confirmed across independent
            # passes is more credible than a single sighting. Boost, then
            # re-derive threat level from the calibrated score.
            if fc.observation_count > 1:
                bonus = fc.persistence_score * _MAX_PERSISTENCE_BONUS
                fc.confidence = round(min(0.97, fc.confidence + bonus), 4)
                fc.threat_level = assign_threat_level(fc.confidence)

        n_tracked = sum(1 for c in new_contacts if c.observation_count > 1)
        logger.info(
            "Temporal correlation: %d/%d contacts matched to existing tracks",
            n_tracked, len(new_contacts),
        )
        return new_contacts

    def _nearest_track(self, fc: FusedContact, candidates) -> dict | None:
        """Return the closest historical observation within track radius."""
        best: dict | None = None
        best_km = self.track_radius_km
        for cand in candidates:
            try:
                d = geodesic((fc.lat, fc.lon), (cand["lat"], cand["lon"])).km
            except (KeyError, ValueError):
                continue
            if d <= best_km:
                best_km = d
                best = cand
        return best

    def _classify(self, delta: float) -> str:
        """Lifecycle from confidence change versus the prior observation."""
        if delta >= _ESCALATE_DELTA:
            return "escalating"
        if delta <= _DEESCALATE_DELTA:
            return "deescalating"
        return "persistent"

    def _persistence(self, observation_count: int) -> float:
        """Diminishing-returns persistence score in [0, 1] from sighting count."""
        if observation_count <= 1:
            return 0.0
        return round(1.0 - 1.0 / observation_count, 4)


def find_resolved_tracks(
    history: list[dict],
    new_contacts: list[FusedContact],
    track_radius_km: float = _TRACK_RADIUS_KM,
) -> list[dict]:
    """Identify previously-active tracks with no matching contact this scan.

    These represent activity that has ceased — useful for the regional board.
    """
    active_ids = {c.track_id for c in new_contacts if c.track_id}
    latest_by_track: dict[str, dict] = {}
    for h in history:
        tid = h.get("track_id")
        if tid:
            prev = latest_by_track.get(tid)
            if not prev or (h.get("timestamp") or 0) > (prev.get("timestamp") or 0):
                latest_by_track[tid] = h
    return [h for tid, h in latest_by_track.items() if tid not in active_ids]
