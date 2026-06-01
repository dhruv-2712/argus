import { useEffect, useRef, useState } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { THREAT_COLORS, SOURCE_COLORS, SOURCE_CODE, THREAT_ORDER } from "../constants"

export default function Map({ aois, contacts, selectedAOI, selectedContact, onContactClick, drawMode, onDrawComplete }) {
  const mapRef = useRef(null)
  const mapInstance = useRef(null)
  const markersRef = useRef([])
  const fittedRef = useRef(false)
  const [activeSources, setActiveSources] = useState({ optical: true, sar: true, events: true, maritime: true })
  const [cursor, setCursor] = useState(null)
  const [zoom, setZoom] = useState(3)

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
      map.addLayer({ id: "aoi-fill", type: "fill", source: "aoi-boxes", paint: { "fill-color": ["get", "fillColor"], "fill-opacity": 0.1 } })
      map.addLayer({ id: "aoi-outline", type: "line", source: "aoi-boxes", paint: { "line-color": ["get", "lineColor"], "line-width": 2 } })
    })

    map.on("mousemove", (e) => setCursor([e.lngLat.lng, e.lngLat.lat]))
    map.on("zoom", () => setZoom(map.getZoom()))

    return () => { map.remove(); mapInstance.current = null }
  }, [])

  // Update AOI boxes + auto-fit on first load
  useEffect(() => {
    const map = mapInstance.current
    if (!map || !map.isStyleLoaded()) return
    const list = aois || []
    const features = list.map(a => ({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [[[a.bbox[0], a.bbox[1]], [a.bbox[2], a.bbox[1]], [a.bbox[2], a.bbox[3]], [a.bbox[0], a.bbox[3]], [a.bbox[0], a.bbox[1]]]] },
      properties: { lineColor: a.active ? "#36dceb" : "#3a4a57", fillColor: a.active ? "#36dceb" : "#3a4a57" }
    }))
    const src = map.getSource("aoi-boxes")
    if (src) src.setData({ type: "FeatureCollection", features })

    // Fit map to show all AOIs on first load
    if (!fittedRef.current && list.length > 0) {
      fittedRef.current = true
      const lons = list.flatMap(a => [a.bbox[0], a.bbox[2]])
      const lats = list.flatMap(a => [a.bbox[1], a.bbox[3]])
      const bounds = [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ]
      map.fitBounds(bounds, { padding: 60, maxZoom: 6, duration: 1200 })
    }
  }, [aois])

  // Update contact markers
  useEffect(() => {
    markersRef.current.forEach(m => m.remove())
    markersRef.current = []
    const map = mapInstance.current
    if (!map || !contacts) return

    contacts.filter(c => {
      const src = c.sources?.[0]
      return activeSources[src] !== false
    }).forEach(fc => {
      const color = THREAT_COLORS[fc.threat_level] || "#6c8090"
      const size = 8 + Math.round((fc.confidence || 0.5) * 10)
      const el = document.createElement("div")
      el.style.cssText = `width:${size}px;height:${size}px;background:${color};border:1.5px solid #04141a;cursor:pointer;box-shadow:0 0 8px ${color}aa,0 0 2px ${color};transform:rotate(45deg);`
      if (fc.threat_level === "critical") el.className = "pulse-critical"
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([fc.lon, fc.lat])
        .addTo(map)
      el.addEventListener("click", () => onContactClick(fc))
      markersRef.current.push(marker)
    })
  }, [contacts, activeSources])

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
