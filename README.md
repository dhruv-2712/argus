# ARGUS — The Unblinking Eye

**Multi-source geospatial intelligence fusion platform**

![Python](https://img.shields.io/badge/python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green) ![LangGraph](https://img.shields.io/badge/LangGraph-0.2-purple) ![React](https://img.shields.io/badge/React-18-61dafb) ![License](https://img.shields.io/badge/license-MIT-orange)

ARGUS fuses **five** open-source intelligence streams — Sentinel-2 optical imagery, Sentinel-1 SAR, GDELT/ACLED conflict events, NASA FIRMS thermal anomalies, and OpenSky live aircraft tracks — into confidence-scored intelligence contacts using **Dempster-Shafer evidence fusion**. A LangGraph OCOKA pipeline (**SPECTER**) runs terrain analysis on high-confidence detections, an autonomous scheduler re-scans every active area on its revisit cadence, and the system auto-generates PDF intelligence briefs. A React + MapLibre command-and-control UI renders everything on a live satellite map.

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

## Folder Structure

```
argus/
├── api/                        # FastAPI application
│   ├── main.py                 # App entry point, lifespan, AOI seeding, scheduler
│   ├── scanner.py              # ScanOrchestrator — runs all layers + fusion
│   └── routes/
│       ├── aoi.py              # AOI CRUD + scan endpoint
│       ├── contacts.py         # Fused contact queries
│       ├── intel.py            # Theater posture, track history, terrain
│       ├── reports.py          # PDF report generation
│       ├── monitor.py          # Health / sensor status
│       └── ws.py               # WebSocket live feed + Redis fan-out
│
├── core/
│   ├── models.py               # Pydantic v2 models (AOI, Contact, FusedContact…)
│   ├── fusion/
│   │   ├── engine.py           # Fusion engine — cluster + score contacts
│   │   ├── dempster_shafer.py  # DS evidence combination
│   │   └── temporal.py         # Track correlation across scans
│   └── simulation/
│       ├── ocoka.py            # SPECTER LangGraph OCOKA pipeline
│       └── terrain.py          # Open-Elevation terrain geometry
│
├── layers/                     # Intelligence sensor layers
│   ├── base.py                 # Abstract layer interface
│   ├── optical/                # Sentinel-2 (Element84 STAC, free)
│   ├── sar/                    # Sentinel-1 (Planetary Computer, free)
│   ├── events/                 # GDELT (free) + ACLED (free key)
│   ├── thermal/                # NASA FIRMS VIIRS (free MAP_KEY)
│   └── flights/                # OpenSky ADS-B (no key)
│
├── db/
│   └── database.py             # SQLAlchemy async ORM + init
│
├── reports/
│   └── generator.py            # PDF intelligence brief (WeasyPrint)
│
├── tests/                      # 57-test pytest suite
│   ├── test_fusion.py
│   ├── test_dempster_shafer.py
│   ├── test_thermal.py
│   ├── test_flights.py
│   └── test_terrain.py
│
├── scripts/
│   ├── galwan_demo.py          # Galwan Valley retrospective demo
│   └── pipeline_demo.py        # End-to-end pipeline smoke test
│
├── frontend/                   # React + MapLibre C2 UI
│   └── src/
│       ├── App.jsx             # Root — layout, mobile drawer, boot gate
│       ├── components/
│       │   ├── Map.jsx         # MapLibre map, markers, SPECTER overlay
│       │   ├── Header.jsx      # AOI selector, scan button, UTC clock
│       │   ├── RightPanel.jsx  # Contacts / Areas / Status tabs
│       │   ├── ContactDetail.jsx
│       │   ├── BootSequence.jsx
│       │   ├── TimelineScrubber.jsx
│       │   ├── CommandPalette.jsx
│       │   └── TheaterPosture.jsx
│       ├── hooks/
│       │   ├── useArgusData.js # React Query hooks for all API calls
│       │   └── useLiveFeed.js  # WebSocket live contact feed
│       └── lib/sound.js        # Audio cues
│
├── .github/workflows/ci.yml    # GitHub Actions — pytest + Vite build
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Architecture

```
Data Sources           Ingestion              Detection             Fusion          Output
-----------            ---------              ---------             ------          ------
Sentinel-2 L2A   -->  optical/ingest.py  --> optical/detect.py  \
Sentinel-1 GRD   -->  sar/ingest.py      --> sar/detect.py       \
GDELT / ACLED    -->  events/ingest.py   --> events/detect.py     --> FusionEngine --> SPECTER --> PDF
NASA FIRMS       -->  thermal/ingest.py  --> thermal/detect.py    /   (DS + corrob)  (OCOKA)   --> API
OpenSky ADS-B    -->  flights/ingest.py  --> flights/detect.py   /                             --> MapLibre UI

Fusion rules:
  Single-source:  weighted-mean x0.6  (uncorroborated penalty)
  Multi-source:   Dempster-Shafer evidence combination (40%) blended with
                  corroboration multiplier (60%): 2 src x1.3 | 3+ x1.6 | cap 0.97
  Contradiction (different types, >48h span): cap 0.4
  Source reliability: SAR 1.0 | optical 0.95 | thermal 0.85 | flights 0.80 | events 0.70
  Threat: <0.35 low | 0.35-0.6 medium | 0.6-0.85 high | >0.85 critical
```

An hourly **autonomous scheduler** (APScheduler) re-scans every active AOI once
its `revisit_hours` window lapses, pushing results to connected operators over
WebSocket. Multi-worker deployments fan out live events via optional Redis pub/sub.

---

## What It Detects

| Layer | Data Source | Detects | Update Freq |
|---|---|---|---|
| Optical | Sentinel-2 L2A via Element84 STAC (free) | Construction, terrain clearance, force buildup (SSIM + NDVI/SWIR) | ~5 days |
| SAR | Sentinel-1 GRD via Planetary Computer (free) | Surface disturbance, construction (amplitude correlation) | ~6 days |
| Events | GDELT (free) + ACLED (free academic) | Military activity, conflict events from news & structured data | Near real-time |
| Thermal | NASA FIRMS VIIRS (free key) | Weapons fire, burn-off, convoy heat (brightness-temp + FRP scoring) | ~3–6 hrs |
| Flights | OpenSky Network (free, no key) | Military callsigns, ISR loiter profiles, emergency squawks | Near real-time |

### Sensor Availability & Known Limitations

Not every sensor works out of the box. The platform degrades gracefully — missing
sensors reduce coverage but scans never fail.

| Layer | Status | Notes |
|---|---|---|
| Optical (Sentinel-2) | Works immediately | Depends on satellite revisit (~5 days). Returns 0 contacts if no recent imagery covers the AOI. |
| SAR (Sentinel-1) | Works immediately | Same revisit caveat. Detects surface change, not objects. |
| Events (GDELT) | Works immediately | Free, no key. Lower confidence ceiling (0.65) than ACLED (0.85). |
| Events (ACLED) | Needs `ACLED_API_KEY` + `ACLED_EMAIL` | Free academic registration, may require approval. |
| Thermal (FIRMS) | Needs `FIRMS_MAP_KEY` | Free instant key — [register here](https://firms.modaps.eosdis.nasa.gov/api/map_key/) (~60 sec). Highest-impact sensor to enable. |
| Flights (OpenSky) | Works immediately | Anonymous ADS-B. Military aircraft often squawk Mode-S without callsign. |

> **Recommendation:** At minimum, get a `FIRMS_MAP_KEY`. It's instant, free, and
> thermal anomalies fire frequently in conflict and volcanic zones.

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
   FIRMS_MAP_KEY=<your FIRMS key>
   ACLED_API_KEY=<optional>
   ACLED_EMAIL=<optional>
   REDIS_URL=<optional, for multi-worker fan-out>
   DATA_DIR=/data  # if using persistent volume
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
- Sensor-feed toggles (EO / SAR / SIGINT / THRM / FLGT), live cursor LAT/LON/ZOOM readout
- Contact-density heatmap at low zoom; escalation rings + directional trajectory vectors
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
| NASA FIRMS | firms.modaps.eosdis.nasa.gov | Free MAP_KEY (`FIRMS_MAP_KEY`) |
| OpenSky Network | opensky-network.org | None |
| Open-Elevation | api.open-elevation.com | None |
| ESRI World Imagery (basemap) | arcgisonline.com | None |

---

## Disclaimer

ARGUS uses exclusively open-source, publicly available data. No classified data sources are used or referenced. All analysis is derived from commercial satellite imagery and public databases available to any researcher. For research and educational purposes only.

---

## Testing

A **57-test** pytest suite covers the intelligence core:

- **Fusion engine** — single-source penalty, multi-source boost + cap, contradiction suppression, reliability weighting, score explainability
- **Dempster-Shafer** — BPA normalisation, agreement amplification, conflict handling, total-conflict fallback
- **Thermal layer** — brightness/FRP/day-night scoring, weak-signal filtering, no-key degradation
- **Flights layer** — military-callsign / ISR-profile / squawk classification, on-ground filtering, rate-limit degradation
- **Terrain geometry** — commanding-height selection, low-ground approaches, observation-radius scaling

```bash
pip install -r requirements.txt
pytest -q          # 57 passed
```

CI (`.github/workflows/ci.yml`) runs the full suite plus a production frontend
build on every push to `main`.

## War-Room UX

- **Cold-boot sequence** — cinematic POST log on launch (skippable)
- **Live feed (WebSocket)** — contacts stream in the instant a scan resolves; audio cue on CRITICAL
- **Autonomous scanning** — hourly scheduler re-scans active AOIs on their revisit cadence; results arrive as `AUTO` live-feed events
- **Command palette** — `⌘K` / `Ctrl-K` to jump to any AOI, run a scan, or toggle audio
- **Time machine** — scrub/replay how each AOI's tracks evolved across scans
- **Confidence explainability** — every contact shows the exact fusion math ("why this score")
- **SPECTER overlay** — engagement ring + avenues of approach drawn around simulated contacts
- **Low-zoom clustering** — theaters collapse into count badges when zoomed out
- 14 hotspot AOIs pre-seeded on first launch (Galwan, Kashmir LoC, Taiwan Strait, Donbas, Java Volcanic Arc, Eastern DRC…)

## Roadmap

- ~~Automated revisit scheduling (APScheduler)~~ ✅ shipped
- ~~Dempster-Shafer evidence fusion~~ ✅ shipped
- ~~Thermal (FIRMS) + flight (OpenSky) layers~~ ✅ shipped
- GeoJSON / KML export
- True SLC coherence SAR via ASF Vertex
- PostGIS spatial backend (`ST_Contains` / `ST_DWithin`)
- Per-user AOI workspaces

---

## License

MIT — see [LICENSE](LICENSE).
