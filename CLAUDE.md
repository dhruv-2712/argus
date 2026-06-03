# ARGUS — Project Bible

## What This Is
Multi-source geospatial intelligence fusion platform. Ingests Sentinel-2 
optical, Sentinel-1 SAR, GDELT/ACLED conflict events, NASA FIRMS thermal, 
and OpenSky flights. Fuses into confidence-scored contacts. Runs OCOKA 
terrain simulation.

## Architecture
[the folder structure from Phase 1 prompt]

## Absolute Rules
- All async, no blocking calls
- Type hints everywhere
- Pydantic v2 only
- Layers never import from each other
- Layers only import from core/
- Fusion engine only imports from core/models
- logging not print
- uuid4 for all IDs
- UTC timestamps only

## Data Model Contract
[paste the Contact, AOI, FusedContact, IntelReport model definitions]

## Fusion Engine Rules
[paste the confidence scoring rules]

## Phase Status
- Phase 1: COMPLETE — Core models, DB, base layer, fusion engine
- Phase 2: COMPLETE — Optical layer (Sentinel-2 via Element84 STAC)
- Phase 3: COMPLETE — Events layer (GDELT + ACLED)
- Phase 4: COMPLETE — SAR layer (Sentinel-1 via Planetary Computer)
- Phase 5: REMOVED — Maritime layer (AISHub) dropped; reciprocal receiver requirement made it unavailable
- Phase 6: COMPLETE — FastAPI routes (AOI CRUD, scan, contacts, reports)
- Phase 7: COMPLETE — SPECTER (LangGraph OCOKA) + PDF report generator
- Phase 8: COMPLETE — React + MapLibre frontend (frontend/)
- Phase 9: COMPLETE — Galwan demo, README, release prep
- Phase 10: COMPLETE — Thermal layer (NASA FIRMS VIIRS) + Flights layer (OpenSky ADS-B)
- Phase 11: COMPLETE — Dempster-Shafer evidence fusion (multi-source clusters)
- Phase 12: COMPLETE — Autonomous scan scheduler (APScheduler) + Redis WS fan-out
- Phase 13: COMPLETE — CI/CD (GitHub Actions), 57-test suite, Render+Vercel deploy

## Demo
Run scripts/galwan_demo.py for the Galwan Valley retrospective demo.
Detects CRITICAL-level (0.96 conf) optical+SAR corroborated construction
activity in Galwan Valley using May-June 2020 open-source satellite data.

## API Conventions
- All endpoints async
- Errors return {"detail": "message"} 
- Contacts always sorted by timestamp desc

## Decisions & Deviations

### Optical Layer — Data Source
Uses Element84 Earth Search (STAC API, free, no credentials) instead of 
Google Earth Engine. GEE requires billing setup; Element84 serves the same 
Sentinel-2 data. earthengine-api stays in requirements for SAR layer (Phase 4).
Packages added: pystac-client, rasterio.

### Optical Layer — SSIM
Windowed SSIM via scipy.ndimage.uniform_filter (spatial map) instead of 
skimage global scalar. Produces contact lat/lon from anomaly location.

### Thermal Layer — NASA FIRMS
VIIRS_SNPP_NRT hotspots via FIRMS area CSV API. Needs free FIRMS_MAP_KEY env
var; layer skips gracefully (returns []) when absent. Scored on brightness
temperature (band I-4 Kelvin) + Fire Radiative Power + day/night + FIRMS
confidence label. Detection type: force_buildup. Reliability weight 0.85.

### Flights Layer — OpenSky Network
Anonymous ADS-B state vectors (no key). Classifies on military callsign
prefixes (RCH/FORTE/etc.), ISR altitude+speed profile, concern-country
overflight, and emergency squawks (7500/7600/7700/7777). Handles 429/503
degradation. Detection type: force_buildup. Reliability weight 0.80.

### Fusion — Dempster-Shafer
Multi-source clusters scored by blending DS evidence combination (40%) with
the existing corroboration multiplier (60%), capped 0.97. Single-source
clusters keep the weighted-mean x0.6 penalty (DS adds nothing for one sensor).
Frame Θ = {THREAT, BENIGN}; low-confidence detections contribute ignorance,
not benign assertion — so inter-sensor conflict is modest by design.

### Autonomous Ops
APScheduler AsyncIOScheduler runs hourly, re-scanning any active AOI whose
latest fused contact is older than its revisit_hours. WebSocket fan-out is
in-process by default; set REDIS_URL to enable cross-worker pub/sub. DB path
is configurable via DATA_DIR (defaults to repo root; set to /data on Fly/volume).