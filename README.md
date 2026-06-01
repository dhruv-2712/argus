# ARGUS — The Unblinking Eye

**Multi-source geospatial intelligence fusion platform**

![Python](https://img.shields.io/badge/python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green) ![LangGraph](https://img.shields.io/badge/LangGraph-0.2-purple) ![React](https://img.shields.io/badge/React-18-61dafb) ![License](https://img.shields.io/badge/license-MIT-orange)

ARGUS fuses Sentinel-2 optical imagery, Sentinel-1 SAR, AIS maritime vessel tracks, and GDELT/ACLED conflict events into confidence-scored intelligence contacts. A LangGraph OCOKA pipeline (**SPECTER**) runs terrain analysis on high-confidence detections, and the system auto-generates PDF intelligence briefs. A React + MapLibre command-and-control UI renders everything on a live satellite map.

![ARGUS Demo](docs/demo.gif)

> **All data is open-source.** No classified sources are used. Built for research and education only.

---

## Demo — Galwan Valley Retrospective (June 2020)

Run against the Galwan Valley AOI using open-source satellite data from May–June 2020 — ARGUS would have flagged the buildup **before** the June 15 clash.

```
LAYER EXECUTION
  Optical  : 9 contact(s)   [Sentinel-2 SSIM + spectral change]
  SAR      : 2 contact(s)   [Sentinel-1 GRD amplitude correlation]
  Events   : 0 contact(s)   [GDELT free tier has no 2020 history]

FUSION ENGINE — 6 fused contacts
  [CRITICAL] conf=0.96  sources=optical+sar  construction,terrain_clearance
             lat=34.497 lon=80.375

SPECTER (top contact)
  Terrain : ridgeline, steep, 5004–5749m
  Intent  : Establish defensive position / observation post
  Tactical significance: HIGH

SUMMARY
  Overall threat : CRITICAL
  Max confidence : 0.96   (optical + SAR corroborated)
```

Run it yourself:
```bash
python scripts/galwan_demo.py
```
Output PDF: `reports/galwan_2020_demo.pdf`

---

## Architecture

```
Data Sources          Ingestion             Detection            Fusion          Output
-----------           ---------             ---------            ------          ------
Sentinel-2 L2A  -->  optical/ingest.py  --> optical/detect.py  \
Sentinel-1 GRD  -->  sar/ingest.py      --> sar/detect.py        --> FusionEngine --> SPECTER --> PDF
GDELT / ACLED   -->  events/ingest.py   --> events/detect.py    /     (OCOKA)       --> API
AIS vessels     -->  maritime/ingest.py --> maritime/detect.py /                    --> MapLibre UI

Fusion rules:
  1 source x0.6 | 2 sources x1.3 | 3+ x1.6 | cap 0.97
  Contradiction (different types, >48h span): cap 0.4
  Threat: <0.35 low | 0.35-0.6 medium | 0.6-0.85 high | >0.85 critical
```

---

## What It Detects

| Layer | Data Source | Detects | Update Freq |
|---|---|---|---|
| Optical | Sentinel-2 L2A via Element84 STAC (free) | Construction, terrain clearance, force buildup (SSIM + NDVI/SWIR) | ~5 days |
| SAR | Sentinel-1 GRD via Planetary Computer (free) | Surface disturbance, construction (amplitude correlation) | ~6 days |
| Events | GDELT (free) + ACLED (free academic) | Military activity, conflict events from news & structured data | Near real-time |
| Maritime | AISHub (free tier) | Loitering, formation sailing, dark (AIS-gap) vessels | ~30 min |

---

## Quick Start

**Backend** (FastAPI, port 8002):
```bash
cp .env.example .env          # fill in API keys (all optional)
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8002
```

**Frontend** (React + MapLibre, port 5173):
```bash
cd frontend
npm install
npm run dev
```

The UI expects the API at `http://localhost:8002` (configured in `frontend/src/api/client.js`).

**Docker** (API on 8000):
```bash
cp .env.example .env
docker compose up
```

---

## Deployment

### Backend → Render (Web Service)

1. Go to [render.com](https://render.com) → **New → Web Service** → connect your GitHub repo
2. Settings:
   - **Root Directory**: *(leave blank — repo root)*
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
3. **Environment Variables** (add in Render dashboard):
   ```
   GROQ_API_KEY=<your key>
   ACLED_EMAIL=<optional>
   ACLED_KEY=<optional>
   AISHUB_USERNAME=<optional>
   ```
4. Deploy — note the URL Render gives you, e.g. `https://argus-api.onrender.com`

### Frontend → Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project** → import your GitHub repo
2. Settings:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Vite *(auto-detected)*
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. **Environment Variables**:
   ```
   VITE_API_URL=https://argus-api.onrender.com
   ```
   *(replace with your actual Render URL)*
4. Deploy

> **CORS**: After deploy, add your Vercel URL to the FastAPI `allow_origins` list in `api/main.py`.

### Frontend → Render (Static Site, alternative)

1. **New → Static Site** → connect repo
2. Root Directory: `frontend` | Build: `npm run build` | Publish: `dist`
3. Add env var `VITE_API_URL=https://your-backend.onrender.com`

---

## API Reference

```bash
# Create an AOI
curl -X POST http://localhost:8002/aoi \
  -H "Content-Type: application/json" \
  -d '{"name":"Sector Alpha","bbox":[76.5,33.5,77.5,34.5],"domain":"land","revisit_hours":24}'

# Scan it (all layers -> fuse -> SPECTER)
curl -X POST http://localhost:8002/aoi/{id}/scan

# Query contacts
curl "http://localhost:8002/contacts?aoi_id={id}&threat_level=high&limit=20"

# Run SPECTER terrain analysis on a contact
curl -X POST http://localhost:8002/aoi/{aoi_id}/simulate \
  -H "Content-Type: application/json" -d '{"contact_id":"{contact_id}"}'

# Generate report + download PDF
curl -X POST http://localhost:8002/aoi/{id}/report \
  -H "Content-Type: application/json" \
  -d '{"include_fused_contacts":true,"threat_threshold":"low"}'
curl http://localhost:8002/reports/{report_id}/pdf -o report.pdf
```

---

## UI

Dark military C2 / Palantir-Gotham aesthetic on a live ESRI satellite basemap:
- Diamond contact markers colored by threat, sized by confidence (critical pulses)
- Cyan AOI bounding boxes, click-to-plot draw mode
- Sensor-feed toggles (EO / SAR / SIGINT / AIS), live cursor LAT/LON/ZOOM readout
- Right panel: Contacts (threat + sensor filters), Areas, Status (threat donut + PDF report)
- SPECTER terrain dossier with collapsible OCOKA factors

---

## Data Sources

| Source | URL | Auth |
|---|---|---|
| Sentinel-2 L2A | earth-search.aws.element84.com | None |
| Sentinel-1 GRD | planetarycomputer.microsoft.com | None |
| GDELT | gdeltproject.org | None |
| ACLED | acleddata.com | Free academic key |
| AISHub | aishub.net | Free username |
| Open-Elevation | api.open-elevation.com | None |
| ESRI World Imagery (basemap) | arcgisonline.com | None |

---

## Disclaimer

ARGUS uses exclusively open-source, publicly available data. No classified data sources are used or referenced. All analysis is derived from commercial satellite imagery and public databases available to any researcher. For research and educational purposes only.

---

## Roadmap

- WebSocket live contact streaming
- Automated revisit scheduling (APScheduler)
- GeoJSON / KML export
- Historical timeline playback in the UI
- True SLC coherence SAR via ASF Vertex
- Alerting on CRITICAL detections

---

## License

MIT — see [LICENSE](LICENSE).
