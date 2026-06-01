import { useEffect, useRef, useState } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { THREAT_COLORS, SOURCE_COLORS, SOURCE_CODE, THREAT_ORDER } from "../constants"

// ── Geo helpers for the SPECTER overlay ──────────────────────────
const R_EARTH = 6371 // km
function destPoint(lat, lon, distKm, bearingDeg) {
  const br = (bearingDeg * Math.PI) / 180
  const lat1 = (lat * Math.PI) / 180
  const lon1 = (lon * Math.PI) / 180
  const dr = distKm / R_EARTH
  const lat2 = Math.asin(Math.sin(lat1) * Math.cos(dr) + Math.cos(lat1) * Math.sin(dr) * Math.cos(br))
  const lon2 = lon1 + Math.atan2(Math.sin(br) * Math.sin(dr) * Math.cos(lat1), Math.cos(dr) - Math.sin(lat1) * Math.sin(lat2))
  return [(lon2 * 180) / Math.PI, (lat2 * 180) / Math.PI]
}
function ringFeature(lat, lon, radiusKm, steps = 48) {
  const coords = []
  for (let i = 0; i <= steps; i++) coords.push(destPoint(lat, lon, radiusKm, (360 / steps) * i))
  return { type: "Feature", properties: { kind: "obs_ring" }, geometry: { type: "Polygon", coordinates: [coords] } }
}

export default function Map({ aois, contacts, selectedAOI, selectedContact, terrain, onContactClick, drawMode, onDrawComplete }) {
  const mapRef = useRef(null)
  const mapInstance = useRef(null)
  const markersRef = useRef([])
  const specterMarkersRef = useRef([])
  const fittedRef = useRef(false)
  const aoisRef = useRef([])
  const selectedAOIRef = useRef(null)
  const [activeSources, setActiveSources] = useState({ optical: true, sar: true, events: true, maritime: true })
  const [cursor, setCursor] = useState(null)
  const [zoom, setZoom] = useState(3)
  const [zoomLevel, setZoomLevel] = useState(3)

  const paintAOIBoxes = (map) => {
    const src = map.getSource("aoi-boxes")
    if (!src) return
    const selId = selectedAOIRef.current?.id
    const features = aoisRef.current.map(a => {
      const selected = a.id === selId
      return {
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [[[a.bbox[0], a.bbox[1]], [a.bbox[2], a.bbox[1]], [a.bbox[2], a.bbox[3]], [a.bbox[0], a.bbox[3]], [a.bbox[0], a.bbox[1]]]] },
        properties: {
          lineColor: selected ? "#ffffff" : (a.active ? "#36dceb" : "#3a4a57"),
          fillColor: selected ? "#ffffff" : (a.active ? "#36dceb" : "#3a4a57"),
          lineWidth: selected ? 2.5 : 1.5,
          fillOpacity: selected ? 0.18 : 0.07,
        }
      }
    })
    src.setData({ type: "FeatureCollection", features })
  }

  useEffect(() => {
    if (mapInstance.current) return
    const map = new maplibregl.Map({
      container: mapRef.current,
      style: {
        version: 8,
        sources: {
          "esri-satellite": {
            type: "raster",
            tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            tileSize: 256,
            attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
          },
          "esri-labels": {
            type: "raster",
            tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"],
            tileSize: 256,
          },
        },
        layers: [
          { id: "satellite", type: "raster", source: "esri-satellite" },
          { id: "labels", type: "raster", source: "esri-labels", paint: { "raster-opacity": 0.7 } },
        ],
      },
      center: [75, 25],
      zoom: 3,
    })
    map.addControl(new maplibregl.NavigationControl(), "top-left")
    mapInstance.current = map

    map.on("load", () => {
      map.addSource("aoi-boxes", { type: "geojson", data: { type: "FeatureCollection", features: [] } })
      map.addLayer({ id: "aoi-fill", type: "fill", source: "aoi-boxes", paint: { "fill-color": ["get", "fillColor"], "fill-opacity": ["get", "fillOpacity"] } })
      map.addLayer({ id: "aoi-outline", type: "line", source: "aoi-boxes", paint: { "line-color": ["get", "lineColor"], "line-width": ["get", "lineWidth"] } })

      // SPECTER tactical overlay — terrain-derived geometry (glyph-free,
      // so it renders without a font source; labels are DOM markers).
      map.addSource("specter", { type: "geojson", data: { type: "FeatureCollection", features: [] } })
      // Observation ring (line-of-sight horizon from the target).
      map.addLayer({ id: "specter-ring-fill", type: "fill", source: "specter", filter: ["==", ["get", "kind"], "obs_ring"], paint: { "fill-color": "#36dceb", "fill-opacity": 0.05 } })
      map.addLayer({ id: "specter-ring-line", type: "line", source: "specter", filter: ["==", ["get", "kind"], "obs_ring"], paint: { "line-color": "#36dceb", "line-width": 1, "line-dasharray": [2, 2], "line-opacity": 0.6 } })
      // Avenues of approach (low-ground corridors), colored by trafficability.
      map.addLayer({ id: "specter-approach", type: "line", source: "specter", filter: ["==", ["get", "kind"], "approach"], paint: { "line-color": ["get", "color"], "line-width": 2.2, "line-opacity": 0.85 } })

      paintAOIBoxes(map)
    })

    map.on("mousemove", (e) => setCursor([e.lngLat.lng, e.lngLat.lat]))
    map.on("zoom", () => {
      const z = map.getZoom()
      setZoom(z)
      setZoomLevel((prev) => (Math.round(z) !== prev ? Math.round(z) : prev))
    })

    return () => { map.remove(); mapInstance.current = null }
  }, [])

  // Update AOI boxes + auto-fit on first load
  useEffect(() => {
    const map = mapInstance.current
    const list = aois || []
    aoisRef.current = list
    if (map && map.isStyleLoaded()) paintAOIBoxes(map)

    if (!fittedRef.current && list.length > 0) {
      fittedRef.current = true
      const lons = list.flatMap(a => [a.bbox[0], a.bbox[2]])
      const lats = list.flatMap(a => [a.bbox[1], a.bbox[3]])
      map?.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 60, maxZoom: 6, duration: 1200 })
    }
  }, [aois])

  // Repaint boxes when selected AOI changes (highlight)
  useEffect(() => {
    selectedAOIRef.current = selectedAOI || null
    const map = mapInstance.current
    if (map && map.isStyleLoaded()) paintAOIBoxes(map)
  }, [selectedAOI])

  // Update contact markers (with low-zoom clustering)
  useEffect(() => {
    markersRef.current.forEach(m => m.remove())
    markersRef.current = []
    const map = mapInstance.current
    if (!map || !contacts) return

    const visible = contacts.filter(c => {
      const src = c.sources?.[0]
      return activeSources[src] !== false
    })

    // Cluster when zoomed out so 10 theaters don't drown in markers.
    if (zoomLevel < 6 && visible.length > 1) {
      const cell = zoomLevel < 4 ? 4 : 1.5  // degrees per cluster cell
      const buckets = new Map()
      visible.forEach(fc => {
        const key = `${Math.round(fc.lat / cell)}:${Math.round(fc.lon / cell)}`
        if (!buckets.has(key)) buckets.set(key, [])
        buckets.get(key).push(fc)
      })
      buckets.forEach(group => {
        if (group.length === 1) { addDiamond(map, group[0]); return }
        const top = group.reduce((a, b) => (THREAT_ORDER.indexOf(a.threat_level) <= THREAT_ORDER.indexOf(b.threat_level) ? a : b))
        const color = THREAT_COLORS[top.threat_level] || "#6c8090"
        const lat = group.reduce((s, c) => s + c.lat, 0) / group.length
        const lon = group.reduce((s, c) => s + c.lon, 0) / group.length
        const el = document.createElement("div")
        el.className = "mono"
        el.style.cssText = `min-width:24px;height:24px;padding:0 5px;display:flex;align-items:center;justify-content:center;background:rgba(7,11,16,0.9);border:1.5px solid ${color};color:${color};font-size:11px;font-weight:700;cursor:pointer;box-shadow:0 0 10px ${color}66;border-radius:50%;`
        el.textContent = group.length
        el.addEventListener("click", () => map.flyTo({ center: [lon, lat], zoom: 8, duration: 700 }))
        markersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(map))
      })
    } else {
      visible.forEach(fc => addDiamond(map, fc))
    }

    function addDiamond(map, fc) {
      const color = THREAT_COLORS[fc.threat_level] || "#6c8090"
      const size = 8 + Math.round((fc.confidence || 0.5) * 10)
      const el = document.createElement("div")
      el.style.cssText = `width:${size}px;height:${size}px;background:${color};border:1.5px solid #04141a;cursor:pointer;box-shadow:0 0 8px ${color}aa,0 0 2px ${color};transform:rotate(45deg);`
      if (fc.threat_level === "critical") el.className = "pulse-critical"
      const marker = new maplibregl.Marker({ element: el }).setLngLat([fc.lon, fc.lat]).addTo(map)
      el.addEventListener("click", () => onContactClick(fc))
      markersRef.current.push(marker)
    }
  }, [contacts, activeSources, zoomLevel])

  // SPECTER tactical overlay — terrain-derived geometry for selected contact.
  useEffect(() => {
    const map = mapInstance.current
    if (!map || !map.isStyleLoaded()) return
    const src = map.getSource("specter")
    if (!src) return

    // Clear prior label markers.
    specterMarkersRef.current.forEach(m => m.remove())
    specterMarkersRef.current = []

    const geo = terrain?.tactical_geometry
    if (!selectedContact || !geo) {
      src.setData({ type: "FeatureCollection", features: [] })
      return
    }

    const { target, key_terrain, avenues_of_approach = [], principal_obstacle, observation_radius_km } = geo
    const tLat = target?.lat ?? selectedContact.lat
    const tLon = target?.lon ?? selectedContact.lon

    const features = []
    // Observation ring at the true line-of-sight horizon.
    if (observation_radius_km) features.push(ringFeature(tLat, tLon, observation_radius_km))
    // Real avenues of approach: from the low-ground ingress point to target.
    const TRAFFIC_COLOR = { unrestricted: "#2fe06e", restricted: "#ffce3a", severely_restricted: "#ff9e2c" }
    avenues_of_approach.forEach(a => {
      features.push({
        type: "Feature",
        properties: { kind: "approach", color: TRAFFIC_COLOR[a.trafficability] || "#ffce3a" },
        geometry: { type: "LineString", coordinates: [[a.from_lon, a.from_lat], [tLon, tLat]] },
      })
    })
    src.setData({ type: "FeatureCollection", features })

    // Key terrain + obstacle as DOM label markers (glyph-free layers above).
    const addLabel = (lat, lon, glyph, text, color) => {
      const el = document.createElement("div")
      el.className = "mono"
      el.style.cssText = `display:flex;flex-direction:column;align-items:center;pointer-events:none;color:${color};text-shadow:0 0 4px #04141a,0 0 2px #04141a;`
      el.innerHTML = `<div style="font-size:15px;line-height:1">${glyph}</div><div style="font-size:8px;letter-spacing:0.06em;white-space:nowrap;margin-top:1px">${text}</div>`
      const m = new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(map)
      specterMarkersRef.current.push(m)
    }
    if (key_terrain) {
      addLabel(key_terrain.lat, key_terrain.lon, "▲",
        `KEY ${Math.round(key_terrain.elevation)}m`, key_terrain.commands_target ? "#ff4242" : "#36dceb")
    }
    if (principal_obstacle) {
      addLabel(principal_obstacle.lat, principal_obstacle.lon, "⛰",
        `OBST ${Math.round(principal_obstacle.elevation)}m`, "#b07cff")
    }
  }, [selectedContact, terrain])

  // Fly to selected contact
  useEffect(() => {
    const map = mapInstance.current
    if (!map || !selectedContact) return
    map.flyTo({ center: [selectedContact.lon, selectedContact.lat], zoom: 11, duration: 900 })
  }, [selectedContact])

  // Fly to selected AOI
  useEffect(() => {
    const map = mapInstance.current
    if (!map || !selectedAOI) return
    const [minLon, minLat, maxLon, maxLat] = selectedAOI.bbox
    map.fitBounds([[minLon, minLat], [maxLon, maxLat]], { padding: 80, maxZoom: 10, duration: 900 })
  }, [selectedAOI])

  // Draw mode
  useEffect(() => {
    const map = mapInstance.current
    if (!map) return
    if (!drawMode) { map.getCanvas().style.cursor = ""; return }
    map.getCanvas().style.cursor = "crosshair"
    let start = null
    const onClick = (e) => {
      if (!start) {
        start = [e.lngLat.lng, e.lngLat.lat]
      } else {
        const bbox = [Math.min(start[0], e.lngLat.lng), Math.min(start[1], e.lngLat.lat), Math.max(start[0], e.lngLat.lng), Math.max(start[1], e.lngLat.lat)]
        map.getCanvas().style.cursor = ""
        map.off("click", onClick)
        onDrawComplete(bbox)
        start = null
      }
    }
    map.on("click", onClick)
    return () => map.off("click", onClick)
  }, [drawMode])

  const sourceEntries = Object.entries(SOURCE_COLORS)
  const fmt = (v, pos, neg) => `${Math.abs(v).toFixed(4)}°${v >= 0 ? pos : neg}`

  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", background: "#04080c" }}>
      <div ref={mapRef} style={{ position: "absolute", inset: 0 }} />

      {/* Screen FX + frame + war-room grid/reticle */}
      <div className="tac-grid" />
      <div className="map-fx" />
      <div className="reticle"><span className="reticle-ring" /></div>
      <span className="frame-corner tl" />
      <span className="frame-corner tr" />
      <span className="frame-corner bl" />
      <span className="frame-corner br" />

      {/* Top-left feed status */}
      <div
        className="mono"
        style={{
          position: "absolute", top: 14, left: 14, zIndex: 6, pointerEvents: "none",
          display: "flex", alignItems: "center", gap: 8,
          background: "rgba(7,11,16,0.78)", border: "1px solid var(--line)", padding: "5px 10px",
          fontSize: 10, letterSpacing: "0.14em", color: "var(--text)",
        }}
      >
        <span className="status-dot" style={{ color: "var(--green)", background: "var(--green)" }} />
        TACTICAL DISPLAY · LIVE
      </div>

      {/* Sensor feed toggles (top-right) */}
      <div
        className="brkt"
        style={{
          position: "absolute", top: 14, right: 14, zIndex: 6,
          background: "rgba(7,11,16,0.88)", border: "1px solid var(--line)", padding: "9px 11px",
        }}
      >
        <div className="label" style={{ marginBottom: 7 }}>Sensor Feeds</div>
        <div style={{ display: "flex", gap: 6 }}>
          {sourceEntries.map(([src, color]) => {
            const on = activeSources[src] !== false
            return (
              <button
                key={src}
                onClick={() => setActiveSources(s => ({ ...s, [src]: !s[src] }))}
                className="mono"
                style={{
                  background: on ? `${color}1f` : "transparent",
                  border: `1px solid ${on ? color : "var(--line)"}`,
                  borderRadius: 0, padding: "4px 9px", fontSize: 10,
                  color: on ? color : "var(--dim)", cursor: "pointer",
                  fontWeight: 700, letterSpacing: "0.08em",
                  boxShadow: on ? `0 0 8px ${color}40` : "none", transition: "all 0.15s",
                }}
                title={src}
              >
                {SOURCE_CODE[src] || src.toUpperCase()}
              </button>
            )
          })}
        </div>
      </div>

      {/* Threat legend (bottom-right) */}
      <div
        className="mono"
        style={{
          position: "absolute", bottom: 26, right: 14, zIndex: 6, pointerEvents: "none",
          background: "rgba(7,11,16,0.82)", border: "1px solid var(--line)", padding: "8px 11px",
        }}
      >
        <div className="label" style={{ marginBottom: 6 }}>Threat Level</div>
        {THREAT_ORDER.map(t => (
          <div key={t} style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 3 }}>
            <span style={{ width: 8, height: 8, background: THREAT_COLORS[t], transform: "rotate(45deg)", boxShadow: `0 0 5px ${THREAT_COLORS[t]}` }} />
            <span style={{ fontSize: 9.5, letterSpacing: "0.1em", color: "var(--text)" }}>{t.toUpperCase()}</span>
          </div>
        ))}
      </div>

      {/* Cursor + zoom readout (bottom-left) */}
      <div
        className="mono"
        style={{
          position: "absolute", bottom: 26, left: 14, zIndex: 6, pointerEvents: "none",
          background: "rgba(7,11,16,0.82)", border: "1px solid var(--line)", padding: "7px 11px",
          fontSize: 10.5, letterSpacing: "0.06em", color: "var(--accent)", display: "flex", gap: 14,
        }}
      >
        <span>
          <span className="label" style={{ marginRight: 6 }}>LAT</span>
          {cursor ? fmt(cursor[1], "N", "S") : "--.----°"}
        </span>
        <span>
          <span className="label" style={{ marginRight: 6 }}>LON</span>
          {cursor ? fmt(cursor[0], "E", "W") : "--.----°"}
        </span>
        <span>
          <span className="label" style={{ marginRight: 6 }}>ZOOM</span>
          {zoom.toFixed(1)}
        </span>
      </div>

      {drawMode && (
        <div
          className="mono"
          style={{
            position: "absolute", bottom: 64, left: "50%", transform: "translateX(-50%)", zIndex: 7,
            background: "rgba(7,11,16,0.95)", border: "1px solid var(--accent)", padding: "9px 18px",
            color: "var(--accent)", fontSize: 11.5, letterSpacing: "0.1em",
            boxShadow: "0 0 18px var(--accent-glow)",
          }}
        >
          ◢ PLOT MODE — DESIGNATE TWO CORNERS TO DEFINE AREA OF INTEREST
        </div>
      )}
    </div>
  )
}
