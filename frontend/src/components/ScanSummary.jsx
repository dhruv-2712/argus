import { useState, useEffect } from "react"
import { X, FileText, Radio } from "lucide-react"
import { SOURCE_CODE, THREAT_COLORS } from "../constants"

// Plain-language briefing shown after a scan completes. Reads the `summary`
// block the backend attaches to the scan response. Dismissible; auto-shows on
// each new scan.
export default function ScanSummary({ summary, aoiName, onClose }) {
  const [open, setOpen] = useState(true)
  useEffect(() => { setOpen(true) }, [summary])

  if (!summary || !open) return null

  const {
    narrative, fused_count = 0, raw_count = 0,
    sensors_online = [], sensors_offline = [], threat_counts = {},
  } = summary

  const close = () => { setOpen(false); onClose?.() }

  return (
    <div
      className="brkt"
      style={{
        position: "absolute", top: 96, left: "50%", transform: "translateX(-50%)",
        width: "min(560px, 92vw)", zIndex: 12,
        background: "rgba(8,13,19,0.97)", border: "1px solid var(--accent)",
        boxShadow: "0 0 34px rgba(54,220,235,0.22)", backdropFilter: "blur(6px)",
        maxHeight: "76vh", display: "flex", flexDirection: "column",
      }}
    >
      {/* Header */}
      <div className="flex items-center" style={{ gap: 9, padding: "10px 13px", borderBottom: "1px solid var(--line)" }}>
        <FileText size={14} style={{ color: "var(--accent)" }} />
        <span className="label" style={{ fontSize: 9 }}>Scan Briefing</span>
        <span className="mono" style={{ fontSize: 11.5, color: "var(--text-bright)", letterSpacing: "0.04em" }}>
          {aoiName}
        </span>
        <button onClick={close} className="mono" style={{ marginLeft: "auto", background: "none", border: "1px solid var(--line)", color: "var(--muted)", cursor: "pointer", padding: "3px 6px" }}>
          <X size={12} />
        </button>
      </div>

      {/* Stat strip */}
      <div className="flex" style={{ borderBottom: "1px solid var(--line)", background: "rgba(0,0,0,0.25)" }}>
        <Stat label="Raw Detections" value={raw_count} />
        <Stat label="Fused Contacts" value={fused_count} accent />
        <Stat label="Sensors Online" value={`${sensors_online.length}/${sensors_online.length + sensors_offline.length}`} />
      </div>

      {/* Narrative */}
      <div style={{ overflowY: "auto", padding: "13px 15px" }}>
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.7, color: "var(--text)" }}>
          {narrative}
        </p>

        {/* Threat breakdown chips */}
        {Object.keys(threat_counts).length > 0 && (
          <div style={{ marginTop: 13 }}>
            <div className="label" style={{ marginBottom: 7 }}>Threat Breakdown</div>
            <div className="flex" style={{ gap: 6, flexWrap: "wrap" }}>
              {Object.entries(threat_counts).map(([lvl, cnt]) => (
                <span key={lvl} className="mono" style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
                  color: THREAT_COLORS[lvl] || "var(--muted)",
                  border: `1px solid ${THREAT_COLORS[lvl] || "var(--line)"}`,
                  background: `${THREAT_COLORS[lvl] || "#6c8090"}1a`, padding: "2px 9px",
                }}>
                  {cnt} {lvl.toUpperCase()}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Sensor chips */}
        <div style={{ marginTop: 13 }}>
          <div className="label" style={{ marginBottom: 7 }}>Sensors</div>
          <div className="flex" style={{ gap: 6, flexWrap: "wrap" }}>
            {sensors_online.map(s => (
              <SensorChip key={s} src={s} online />
            ))}
            {sensors_offline.map(s => (
              <SensorChip key={s} src={s} online={false} />
            ))}
          </div>
        </div>

        {/* Replay hint */}
        {fused_count > 0 && (
          <div className="flex items-center" style={{ gap: 8, marginTop: 14, padding: "9px 11px", background: "rgba(54,220,235,0.06)", border: "1px solid var(--line)", borderLeft: "3px solid var(--accent)" }}>
            <Radio size={13} style={{ color: "var(--accent)", flexShrink: 0 }} />
            <span style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>
              Scan this area again later to build track history — a second scan enables
              the <b style={{ color: "var(--text)" }}>Timeline replay</b> and boosts confidence on anything that persists.
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, accent }) {
  return (
    <div style={{ flex: 1, padding: "9px 13px", borderRight: "1px solid var(--line)" }}>
      <div className="label" style={{ fontSize: 8 }}>{label}</div>
      <div className="mono" style={{ fontSize: 18, fontWeight: 700, color: accent ? "var(--accent)" : "var(--text-bright)" }}>
        {value}
      </div>
    </div>
  )
}

function SensorChip({ src, online }) {
  const col = online ? "var(--green)" : "var(--dim)"
  return (
    <span className="mono" style={{
      fontSize: 9.5, fontWeight: 700, letterSpacing: "0.06em", color: col,
      border: `1px solid ${online ? col : "var(--line)"}`, padding: "2px 8px",
      display: "flex", alignItems: "center", gap: 5, opacity: online ? 1 : 0.6,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: col, display: "inline-block" }} />
      {SOURCE_CODE[src] || src.toUpperCase()}
      {!online && " · OFFLINE"}
    </span>
  )
}
