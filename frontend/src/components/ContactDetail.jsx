import { useState } from "react"
import { ArrowLeft, Zap, ChevronDown, ChevronRight, MapPin, Clock } from "lucide-react"
import { THREAT_COLORS, SOURCE_COLORS, SOURCE_CODE, LIFECYCLE } from "../constants"
import { useSimulate } from "../hooks/useArgusData"

function OcokaSection({ label, value }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ borderTop: "1px solid var(--line)" }}>
      <button
        onClick={() => setOpen(!open)}
        className="mono"
        style={{
          width: "100%", background: "none", border: "none", color: open ? "var(--accent)" : "var(--text)",
          cursor: "pointer", display: "flex", alignItems: "center", gap: 6, fontSize: 11,
          padding: "8px 0", letterSpacing: "0.08em", textTransform: "uppercase", fontWeight: 600,
        }}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <span>{label.replace(/_/g, " ")}</span>
      </button>
      {open && (
        <p style={{ margin: "0 0 10px 18px", fontSize: 11.5, color: "var(--muted)", lineHeight: 1.55 }}>{value}</p>
      )}
    </div>
  )
}

function DataCell({ icon, label, value }) {
  return (
    <div style={{ flex: 1, border: "1px solid var(--line)", background: "var(--panel)", padding: "7px 9px" }}>
      <div className="label flex items-center" style={{ gap: 4, marginBottom: 3 }}>{icon}{label}</div>
      <div className="mono" style={{ fontSize: 11, color: "var(--text-bright)", letterSpacing: "0.03em" }}>{value}</div>
    </div>
  )
}

function TrackHistory({ contact }) {
  const lc = LIFECYCLE[contact.lifecycle] || LIFECYCLE.new
  const obs = contact.observation_count || 1
  const delta = contact.confidence_delta || 0
  const persistence = Math.round((contact.persistence_score || 0) * 100)
  const firstSeen = contact.first_seen ? new Date(contact.first_seen) : null
  const daysTracked = firstSeen ? Math.max(0, Math.round((Date.now() - firstSeen) / 86400000)) : 0

  return (
    <div style={{ border: "1px solid var(--line)", marginBottom: 14 }}>
      <div className="mono flex items-center justify-between" style={{ background: "var(--panel)", padding: "7px 10px", borderBottom: "1px solid var(--line)" }}>
        <span className="label">Track History</span>
        <span className="mono" style={{ color: lc.color, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em" }}>
          {lc.glyph} {lc.label}
        </span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, background: "var(--line)" }}>
        <HistCell label="Sightings" value={`×${obs}`} />
        <HistCell label="Persistence" value={`${persistence}%`} />
        <HistCell label="First Seen" value={firstSeen ? `${daysTracked}d ago` : "—"} />
        <HistCell
          label="Conf. Trend"
          value={delta === 0 ? "STABLE" : `${delta > 0 ? "+" : ""}${Math.round(delta * 100)}%`}
          color={delta > 0 ? "var(--red)" : delta < 0 ? "var(--green)" : "var(--text-bright)"}
        />
      </div>
    </div>
  )
}

function HistCell({ label, value, color }) {
  return (
    <div style={{ background: "var(--panel)", padding: "7px 10px" }}>
      <div className="label" style={{ marginBottom: 3 }}>{label}</div>
      <div className="mono" style={{ fontSize: 12, color: color || "var(--text-bright)", letterSpacing: "0.03em" }}>{value}</div>
    </div>
  )
}

export default function ContactDetail({ contact, specter, onBack }) {
  const simulate = useSimulate()
  const color = THREAT_COLORS[contact.threat_level] || "#6c8090"
  const conf = Math.round((contact.confidence || 0) * 100)

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div
        className="flex items-center"
        style={{ padding: "11px 14px", borderBottom: "1px solid var(--line)", gap: 10, background: "#0a1017" }}
      >
        <button
          onClick={onBack}
          className="mono"
          style={{ background: "none", border: "1px solid var(--line)", color: "var(--accent)", cursor: "pointer", display: "flex", alignItems: "center", gap: 5, fontSize: 11, padding: "4px 9px", letterSpacing: "0.08em" }}
        >
          <ArrowLeft size={13} /> BACK
        </button>
        <div style={{ lineHeight: 1.2 }}>
          <div className="label" style={{ fontSize: 7.5 }}>Contact Dossier</div>
          <div className="mono" style={{ fontSize: 12, color: "var(--text-bright)" }}>#{contact.id?.slice(0, 8)}</div>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>
        {/* Threat banner */}
        <div
          className="mono flex items-center justify-between"
          style={{ background: `${color}14`, border: `1px solid ${color}`, borderLeft: `3px solid ${color}`, padding: "8px 11px", marginBottom: 12 }}
        >
          <span style={{ color, fontSize: 13, fontWeight: 700, letterSpacing: "0.14em" }}>
            {contact.threat_level?.toUpperCase()} THREAT
          </span>
          <span style={{ color, fontSize: 12, fontWeight: 700 }}>{conf}% CONF</span>
        </div>

        {/* Sources */}
        <div className="label" style={{ marginBottom: 6 }}>Contributing Sensors</div>
        <div className="flex" style={{ gap: 5, marginBottom: 12, flexWrap: "wrap" }}>
          {(contact.sources || []).map(s => (
            <span
              key={s}
              className="mono"
              style={{ color: SOURCE_COLORS[s] || "#6c8090", border: `1px solid ${SOURCE_COLORS[s] || "#6c8090"}`, background: `${SOURCE_COLORS[s] || "#6c8090"}1a`, padding: "2px 9px", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em" }}
            >
              {SOURCE_CODE[s] || s.toUpperCase()}
            </span>
          ))}
        </div>

        {/* Detection types */}
        <div className="label" style={{ marginBottom: 6 }}>Classification</div>
        <div className="mono" style={{ fontSize: 13, color: "var(--text-bright)", marginBottom: 12, letterSpacing: "0.03em" }}>
          {contact.detection_types?.map(t => t.replace(/_/g, " ").toUpperCase()).join(" · ")}
        </div>

        {/* Confidence bar */}
        <div style={{ marginBottom: 12 }}>
          <div className="flex justify-between label" style={{ marginBottom: 5 }}>
            <span>Confidence</span><span style={{ color }}>{conf}%</span>
          </div>
          <div style={{ background: "#0a1119", height: 6, overflow: "hidden", border: "1px solid var(--line)" }}>
            <div style={{ width: `${conf}%`, height: "100%", background: color, boxShadow: `0 0 8px ${color}` }} />
          </div>
        </div>

        {/* Coordinate grid */}
        <div className="flex" style={{ gap: 7, marginBottom: 14 }}>
          <DataCell icon={<MapPin size={9} />} label="Grid" value={`${contact.lat?.toFixed(4)}°${contact.lat >= 0 ? "N" : "S"} ${contact.lon?.toFixed(4)}°${contact.lon >= 0 ? "E" : "W"}`} />
          <DataCell icon={<Clock size={9} />} label="DTG" value={contact.timestamp ? new Date(contact.timestamp).toISOString().slice(0, 16).replace("T", " ") + "Z" : "—"} />
        </div>

        {/* Track history */}
        <TrackHistory contact={contact} />

        {/* SPECTER */}
        {contact.simulation_run && specter ? (
          <div className="brkt" style={{ background: "var(--panel)", border: "1px solid var(--line)", padding: "11px 12px", marginBottom: 12 }}>
            <div className="mono flex items-center" style={{ gap: 7, fontSize: 11.5, fontWeight: 700, color: "var(--accent)", marginBottom: 9, letterSpacing: "0.1em" }}>
              <Zap size={13} /> SPECTER // TERRAIN ASSESSMENT
            </div>
            {specter.ocoka_analysis && Object.entries(specter.ocoka_analysis).filter(([k]) => k !== "tactical_significance").map(([k, v]) => (
              <OcokaSection key={k} label={k} value={v} />
            ))}
            {specter.threat_assessment && (
              <div style={{ marginTop: 11, background: "var(--panel-2)", border: "1px solid var(--line)", borderLeft: "3px solid var(--amber)", padding: "9px 11px" }}>
                <div className="label" style={{ color: "var(--amber)", marginBottom: 6 }}>Threat Assessment</div>
                <div className="mono" style={{ fontSize: 11.5, color: "var(--text-bright)", marginBottom: 5, lineHeight: 1.5 }}>
                  <span style={{ color: "var(--muted)" }}>INTENT:</span> {specter.threat_assessment.probable_intent}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.55 }}>{specter.threat_assessment.projected_activity}</div>
              </div>
            )}
          </div>
        ) : contact.confidence >= 0.5 ? (
          <button
            disabled={simulate.isPending}
            onClick={() => simulate.mutate({ aoiId: contact.aoi_id, contactId: contact.id })}
            className="mono"
            style={{
              width: "100%", background: "var(--accent-dim)", border: "1px solid var(--accent)",
              borderRadius: 0, padding: "10px 0", fontSize: 11.5, color: "var(--accent)", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
              letterSpacing: "0.1em", fontWeight: 700, textTransform: "uppercase",
              boxShadow: "0 0 10px rgba(54,220,235,0.2)",
            }}
          >
            {simulate.isPending
              ? <><span style={{ display: "inline-block", animation: "spin 0.9s linear infinite", width: 12, height: 12, border: "2px solid rgba(54,220,235,0.25)", borderTopColor: "var(--accent)", borderRadius: "50%" }} /> Running SPECTER…</>
              : <><Zap size={13} /> Run SPECTER Analysis</>}
          </button>
        ) : null}

        {/* Summary */}
        {contact.summary && (
          <div style={{ marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 11 }}>
            <div className="label" style={{ marginBottom: 6 }}>Narrative</div>
            <p style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.6, margin: 0 }}>{contact.summary}</p>
          </div>
        )}
      </div>
    </div>
  )
}
