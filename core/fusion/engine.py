"""Fusion engine — merges contacts from all layers into corroborated intelligence."""

import logging
import uuid

from geopy.distance import geodesic

from core.models import Contact, FusedContact, SourceType

logger = logging.getLogger(__name__)

# Contacts further apart in time than this are considered contradictory
# if they share a location but differ in detection type.
_TEMPORAL_COHERENCE_HOURS = 48

# Per-source reliability weights for confidence calibration. Physical,
# all-weather sensors are trusted above coarse, noisier OSINT signals.
SOURCE_RELIABILITY: dict[str, float] = {
    "sar": 1.00,       # all-weather radar, physical backscatter measurement
    "optical": 0.95,   # high-res imagery, but cloud/illumination dependent
    "thermal": 0.85,   # VIIRS radiometric, coarser spatial resolution
    "flights": 0.80,   # ADS-B self-reported, spoofable but high coverage
    "events": 0.70,    # news/sentiment, coarse geolocation, higher noise
}

# Maximum confidence bonus the TemporalCorrelator may award for repeated
# independent confirmation. Lives here so explain_confidence can mirror it.
MAX_PERSISTENCE_BONUS = 0.10


def assign_threat_level(confidence: float) -> str:
    """Map a confidence score to a threat level. Shared across the engine."""
    if confidence > 0.85:
        return "critical"
    if confidence > 0.6:
        return "high"
    if confidence >= 0.35:
        return "medium"
    return "low"


def corroboration_multiplier(n_sources: int) -> float:
    """Confidence multiplier keyed on number of distinct corroborating sources."""
    if n_sources <= 1:
        return 0.6
    if n_sources == 2:
        return 1.3
    return 1.6


def explain_confidence(
    raw_contacts: list[dict],
    persistence_score: float = 0.0,
    observation_count: int = 1,
) -> dict:
    """Reconstruct the fusion confidence math as a human-readable breakdown.

    Each raw contact dict must carry ``source`` and ``confidence``. Mirrors
    ``FusionEngine._score_cluster`` exactly — including the Dempster-Shafer
    blend for multi-source clusters — plus the TemporalCorrelator persistence
    bonus, so the UI shows operators the same math that produced the stored
    score.
    """
    if not raw_contacts:
        return {"steps": [], "final": 0.0}

    contributions = []
    total_w = 0.0
    weighted = 0.0
    for c in raw_contacts:
        src = c.get("source", "unknown")
        conf = float(c.get("confidence", 0.0))
        w = SOURCE_RELIABILITY.get(src, 0.8)
        total_w += w
        weighted += conf * w
        contributions.append({
            "source": src,
            "confidence": round(conf, 3),
            "reliability": w,
            "weighted": round(conf * w, 3),
        })

    base = weighted / total_w if total_w else 0.0
    distinct = len({c.get("source") for c in raw_contacts})
    mult = corroboration_multiplier(distinct)

    ds_confidence: float | None = None
    if distinct >= 2:
        from core.fusion.dempster_shafer import fuse_ds
        ds = fuse_ds(raw_contacts, SOURCE_RELIABILITY)
        ds_confidence = ds["ds_confidence"]
        corr_score = min(base * mult, 0.97)
        final = min(round(0.4 * ds_confidence + 0.6 * corr_score, 4), 0.97)
    else:
        final = base * mult

    persistence_bonus = 0.0
    if observation_count > 1 and persistence_score > 0:
        persistence_bonus = round(persistence_score * MAX_PERSISTENCE_BONUS, 4)
        final = min(0.97, final + persistence_bonus)

    final = round(final, 4)
    return {
        "contributions": contributions,
        "weighted_base": round(base, 4),
        "distinct_sources": distinct,
        "corroboration_multiplier": mult,
        "corroboration_label": (
            "uncorroborated (single source)" if distinct <= 1
            else f"{distinct}-source corroboration"
        ),
        "ds_confidence": ds_confidence,
        "persistence_bonus": persistence_bonus,
        "observation_count": observation_count,
        "capped": final >= 0.97,
        "final": final,
        "threat_level": assign_threat_level(final),
    }


class FusionEngine:
    """Clusters geographically proximate contacts and applies corroboration scoring."""

    def __init__(self, cluster_radius_deg: float = 0.1) -> None:
        self.cluster_radius = cluster_radius_deg

    def fuse(self, contacts: list[Contact]) -> list[FusedContact]:
        """Take raw contacts from all layers, cluster, score, and return FusedContacts."""
        if not contacts:
            return []

        clusters = self._cluster_contacts(contacts)
        fused: list[FusedContact] = []

        for cluster in clusters:
            confidence = self._score_cluster(cluster)
            threat_level = self._assign_threat_level(confidence)

            sources: list[SourceType] = list({c.source for c in cluster})
            detection_types = list({c.detection_type for c in cluster})

            centroid_lat = sum(c.lat for c in cluster) / len(cluster)
            centroid_lon = sum(c.lon for c in cluster) / len(cluster)

            latest_ts = max(c.timestamp for c in cluster)

            # Geological activity is environmental noise, not a threat — cap below medium.
            if detection_types == ["geological_activity"]:
                confidence = min(confidence, 0.34)
                threat_level = "low"

            summary = self._build_summary(cluster, sources, detection_types, confidence)

            fused.append(
                FusedContact(
                    id=str(uuid.uuid4()),
                    aoi_id=cluster[0].aoi_id,
                    constituent_contacts=[c.id for c in cluster],
                    sources=sources,
                    confidence=round(confidence, 4),
                    detection_types=detection_types,
                    lat=round(centroid_lat, 6),
                    lon=round(centroid_lon, 6),
                    timestamp=latest_ts,
                    threat_level=threat_level,
                    summary=summary,
                )
            )

        logger.info(
            "Fused %d contacts into %d clusters", len(contacts), len(fused)
        )
        return fused

    def _cluster_contacts(self, contacts: list[Contact]) -> list[list[Contact]]:
        """Group contacts within cluster_radius of a cluster anchor.

        Greedy anchor-based pass (not full single-linkage): each unassigned
        contact becomes an anchor and absorbs everything within radius of
        *it* — chains of contacts each within radius of a member but not of
        the anchor land in separate clusters.
        """
        assigned = [False] * len(contacts)
        clusters: list[list[Contact]] = []

        for i, anchor in enumerate(contacts):
            if assigned[i]:
                continue
            cluster = [anchor]
            assigned[i] = True

            for j in range(i + 1, len(contacts)):
                if assigned[j]:
                    continue
                if self._within_radius(anchor, contacts[j]):
                    cluster.append(contacts[j])
                    assigned[j] = True

            clusters.append(cluster)

        return clusters

    def _within_radius(self, a: Contact, b: Contact) -> bool:
        """Check whether two contacts are within the clustering radius."""
        dist_km = geodesic((a.lat, a.lon), (b.lat, b.lon)).km
        # ~0.1 deg ≈ 11 km at equator; convert configured radius
        radius_km = self.cluster_radius * 111.0
        return dist_km <= radius_km

    def _score_cluster(self, cluster: list[Contact]) -> float:
        """Score a cluster using Dempster-Shafer for multi-source and
        reliability-weighted mean + corroboration multiplier for single-source.

        Multi-source: blend DS threat belief (40%) with the corroboration score
        (60%) so conflict between contradictory sensors depresses confidence
        while agreement across independent sensors amplifies it.
        """
        unique_sources = {c.source for c in cluster}
        avg_conf = self._weighted_confidence(cluster)
        n_sources = len(unique_sources)

        if self._is_contradictory(cluster):
            return min(avg_conf, 0.4)

        if n_sources <= 1:
            return avg_conf * corroboration_multiplier(1)

        # Multi-source: Dempster-Shafer + corroboration blend
        from core.fusion.dempster_shafer import fuse_ds
        raw = [{"source": c.source, "confidence": c.confidence} for c in cluster]
        ds = fuse_ds(raw, SOURCE_RELIABILITY)
        corr_score = min(avg_conf * corroboration_multiplier(n_sources), 0.97)
        return min(round(0.4 * ds["ds_confidence"] + 0.6 * corr_score, 4), 0.97)

    def _weighted_confidence(self, cluster: list[Contact]) -> float:
        """Reliability-weighted mean of constituent confidences."""
        total_w = sum(SOURCE_RELIABILITY.get(c.source, 0.8) for c in cluster)
        if total_w == 0:
            return sum(c.confidence for c in cluster) / len(cluster)
        weighted = sum(
            c.confidence * SOURCE_RELIABILITY.get(c.source, 0.8) for c in cluster
        )
        return weighted / total_w

    def _is_contradictory(self, cluster: list[Contact]) -> bool:
        """Detect contradiction: same location, different detection types, far apart in time."""
        if len(cluster) < 2:
            return False

        detection_types = {c.detection_type for c in cluster}
        if len(detection_types) <= 1:
            return False

        timestamps = sorted(c.timestamp for c in cluster)
        span_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600
        return span_hours > _TEMPORAL_COHERENCE_HOURS

    def _assign_threat_level(self, confidence: float) -> str:
        """Map confidence score to threat level (delegates to shared helper)."""
        return assign_threat_level(confidence)

    def _build_summary(
        self,
        cluster: list[Contact],
        sources: list[SourceType],
        detection_types: list[str],
        confidence: float,
    ) -> str:
        """Generate a rule-based summary for a fused contact."""
        source_str = ", ".join(sources)
        det_str = ", ".join(dt.replace("_", " ") for dt in detection_types)
        return (
            f"{len(cluster)} contact(s) from {source_str} indicating {det_str} "
            f"(fused confidence {confidence:.0%})"
        )
