"""Fusion engine — merges contacts from all layers into corroborated intelligence."""

import logging
import uuid
from datetime import datetime, timezone

from geopy.distance import geodesic

from core.models import Contact, FusedContact, SourceType

logger = logging.getLogger(__name__)

# Contacts further apart in time than this are considered contradictory
# if they share a location but differ in detection type.
_TEMPORAL_COHERENCE_HOURS = 48


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
        """Group contacts within cluster_radius of each other (greedy single-linkage)."""
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
        """Apply corroboration scoring rules to a cluster."""
        unique_sources = {c.source for c in cluster}
        avg_conf = sum(c.confidence for c in cluster) / len(cluster)
        n_sources = len(unique_sources)

        if self._is_contradictory(cluster):
            return min(avg_conf, 0.4)

        if n_sources == 1:
            return avg_conf * 0.6

        if n_sources == 2:
            return min(avg_conf * 1.3, 0.97)

        # 3+ sources
        return min(avg_conf * 1.6, 0.97)

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

    def _assign_threat_level(
        self, confidence: float
    ) -> str:
        """Map confidence score to threat level."""
        if confidence > 0.85:
            return "critical"
        if confidence > 0.6:
            return "high"
        if confidence >= 0.35:
            return "medium"
        return "low"

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
