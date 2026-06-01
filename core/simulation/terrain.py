"""Terrain-derived tactical geometry.

Pure functions (no LLM, no I/O) that turn a sampled elevation grid into
militarily meaningful geometry: where the commanding high ground is, which
low-ground corridors a force would actually use to approach, and how far the
target can observe. The map overlay renders this directly, so what operators
see is grounded in real elevation data rather than decoration.
"""

import math

R_EARTH_KM = 6371.0


def _bearing(lat1, lon1, lat2, lon2):
    """Initial compass bearing from point 1 to point 2, in degrees [0, 360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH_KM * math.asin(math.sqrt(a))


def _observation_radius_km(prominence_m):
    """Geometric horizon distance for an observer raised `prominence_m` above
    the surrounding low ground: d ≈ sqrt(2 * R * h). Clamped to a sane band."""
    if prominence_m <= 0:
        return 2.0
    d = math.sqrt(2 * R_EARTH_KM * 1000 * prominence_m) / 1000.0
    return round(max(2.0, min(d, 40.0)), 1)


def compute_tactical_geometry(grid, center_lat, center_lon, max_approaches=3):
    """Derive tactical geometry from a positioned elevation grid.

    `grid` is a list of {"lat", "lon", "elevation"} samples. Returns key
    terrain (commanding height), avenues of approach (low-ground corridors,
    angularly separated), principal obstacles (high ground), the target's
    elevation, and its observation radius.
    """
    pts = [g for g in grid if g.get("elevation") is not None]
    if len(pts) < 4:
        return None

    elevations = [g["elevation"] for g in pts]
    min_e, max_e = min(elevations), max(elevations)
    mean_e = sum(elevations) / len(elevations)

    # Target elevation = nearest sample to the contact centroid.
    target = min(pts, key=lambda g: _haversine_km(center_lat, center_lon, g["lat"], g["lon"]))
    target_elev = target["elevation"]

    # Key terrain = the dominant height in the sampled area.
    key = max(pts, key=lambda g: g["elevation"])

    # Perimeter samples = candidate approach/obstacle ingress points. A force
    # enters along the edges of the area, so rank edge samples by elevation:
    # low ground = avenues of approach, high ground = obstacles.
    cx = sum(g["lat"] for g in pts) / len(pts)
    cy = sum(g["lon"] for g in pts) / len(pts)
    max_r = max(_haversine_km(cx, cy, g["lat"], g["lon"]) for g in pts) or 1.0
    perimeter = [g for g in pts if _haversine_km(cx, cy, g["lat"], g["lon"]) >= 0.6 * max_r]
    if not perimeter:
        perimeter = pts

    # Avenues of approach — lowest perimeter points, kept angularly distinct.
    by_low = sorted(perimeter, key=lambda g: g["elevation"])
    approaches = []
    for g in by_low:
        brng = _bearing(g["lat"], g["lon"], center_lat, center_lon)
        if all(abs((brng - a["ingress_bearing"] + 180) % 360 - 180) >= 40 for a in approaches):
            approaches.append({
                "from_lat": g["lat"], "from_lon": g["lon"],
                "ingress_bearing": round(brng, 1),
                "elevation": g["elevation"],
                # Trafficability: lower relative to mean = better going.
                "trafficability": _trafficability(g["elevation"], min_e, max_e),
            })
        if len(approaches) >= max_approaches:
            break

    # Principal obstacle — highest perimeter point (restrictive high ground).
    obstacle = max(perimeter, key=lambda g: g["elevation"])

    prominence = target_elev - min_e
    return {
        "target": {"lat": center_lat, "lon": center_lon, "elevation": round(target_elev, 1)},
        "key_terrain": {
            "lat": key["lat"], "lon": key["lon"], "elevation": round(key["elevation"], 1),
            "commands_target": key["elevation"] > target_elev,
        },
        "avenues_of_approach": approaches,
        "principal_obstacle": {
            "lat": obstacle["lat"], "lon": obstacle["lon"],
            "elevation": round(obstacle["elevation"], 1),
            "bearing": round(_bearing(center_lat, center_lon, obstacle["lat"], obstacle["lon"]), 1),
        },
        "observation_radius_km": _observation_radius_km(prominence),
        "elevation_band": {"min": round(min_e, 1), "mean": round(mean_e, 1), "max": round(max_e, 1)},
        "relief_m": round(max_e - min_e, 1),
    }


def _trafficability(elev, min_e, max_e):
    """Qualitative going for an approach corridor based on relative elevation."""
    if max_e == min_e:
        return "unrestricted"
    frac = (elev - min_e) / (max_e - min_e)
    if frac < 0.25:
        return "unrestricted"
    if frac < 0.6:
        return "restricted"
    return "severely_restricted"
