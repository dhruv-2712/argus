import { useRegional } from "../hooks/useArgusData"
import { Radar, TriangleAlert } from "lucide-react"

const POSTURE_COLOR = {
  ALERT: "#ff4242",
  ELEVATED: "#ff9e2c",
  WATCH: "#ffce3a",
  QUIET: "#6c8090",
}

function assessmentTone(a = "") {
  if (a.includes("REGIONAL ESCALATION")) return { color: "#ff4242", pulse: true, defcon: "DEFCON 2" }
  if (a.includes("COORDINATED")) return { color: "#ff9e2c", pulse: true, defcon: "DEFCON 3" }
  if (a.includes("LOCALIZED ALERT")) return { color: "#ff9e2c", pulse: false, defcon: "DEFCON 3" }
  return { color: "#2fe06e", pulse: false, defcon: "DEFCON 5" }
}

export default function TheaterPosture({ onSelectAOI, aois }) {
  const { data } = useRegional()
  if (!data) return null

  const tone = assessmentTone(data.regional_assessment)
  const board = data.board || []

  return (
    <div
      className="flex items-center shrink-0"
      style={{
        height: 34, gap: 14, padding: "0 14px",
        background: "linear-gradient(180deg, #0a1219, #080d13)",
        borderBottom: "1px solid var(--line)", overflow: "hidden",
      }}
    >
      {/* DEFCON / theater assessment */}
      <div className="flex items-center" style={{ gap: 9, flexShrink: 0 }}>
        <Radar size={14} style={{ color: tone.color }} className={tone.pulse ? "pulse-critical" : ""} />
        <span className="label" style={{ fontSize: 8 }}>Theater</span>
        <span
          className="mono"
          style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: tone.color }}
        >
          {tone.defcon}
        </span>
      </div>

      <div style={{ width: 1, height: 18, background: "var(--line)", flexShrink: 0 }} />

      <div className="mono" style={{ fontSize: 10.5, letterSpacing: "0.06em", color: tone.color, flexShrink: 0, display: "flex", alignItems: "center", gap: 7 }}>
        {tone.pulse && <TriangleAlert size={12} />}
        {data.regional_assessment}
      </div>

      {/* Per-AOI posture chips */}
      <div className="flex items-center" style={{ gap: 6, overflowX: "auto", flex: 1, minWidth: 0 }}>
        {board.map((b) => {
          const col = POSTURE_COLOR[b.posture] || "#6c8090"
          return (
            <button
              key={b.aoi_id}
              onClick={() => { const found = aois?.find(a => a.id === b.aoi_id); if (found) onSelectAOI(found) }}
              className="mono"
              title={`${b.name} · ${b.active_tracks} tracks · ${b.escalating_tracks} escalating`}
              style={{
                flexShrink: 0, background: `${col}14`, border: `1px solid ${col}`, borderRadius: 0,
                padding: "2px 9px", fontSize: 9.5, color: col, cursor: "pointer",
                letterSpacing: "0.06em", fontWeight: 700, display: "flex", alignItems: "center", gap: 6,
              }}
            >
              <span style={{ width: 6, height: 6, background: col, transform: "rotate(45deg)", boxShadow: b.posture === "ALERT" ? `0 0 6px ${col}` : "none" }} />
              {b.name.length > 18 ? b.name.slice(0, 18) + "…" : b.name}
              <span style={{ opacity: 0.7 }}>{b.posture}</span>
              {b.escalating_tracks > 0 && <span style={{ color: "#ff4242" }}>▲{b.escalating_tracks}</span>}
            </button>
          )
        })}
      </div>

      {/* Right counts */}
      <div className="flex items-center mono" style={{ gap: 14, flexShrink: 0, fontSize: 10 }}>
        <Counter label="Areas" value={data.areas_total} />
        <Counter label="Alert" value={data.areas_alert} color={data.areas_alert > 0 ? "#ff4242" : undefined} />
        <Counter label="Escalating" value={data.total_escalating_tracks} color={data.total_escalating_tracks > 0 ? "#ff9e2c" : undefined} />
      </div>
    </div>
  )
}

function Counter({ label, value, color }) {
  return (
    <div className="flex items-center" style={{ gap: 6 }}>
      <span className="label" style={{ fontSize: 8 }}>{label}</span>
      <span className="mono" style={{ fontSize: 12, fontWeight: 700, color: color || "var(--text-bright)" }}>
        {String(value ?? 0).padStart(2, "0")}
      </span>
    </div>
  )
}
