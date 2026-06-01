import { useState, useMemo, useEffect, useRef } from "react"
import { Clock, Play, Pause, X, History } from "lucide-react"
import { useTracks } from "../hooks/useArgusData"
import { THREAT_COLORS } from "../constants"

// Bottom-docked time-machine. Replays how an AOI's tracks evolved across
// scans — scrub the playhead and watch threat states change over time.
export default function TimelineScrubber({ aoiId, aoiName, onClose, onSeekContact }) {
  const { data } = useTracks(aoiId)
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const timer = useRef(null)

  const tracks = data?.tracks || []

  // Build the global ordered set of observation timestamps (the "frames").
  const frames = useMemo(() => {
    const set = new Set()
    tracks.forEach((t) => t.observations.forEach((o) => o.timestamp && set.add(o.timestamp)))
    return Array.from(set).sort()
  }, [tracks])

  useEffect(() => { setIdx(Math.max(0, frames.length - 1)) }, [frames.length])

  useEffect(() => {
    if (!playing) { clearInterval(timer.current); return }
    timer.current = setInterval(() => {
      setIdx((i) => {
        if (i >= frames.length - 1) { setPlaying(false); return i }
        return i + 1
      })
    }, 700)
    return () => clearInterval(timer.current)
  }, [playing, frames.length])

  if (!aoiId) return null

  const currentTs = frames[idx]
  const currentDate = currentTs ? new Date(currentTs) : null

  // State of each track at the current playhead = its latest observation <= currentTs
  const stateAt = (t) => {
    let latest = null
    for (const o of t.observations) {
      if (!o.timestamp) continue
      if (currentTs && o.timestamp <= currentTs) latest = o
    }
    return latest
  }

  return (
    <div
      className="brkt"
      style={{
        position: "absolute", left: 14, right: 14, bottom: 52, zIndex: 9,
        background: "rgba(8,13,19,0.96)", border: "1px solid var(--accent)",
        boxShadow: "0 0 30px rgba(54,220,235,0.18)", backdropFilter: "blur(6px)",
        maxHeight: "42vh", display: "flex", flexDirection: "column",
      }}
    >
      {/* Header */}
      <div className="flex items-center" style={{ gap: 10, padding: "8px 12px", borderBottom: "1px solid var(--line)" }}>
        <History size={14} style={{ color: "var(--accent)" }} />
        <span className="label" style={{ fontSize: 9 }}>Time Machine</span>
        <span className="mono" style={{ fontSize: 11.5, color: "var(--text-bright)", letterSpacing: "0.04em" }}>
          {aoiName}
        </span>
        <span className="mono flex items-center" style={{ gap: 6, marginLeft: "auto", color: "var(--accent)", fontSize: 11.5 }}>
          <Clock size={12} />
          {currentDate ? currentDate.toISOString().slice(0, 16).replace("T", " ") + "Z" : "— NO HISTORY —"}
        </span>
        <button onClick={onClose} className="mono" style={{ background: "none", border: "1px solid var(--line)", color: "var(--muted)", cursor: "pointer", padding: "3px 6px", marginLeft: 6 }}>
          <X size={12} />
        </button>
      </div>

      {/* Transport + slider */}
      <div className="flex items-center" style={{ gap: 10, padding: "8px 12px", borderBottom: "1px solid var(--line)" }}>
        <button
          onClick={() => { if (idx >= frames.length - 1) setIdx(0); setPlaying((p) => !p) }}
          disabled={frames.length < 2}
          className="mono"
          style={{ background: "var(--accent-dim)", border: "1px solid var(--accent)", color: "var(--accent)", cursor: frames.length < 2 ? "not-allowed" : "pointer", padding: "5px 8px", display: "flex", alignItems: "center", gap: 5, fontSize: 10 }}
        >
          {playing ? <Pause size={12} /> : <Play size={12} />}
          {playing ? "PAUSE" : "REPLAY"}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, frames.length - 1)}
          value={idx}
          onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)) }}
          style={{ flex: 1, accentColor: "var(--accent)" }}
        />
        <span className="mono label" style={{ fontSize: 9 }}>
          {frames.length ? `${idx + 1}/${frames.length}` : "0/0"}
        </span>
      </div>

      {/* Track ribbons */}
      <div style={{ overflowY: "auto", padding: "6px 12px 10px" }}>
        {tracks.length === 0 && (
          <div className="mono" style={{ color: "var(--dim)", fontSize: 11, textAlign: "center", padding: 16, letterSpacing: "0.1em" }}>
            NO TRACK HISTORY — RUN A SCAN
          </div>
        )}
        {tracks.map((t) => {
          const st = stateAt(t)
          const active = !!st
          const col = st ? (THREAT_COLORS[st.threat_level] || "#6c8090") : "#1b2832"
          return (
            <div
              key={t.track_id}
              onClick={() => onSeekContact?.(t)}
              className="flex items-center"
              style={{ gap: 10, padding: "5px 0", cursor: "pointer", opacity: active ? 1 : 0.4 }}
            >
              <span className="mono" style={{ fontSize: 9.5, color: "var(--muted)", width: 64, flexShrink: 0 }}>
                {t.track_id?.slice(0, 6)}
              </span>
              {/* Ribbon */}
              <div style={{ flex: 1, position: "relative", height: 14, background: "#0a1119", border: "1px solid var(--line)" }}>
                {t.observations.map((o, i) => {
                  if (!o.timestamp || !frames.length) return null
                  const pos = frames.indexOf(o.timestamp)
                  if (pos < 0) return null
                  const left = (pos / Math.max(1, frames.length - 1)) * 100
                  const past = currentTs && o.timestamp <= currentTs
                  const c = THREAT_COLORS[o.threat_level] || "#6c8090"
                  return (
                    <span
                      key={i}
                      title={`${o.threat_level} · ${Math.round(o.confidence * 100)}%`}
                      style={{
                        position: "absolute", left: `${left}%`, top: "50%",
                        width: 8, height: 8, transform: "translate(-50%,-50%) rotate(45deg)",
                        background: past ? c : "#1b2832",
                        boxShadow: past && o.threat_level === "critical" ? `0 0 6px ${c}` : "none",
                        transition: "background 0.2s",
                      }}
                    />
                  )
                })}
                {/* Playhead */}
                <span style={{ position: "absolute", left: `${(idx / Math.max(1, frames.length - 1)) * 100}%`, top: 0, bottom: 0, width: 1, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />
              </div>
              <span className="mono" style={{ fontSize: 9.5, color: col, width: 64, flexShrink: 0, textAlign: "right", fontWeight: 700, letterSpacing: "0.06em" }}>
                {st ? st.threat_level?.toUpperCase() : "—"}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
