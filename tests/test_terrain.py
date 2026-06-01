"""Tests for terrain-derived tactical geometry.

These verify the militarily meaningful claims: key terrain is the commanding
height, avenues of approach follow low ground and stay angularly distinct,
and observation radius scales with prominence.
"""

import math

from core.simulation.terrain import (
    compute_tactical_geometry,
    _observation_radius_km,
)


def ring_grid(center_lat, center_lon, span=0.1, n=5):
    """Build an n×n positioned grid around a center."""
    pts = []
    step = (2 * span) / (n - 1)
    for i in range(n):
        for j in range(n):
            pts.append({
                "lat": center_lat - span + step * i,
                "lon": center_lon - span + step * j,
                "elevation": 1000.0,
            })
    return pts


def test_returns_none_for_sparse_grid():
    assert compute_tactical_geometry([{"lat": 0, "lon": 0, "elevation": 1}], 0, 0) is None


def test_key_terrain_is_highest_point():
    grid = ring_grid(34.5, 80.4)
    # Put a peak in one corner
    grid[0]["elevation"] = 5000.0
    geo = compute_tactical_geometry(grid, 34.5, 80.4)
    assert geo is not None
    assert geo["key_terrain"]["elevation"] == 5000.0
    assert geo["key_terrain"]["lat"] == grid[0]["lat"]


def test_avenues_follow_low_ground():
    grid = ring_grid(34.5, 80.4)
    # Carve a low valley on the western perimeter
    for g in grid:
        if g["lon"] < 80.35:
            g["elevation"] = 200.0
    geo = compute_tactical_geometry(grid, 34.5, 80.4)
    assert geo["avenues_of_approach"], "should find at least one approach"
    # The lowest approach corridor should sit on the low (western) ground
    lowest = min(geo["avenues_of_approach"], key=lambda a: a["elevation"])
    assert lowest["elevation"] == 200.0
    assert lowest["trafficability"] in ("unrestricted", "restricted")


def test_avenues_are_angularly_distinct():
    grid = ring_grid(34.5, 80.4)
    # Vary elevations so multiple approaches are found
    for idx, g in enumerate(grid):
        g["elevation"] = 500.0 + (idx % 7) * 80.0
    geo = compute_tactical_geometry(grid, 34.5, 80.4)
    brs = [a["ingress_bearing"] for a in geo["avenues_of_approach"]]
    for i in range(len(brs)):
        for j in range(i + 1, len(brs)):
            sep = abs((brs[i] - brs[j] + 180) % 360 - 180)
            assert sep >= 40, "approaches must be angularly separated"


def test_observation_radius_scales_with_prominence():
    flat = _observation_radius_km(0)
    low = _observation_radius_km(100)
    high = _observation_radius_km(2000)
    assert flat < low < high
    assert high <= 40.0  # clamped


def test_relief_reported():
    grid = ring_grid(34.5, 80.4)
    grid[0]["elevation"] = 5000.0
    grid[1]["elevation"] = 1000.0
    geo = compute_tactical_geometry(grid, 34.5, 80.4)
    assert geo["relief_m"] == 4000.0
    assert geo["elevation_band"]["max"] == 5000.0
