import { useState, useEffect } from "react"

// Loading screen shown while the MapLibre chunk downloads (Suspense fallback).
// The bar eases toward ~92% on a curve, then the map mounts and replaces it —
// so it reads as real progress without needing true download byte counts.
const STAGES = [
  [0, "LINKING SATELLITE UPLINK"],
  [30, "DECRYPTING IMAGERY STREAM"],
  [62, "RENDERING TACTICAL DISPLAY"],
  [85, "CALIBRATING OVERLAYS"],
]

export default function MapLoader() {
  const [pct, setPct] = useState(6)

  useEffect(() => {
    const id = setInterval(() => {
      setPct((p) => (p < 92 ? p + Math.max(0.6, (92 - p) * 0.08) : p))
    }, 110)
    return () => clearInterval(id)
  }, [])

  const stage = STAGES.reduce((acc, s) => (pct >= s[0] ? s[1] : acc), STAGES[0][1])

  return (
    <div
      className="mono"
      style={{
        position: "absolute", inset: 0, zIndex: 9,
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 18,
        background: "radial-gradient(circle at 50% 45%, #0a1622 0%, #04080c 72%)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ display: "inline-block", width: 22, height: 22, border: "2px solid rgba(54,220,235,0.25)", borderTopColor: "var(--accent)", borderRadius: "50%", animation: "spin 0.9s linear infinite" }} />
        <span style={{ color: "var(--text-bright)", fontSize: 13, letterSpacing: "0.26em" }}>INITIALIZING TACTICAL DISPLAY</span>
      </div>

      {/* Progress bar */}
      <div style={{ width: 320, maxWidth: "70vw" }}>
        <div style={{ height: 6, background: "rgba(54,220,235,0.1)", border: "1px solid var(--line)", overflow: "hidden" }}>
          <div
            style={{
              height: "100%", width: `${pct}%`,
              background: "linear-gradient(90deg, rgba(54,220,235,0.5), var(--accent))",
              boxShadow: "0 0 10px var(--accent-glow)", transition: "width 0.2s ease-out",
            }}
          />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 7 }}>
          <span style={{ color: "var(--dim)", fontSize: 9, letterSpacing: "0.14em" }}>{stage}</span>
          <span style={{ color: "var(--accent)", fontSize: 9, letterSpacing: "0.1em" }}>{Math.round(pct)}%</span>
        </div>
      </div>
    </div>
  )
}
