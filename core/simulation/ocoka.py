"""SPECTER — LangGraph OCOKA terrain reasoning pipeline.

4-node graph: terrain -> ocoka -> threat -> synthesize
Uses Groq LLM for analysis nodes.
"""

import asyncio
import json
import logging
import os
from typing import TypedDict

import aiohttp
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph

from core.models import AOI, FusedContact
from core.simulation.terrain import compute_tactical_geometry

load_dotenv()

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.5
ELEVATION_API = "https://api.open-elevation.com/api/v1/lookup"
GRID_OFFSET = 0.1
GRID_POINTS = 5


class OcokaState(TypedDict):
    """State schema for the SPECTER pipeline."""
    aoi: dict
    fused_contact: dict
    terrain_data: dict
    ocoka_analysis: dict
    threat_assessment: dict
    final_report: str


def _classify_slope(elevation_range: float) -> str:
    """Classify dominant slope from elevation range."""
    if elevation_range < 50:
        return "flat"
    if elevation_range < 200:
        return "gentle"
    if elevation_range < 500:
        return "moderate"
    return "steep"


def _classify_terrain(mean_elev: float, elev_range: float) -> str:
    """Heuristic terrain type classification."""
    if mean_elev < 50:
        return "coastal"
    if mean_elev < 300 and elev_range < 100:
        return "plains"
    if elev_range > 400:
        return "ridgeline"
    if mean_elev > 3000:
        return "high_altitude"
    return "valley"


async def _fetch_elevations(lat: float, lon: float) -> dict:
    """Query Open-Elevation API for a grid around the point."""
    locations = []
    for i in range(GRID_POINTS):
        for j in range(GRID_POINTS):
            pt_lat = lat - GRID_OFFSET + (2 * GRID_OFFSET / (GRID_POINTS - 1)) * i
            pt_lon = lon - GRID_OFFSET + (2 * GRID_OFFSET / (GRID_POINTS - 1)) * j
            locations.append({"latitude": round(pt_lat, 4), "longitude": round(pt_lon, 4)})

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ELEVATION_API,
                json={"locations": locations},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Elevation API returned %d", resp.status)
                    return {"error": f"HTTP {resp.status}"}
                data = await resp.json()
    except Exception as exc:
        logger.warning("Elevation API failed: %s", exc)
        return {"error": str(exc)}

    results = data.get("results", [])
    grid = [
        {"lat": r["latitude"], "lon": r["longitude"], "elevation": r["elevation"]}
        for r in results
        if r.get("elevation") is not None
    ]
    elevations = [g["elevation"] for g in grid]
    if not elevations:
        return {"error": "no elevation data"}

    mean_elev = sum(elevations) / len(elevations)
    elev_range = max(elevations) - min(elevations)

    terrain = {
        "elevation_mean": round(mean_elev, 1),
        "elevation_range": round(elev_range, 1),
        "elevation_min": round(min(elevations), 1),
        "elevation_max": round(max(elevations), 1),
        "dominant_slope": _classify_slope(elev_range),
        "terrain_type": _classify_terrain(mean_elev, elev_range),
        "grid_size": len(elevations),
        "center_lat": lat,
        "center_lon": lon,
        "grid": grid,
    }
    # Attach terrain-derived tactical geometry (key terrain, avenues of
    # approach, observation radius) computed from the positioned grid.
    geometry = compute_tactical_geometry(grid, lat, lon)
    if geometry:
        terrain["tactical_geometry"] = geometry
    return terrain


def _get_llm() -> ChatGroq:
    """Create Groq LLM instance."""
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        api_key=os.environ.get("GROQ_API_KEY", ""),
    )


async def terrain_node(state: OcokaState) -> dict:
    """Node 1: Fetch terrain/elevation data."""
    fc = state["fused_contact"]
    terrain = await _fetch_elevations(fc["lat"], fc["lon"])
    return {"terrain_data": terrain}


async def ocoka_node(state: OcokaState) -> dict:
    """Node 2: LLM OCOKA terrain analysis."""
    llm = _get_llm()
    system = (
        "You are a military terrain analyst. Analyze the following terrain data "
        "and detected activity using the OCOKA framework used in military "
        "intelligence: Observation and fields of fire, Cover and concealment, "
        "Obstacles, Key terrain, Avenues of approach.\n\n"
        "Respond in JSON only. No preamble. Schema:\n"
        '{"observation": "string", "cover_concealment": "string", '
        '"obstacles": "string", "key_terrain": "string", '
        '"avenues_of_approach": "string", '
        '"tactical_significance": "low" | "medium" | "high" | "critical"}'
    )
    user = json.dumps({
        "terrain_data": state["terrain_data"],
        "detection_types": state["fused_contact"].get("detection_types", []),
        "sources": state["fused_contact"].get("sources", []),
        "confidence": state["fused_contact"].get("confidence", 0),
        "lat": state["fused_contact"].get("lat"),
        "lon": state["fused_contact"].get("lon"),
    }, default=str)

    resp = await llm.ainvoke([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    try:
        analysis = json.loads(resp.content)
    except json.JSONDecodeError:
        analysis = {"raw": resp.content, "tactical_significance": "medium"}

    return {"ocoka_analysis": analysis}


async def threat_node(state: OcokaState) -> dict:
    """Node 3: LLM threat assessment."""
    llm = _get_llm()
    system = (
        "You are a defense intelligence analyst. Based on the OCOKA terrain "
        "analysis and multi-source detection data provided, assess the threat.\n\n"
        "Respond in JSON only. Schema:\n"
        '{"probable_intent": "string", "confidence_assessment": "string", '
        '"projected_activity": "string", "recommended_observation": "string"}'
    )
    user = json.dumps({
        "ocoka_analysis": state["ocoka_analysis"],
        "fused_contact": state["fused_contact"],
    }, default=str)

    resp = await llm.ainvoke([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    try:
        assessment = json.loads(resp.content)
    except json.JSONDecodeError:
        assessment = {"raw": resp.content}

    return {"threat_assessment": assessment}


async def synthesize_node(state: OcokaState) -> dict:
    """Node 4: Synthesize all analysis into a concise paragraph."""
    llm = _get_llm()
    user = (
        "Synthesize the following analysis into a concise intelligence "
        "assessment paragraph. Max 200 words. No bullet points.\n\n"
        f"Terrain: {json.dumps(state['terrain_data'], default=str)}\n"
        f"OCOKA: {json.dumps(state['ocoka_analysis'], default=str)}\n"
        f"Threat: {json.dumps(state['threat_assessment'], default=str)}\n"
        f"Detection: {json.dumps(state['fused_contact'], default=str)}"
    )

    resp = await llm.ainvoke([{"role": "user", "content": user}])
    return {"final_report": resp.content.strip()}


def _build_graph() -> StateGraph:
    """Construct the 4-node SPECTER pipeline."""
    graph = StateGraph(OcokaState)
    graph.add_node("terrain", terrain_node)
    graph.add_node("ocoka", ocoka_node)
    graph.add_node("threat", threat_node)
    graph.add_node("synthesize", synthesize_node)
    graph.set_entry_point("terrain")
    graph.add_edge("terrain", "ocoka")
    graph.add_edge("ocoka", "threat")
    graph.add_edge("threat", "synthesize")
    graph.set_finish_point("synthesize")
    return graph


class Specter:
    """SPECTER terrain reasoning engine."""

    def __init__(self) -> None:
        self.app = _build_graph().compile()

    async def analyze(self, aoi: AOI, contact: FusedContact) -> dict | None:
        """Run OCOKA pipeline on a FusedContact. Returns None if below threshold."""
        if contact.confidence < CONFIDENCE_THRESHOLD:
            logger.info(
                "Skipping SPECTER for contact %s (conf %.2f < %.2f)",
                contact.id, contact.confidence, CONFIDENCE_THRESHOLD,
            )
            return None

        initial_state: OcokaState = {
            "aoi": aoi.model_dump(),
            "fused_contact": contact.model_dump(),
            "terrain_data": {},
            "ocoka_analysis": {},
            "threat_assessment": {},
            "final_report": "",
        }

        result = await self.app.ainvoke(initial_state)

        return {
            "terrain_data": result.get("terrain_data", {}),
            "ocoka_analysis": result.get("ocoka_analysis", {}),
            "threat_assessment": result.get("threat_assessment", {}),
            "final_report": result.get("final_report", ""),
        }
