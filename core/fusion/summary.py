"""Plain-language scan summaries.

Turns a raw scan result into an explanation a non-expert can read: which
sensors looked, what they found, how detections were fused, and what the
threat picture means. The deterministic builder always produces a clear
narrative; an optional Groq pass rewrites it into simpler English. The LLM
is best-effort — if the key is missing or the call fails, the deterministic
text stands on its own.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Human-readable names for the sensor layers.
_SENSOR_NAMES = {
    "optical": "optical satellite imagery (Sentinel-2)",
    "sar": "radar imaging (Sentinel-1)",
    "events": "conflict news & events (GDELT/ACLED)",
    "thermal": "thermal hotspots (NASA FIRMS)",
    "flights": "live aircraft tracking (OpenSky)",
}

_THREAT_PLAIN = {
    "critical": "critical — strongly corroborated, act now",
    "high": "high — credible, warrants attention",
    "medium": "medium — worth watching",
    "low": "low — background noise",
}

_THREAT_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def build_scan_summary(aoi, result: dict) -> dict:
    """Build a structured + plain-text summary from a scan result.

    ``result`` is the dict returned by ``ScanOrchestrator.scan`` (fused_contacts,
    raw_contact_count, layer_errors, layers_run). Returns a dict with structured
    facts and a deterministic ``narrative`` string.
    """
    fused = result.get("fused_contacts", [])
    raw_count = result.get("raw_contact_count", 0)
    layers_run = result.get("layers_run", [])
    layer_errors = result.get("layer_errors", {})

    online = [l for l in layers_run if l not in layer_errors]
    offline = list(layer_errors.keys())

    # Threat breakdown.
    threat_counts: dict[str, int] = {}
    for fc in fused:
        lvl = getattr(fc, "threat_level", None) or "low"
        threat_counts[lvl] = threat_counts.get(lvl, 0) + 1

    # Top contact (highest threat, then confidence).
    top = None
    if fused:
        top = max(
            fused,
            key=lambda c: (
                _THREAT_RANK.get(getattr(c, "threat_level", "low"), 0),
                getattr(c, "confidence", 0),
            ),
        )

    # Sensors that actually contributed to a fused contact.
    contributing: set[str] = set()
    for fc in fused:
        for s in (getattr(fc, "sources", None) or []):
            contributing.add(s)

    narrative = _compose_narrative(
        aoi_name=getattr(aoi, "name", "the area"),
        online=online,
        offline=offline,
        raw_count=raw_count,
        fused=fused,
        threat_counts=threat_counts,
        top=top,
        contributing=contributing,
    )

    return {
        "narrative": narrative,
        "fused_count": len(fused),
        "raw_count": raw_count,
        "sensors_online": online,
        "sensors_offline": offline,
        "threat_counts": threat_counts,
        "top_threat": getattr(top, "threat_level", None) if top else None,
    }


def _compose_narrative(
    aoi_name, online, offline, raw_count, fused, threat_counts, top, contributing
) -> str:
    """Deterministic plain-English narrative — the always-available backbone."""
    parts: list[str] = []

    # 1. What looked.
    online_names = [_SENSOR_NAMES.get(l, l) for l in online]
    if online_names:
        parts.append(
            f"Scanned {aoi_name} using {len(online_names)} sensor(s): "
            + ", ".join(online_names) + "."
        )
    else:
        parts.append(f"Scanned {aoi_name}, but no sensors returned data.")
    if offline:
        off_names = [_SENSOR_NAMES.get(l, l) for l in offline]
        parts.append(
            "Offline this scan: " + ", ".join(off_names)
            + " (no data, missing key, or rate-limited)."
        )

    # 2. What they found, and how it fused.
    if raw_count == 0:
        parts.append(
            "No raw detections — the sensors saw nothing unusual. This is normal "
            "when satellite imagery hasn't changed recently or no events/heat/aircraft "
            "were present in the window."
        )
    else:
        n = len(fused)
        if n == 0:
            parts.append(
                f"The sensors produced {raw_count} raw detection(s), but none were "
                "strong or corroborated enough to become a confirmed contact."
            )
        else:
            parts.append(
                f"{raw_count} raw detection(s) were fused into {n} confirmed "
                f"contact(s). Fusion clusters nearby detections and scores them — "
                "two sensors agreeing on the same spot scores far higher than one alone."
            )
            multi = sum(1 for fc in fused if len(getattr(fc, "sources", []) or []) > 1)
            if multi:
                parts.append(
                    f"{multi} of those were seen by more than one sensor "
                    "(corroborated — the most trustworthy kind)."
                )

    # 3. Threat picture.
    if threat_counts:
        ordered = sorted(threat_counts.items(), key=lambda kv: -_THREAT_RANK.get(kv[0], 0))
        bits = [f"{cnt} {lvl}" for lvl, cnt in ordered]
        parts.append("Threat breakdown: " + ", ".join(bits) + ".")

    # 4. Headline contact.
    if top is not None:
        dt = getattr(top, "detection_types", None) or []
        dt_txt = ", ".join(t.replace("_", " ") for t in dt) or "activity"
        srcs = getattr(top, "sources", None) or []
        conf = round(float(getattr(top, "confidence", 0)) * 100)
        lvl = getattr(top, "threat_level", "low")
        lat = getattr(top, "lat", 0)
        lon = getattr(top, "lon", 0)
        parts.append(
            f"Top contact: {_THREAT_PLAIN.get(lvl, lvl)} — {dt_txt} at "
            f"{lat:.3f}, {lon:.3f}, {conf}% confidence, from "
            f"{', '.join(srcs) or 'one sensor'}."
        )

    # 5. Next step.
    if fused:
        parts.append(
            "Scan again later to track how these contacts evolve — a second scan "
            "unlocks the Timeline replay and raises confidence on anything that persists."
        )

    return " ".join(parts)


async def polish_summary_llm(narrative: str) -> str:
    """Best-effort: rewrite the narrative into simpler, friendlier English via Groq.

    Returns the original narrative unchanged if no key is set or the call fails.
    """
    if not os.environ.get("GROQ_API_KEY", "").strip():
        return narrative
    try:
        from langchain_groq import ChatGroq

        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            api_key=os.environ["GROQ_API_KEY"],
            timeout=12,
            max_retries=0,
        )
        system = (
            "You rewrite intelligence scan reports for a non-technical reader. "
            "Keep every fact and number exactly. Use plain, calm language, no jargon, "
            "no bullet points, 3-5 short sentences. Do not invent anything."
        )
        resp = await llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": narrative},
        ])
        text = (resp.content or "").strip()
        return text or narrative
    except Exception as exc:  # noqa: BLE001 — summary is best-effort
        logger.warning("Scan summary LLM polish failed: %s", exc)
        return narrative
