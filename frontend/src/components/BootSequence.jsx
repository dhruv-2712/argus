import { useState, useEffect, useRef } from "react"

// Cinematic cold-boot sequence — plays once on app load.
const LINES = [
  { t: "ARGUS TACTICAL INTELLIGENCE SYSTEM", cls: "boot-title" },
  { t: "Geospatial Multi-Source Fusion Core // v0.1.0", cls: "boot-sub" },
  { t: "", cls: "" },
  { t: "[ 0.002 ] POST ........................ OK", cls: "ok" },
  { t: "[ 0.014 ] Loading fusion kernel ........ OK", cls: "ok" },
  { t: "[ 0.061 ] SATCOM uplink ................ ACQUIRED", cls: "ok" },
  { t: "[ 0.088 ] Sentinel-2 EO feed ........... ONLINE", cls: "ok" },
  { t: "[ 0.103 ] Sentinel-1 SAR feed .......... ONLINE", cls: "ok" },
  { t: "[ 0.119 ] GDELT / ACLED SIGINT ......... ONLINE", cls: "ok" },
  { t: "[ 0.140 ] AIS maritime track net ....... ONLINE", cls: "ok" },
  { t: "[ 0.171 ] SPECTER OCOKA engine ......... ARMED", cls: "warn" },
  { t: "[ 0.205 ] Theater posture monitor ...... ACTIVE", cls: "ok" },
  { t: "", cls: "" },
  { t: ">> ALL SYSTEMS NOMINAL — OPERATOR CLEARED", cls: "boot-final" },
]

export default function BootSequence({ onDone }) {
  const [shown, setShown] = useState(0)
  const [closing, setClosing] = useState(false)
  const skipped = useRef(false)

  useEffect(() => {
    if (shown >= LINES.length) {
      const t = setTimeout(() => finish(), 650)
      return () => clearTimeout(t)
    }
    const delay = LINES[shown]?.t === "" ? 90 : 130 + Math.random() * 90
    const id = setTimeout(() => setShown((s) => s + 1), delay)
    return () => clearTimeout(id)
  }, [shown])

  const finish = () => {
    if (skipped.current) return
    skipped.current = true
    setClosing(true)
    setTimeout(onDone, 520)
  }

  return (
    <div className={`boot-root${closing ? " boot-closing" : ""}`} onClick={finish}>
      <div className="boot-scan" />
      <div className="boot-grid" />
      <div className="boot-reticle">
        <span className="boot-reticle-ring" />
        <span className="boot-reticle-ring r2" />
      </div>

      <div className="boot-console mono">
        {LINES.slice(0, shown).map((l, i) => (
          <div key={i} className={`boot-line ${l.cls}`}>
            {l.t || " "}
          </div>
        ))}
        {shown < LINES.length && <span className="boot-cursor">█</span>}
      </div>

      <div className="boot-skip mono">CLICK TO BYPASS</div>
    </div>
  )
}
