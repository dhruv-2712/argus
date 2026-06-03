import { useEffect, useState } from "react"

// Full-screen tactical scan HUD — overlays the map while a scan runs.
const PHASES = [
  "TASKING ORBITAL ASSETS",
  "DOWNLINKING SENTINEL-2 EO",
  "DOWNLINKING SENTINEL-1 SAR",
  "CORRELATING SIGINT / THERMAL",
  "RUNNING FUSION KERNEL",
  "SCORING CONTACTS",
]

export default function ScanOverlay({ active }) {
  const [phase, setPhase] = useState(0)

  useEffect(() => {
    if (!active) { setPhase(0); return }
    const id = setInterval(() => setPhase((p) => (p + 1) % PHASES.length), 900)
    return () => clearInterval(id)
  }, [active])

  if (!active) return null

  return (
    <div className="scan-overlay">
      <div className="scan-radar">
        <span className="scan-radar-sweep" />
        <span className="scan-radar-ring" />
        <span className="scan-radar-ring r2" />
        <span className="scan-radar-ring r3" />
        <span className="scan-radar-cross v" />
        <span className="scan-radar-cross h" />
      </div>
      <div className="scan-vbar" />
      <div className="scan-hbar" />
      <div className="scan-readout mono">
        <span className="scan-blip">●</span> ACQUIRING — {PHASES[phase]}
        <span className="scan-dots" />
      </div>
    </div>
  )
}
