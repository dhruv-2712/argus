import { THREAT_COLORS, SOURCE_COLORS, SOURCE_CODE, LIFECYCLE } from "../constants"

function timeAgo(ts) {
  const diff = (Date.now() - new Date(ts)) / 1000
  if (diff < 60) return `${Math.round(diff)}s`
  if (diff < 3600) return `${Math.round(diff / 60)}m`
  if (diff < 86400) return `${Math.round(diff / 3600)}h`
  return `${Math.round(diff / 86400)}d`
}

export default function ContactCard({ contact, onClick }) {
  const color = THREAT_COLORS[contact.threat_level] || "#6c8090"
  const conf = Math.round((contact.confidence || 0) * 100)
  const lc = LIFECYCLE[contact.lifecycle] || LIFECYCLE.new
  const obs = contact.observation_count || 1
  const delta = contact.confidence_delta || 0

  return (
    <div
      onClick={() => onClick(contact)}
      style={{
        position: "relative", background: "var(--panel-2)", border: "1px solid var(--line)",
        borderLeft: `3px solid ${color}`, padding: "9px 11px 9px 12px", cursor: "pointer",
        marginBottom: 7, transition: "all 0.13s",
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--accent)"; e.currentTarget.style.borderLeftColor = color; e.currentTarget.style.background = "var(--panel-3)" }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--line)"; e.currentTarget.style.borderLeftColor = color; e.currentTarget.style.background = "var(--panel-2)" }}
    >
      {/* Top row: threat tag + id + age */}
      <div className="flex items-center justify-between" style={{ marginBottom: 6 }}>
        <span
          className="mono"
          style={{
            color, border: `1px solid ${color}`, background: `${color}1a`,
            padding: "1px 7px", fontSize: 9.5, fontWeight: 700, letterSpacing: "0.1em",
          }}
        >
          {contact.threat_level?.toUpperCase()}
        </span>
        <div className="flex items-center mono" style={{ gap: 9, fontSize: 9.5, color: "var(--dim)" }}>
          <span>#{contact.id?.slice(0, 6)}</span>
          <span style={{ color: "var(--muted)" }}>T-{timeAgo(contact.timestamp)}</span>
        </div>
      </div>

      {/* Lifecycle / track strip */}
      <div className="flex items-center mono" style={{ gap: 8, marginBottom: 6, fontSize: 9 }}>
        <span style={{ color: lc.color, letterSpacing: "0.08em", fontWeight: 700 }}>
          {lc.glyph} {lc.label}
        </span>
        {obs > 1 && <span style={{ color: "var(--muted)" }}>×{obs} SIGHTINGS</span>}
        {delta !== 0 && (
          <span style={{ color: delta > 0 ? "var(--red)" : "var(--green)" }}>
            {delta > 0 ? "+" : ""}{Math.round(delta * 100)}%
          </span>
        )}
      </div>

      {/* Detection type */}
      <div className="mono" style={{ fontSize: 12, color: "var(--text-bright)", marginBottom: 8, letterSpacing: "0.03em" }}>
        {contact.detection_types?.map(t => t.replace(/_/g, " ").toUpperCase()).join(" · ")}
      </div>

      {/* Bottom row: sources + coords + confidence */}
      <div className="flex items-center justify-between">
        <div className="flex" style={{ gap: 4 }}>
          {(contact.sources || []).map(s => (
            <span
              key={s}
              className="mono"
              style={{
                fontSize: 8.5, fontWeight: 700, letterSpacing: "0.06em",
                color: SOURCE_COLORS[s] || "#6c8090", border: `1px solid ${SOURCE_COLORS[s] || "#6c8090"}66`,
                padding: "0 5px", lineHeight: "15px",
              }}
              title={s}
            >
              {SOURCE_CODE[s] || s.toUpperCase()}
            </span>
          ))}
        </div>
        <span className="mono" style={{ color: "var(--muted)", fontSize: 10 }}>
          {contact.lat?.toFixed(3)}°{contact.lat >= 0 ? "N" : "S"} {contact.lon?.toFixed(3)}°{contact.lon >= 0 ? "E" : "W"}
        </span>
      </div>

      {/* Confidence micro-bar */}
      <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 7 }}>
        <div style={{ flex: 1, height: 3, background: "#0a1119", overflow: "hidden" }}>
          <div style={{ width: `${conf}%`, height: "100%", background: color, boxShadow: `0 0 6px ${color}` }} />
        </div>
        <span className="mono" style={{ color, fontSize: 10, fontWeight: 700, minWidth: 30, textAlign: "right" }}>{conf}%</span>
      </div>
    </div>
  )
}
