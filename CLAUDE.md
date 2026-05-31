# ARGUS — Project Bible

## What This Is
Multi-source geospatial intelligence fusion platform. Ingests Sentinel-2 
optical, Sentinel-1 SAR, AIS maritime, and GDELT/ACLED conflict events. 
Fuses into confidence-scored contacts. Runs OCOKA terrain simulation.

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
- Phase 5: COMPLETE — Maritime layer (AISHub vessel tracking)
- Phase 6: COMPLETE — FastAPI routes (AOI CRUD, scan, contacts, reports)
- Phase 7: COMPLETE — SPECTER (LangGraph OCOKA) + PDF report generator
- Phase 8: COMPLETE — React + MapLibre frontend (frontend/)
- Phase 9: COMPLETE — Galwan demo, README, release prep

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