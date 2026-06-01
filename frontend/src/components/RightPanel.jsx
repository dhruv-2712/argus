import { useState, useEffect } from "react"
import { List, Activity, Square } from "lucide-react"
import ContactCard from "./ContactCard"
import ContactDetail from "./ContactDetail"
import AOIList from "./AOIList"
import StatusTab from "./StatusTab"
import { THREAT_COLORS, SOURCE_COLORS, SOURCE_CODE, THREAT_ORDER } from "../constants"
import { api } from "../api/client"

const PANEL_W = 388

function TabButton({ active, onClick, icon, label, count }) {
  return (
    <button
      onClick={onClick}
      className="mono"
      style={{
        flex: 1, background: active ? "var(--accent-dim)" : "transparent", border: "none",
        borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
        color: active ? "var(--accent)" : "var(--muted)", cursor: "pointer",
        padding: "11px 0", fontSize: 11, fontWeight: 700, letterSpacing: "0.12em",
        display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
        textTransform: "uppercase", transition: "all 0.15s",
      }}
    >
      {icon}
      {label}
      {count != null && (
        <span style={{ color: active ? "var(--accent)" : "var(--dim)", fontSize: 10 }}>
          [{String(count).padStart(2, "0")}]
        </span>
      )}
    </button>
  )
}

export default function RightPanel({ contacts, aois, selectedAOI, onAOISelect, onContactSelect, onCreateAOI }) {
  const [tab, setTab] = useState("contacts")
  const [selectedContact, setSelectedContact] = useState(null)
  const [specter, setSpecter] = useState(null)
  const [threatFilter, setThreatFilter] = useState("all")
  const [sourceFilter, setSourceFilter] = useState("all")
  const [status, setStatus] = useState(null)

  useEffect(() => {
    if (selectedAOI) {
      api.getAOIStatus(selectedAOI.id).then(setStatus).catch(() => {})
      setTab("contacts")
    }
  }, [selectedAOI, contacts])

  const filtered = (contacts || []).filter(c => {
    if (threatFilter !== "all" && c.threat_level !== threatFilter) return false
    if (sourceFilter !== "all" && !c.sources?.includes(sourceFilter)) return false
    return true
  }).sort((a, b) => {
    const ai = THREAT_ORDER.indexOf(a.threat_level)
    const bi = THREAT_ORDER.indexOf(b.threat_level)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })

  const handleContactClick = (c) => {
    setSelectedContact(c)
    setSpecter(null)
    onContactSelect?.(c)
  }

  const shell = {
    width: PANEL_W, borderLeft: "1px solid var(--line)",
    background: "linear-gradient(180deg, #0b121a, #090e14)",
    display: "flex", flexDirection: "column",
  }

  if (selectedContact) {
    return (
      <div style={shell}>
        <ContactDetail contact={selectedContact} specter={specter} onBack={() => setSelectedContact(null)} />
      </div>
    )
  }

  return (
    <div style={shell}>
      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--line)", background: "#0a1017" }}>
        <TabButton active={tab === "contacts"} onClick={() => setTab("contacts")} icon={<List size={12} />} label="Contacts" count={contacts?.length || 0} />
        <TabButton active={tab === "aois"} onClick={() => setTab("aois")} icon={<Square size={12} />} label="Areas" />
        <TabButton active={tab === "status"} onClick={() => setTab("status")} icon={<Activity size={12} />} label="Status" />
      </div>

      {tab === "contacts" && (
        <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
          {/* Filters */}
          <div style={{ padding: "11px 13px", borderBottom: "1px solid var(--line)", background: "rgba(0,0,0,0.2)" }}>
            <div className="label" style={{ marginBottom: 7 }}>Threat Filter</div>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 11 }}>
              {["all", ...THREAT_ORDER].map(t => {
                const on = threatFilter === t
                const col = t === "all" ? "var(--accent)" : THREAT_COLORS[t]
                return (
                  <FilterPill key={t} on={on} color={col} onClick={() => setThreatFilter(t)}>
                    {t.toUpperCase()}
                  </FilterPill>
                )
              })}
            </div>
            <div className="label" style={{ marginBottom: 7 }}>Sensor Filter</div>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
              {["all", "optical", "sar", "events", "maritime"].map(s => {
                const on = sourceFilter === s
                const col = s === "all" ? "var(--accent)" : SOURCE_COLORS[s]
                return (
                  <FilterPill key={s} on={on} color={col} onClick={() => setSourceFilter(s)}>
                    {s === "all" ? "ALL" : (SOURCE_CODE[s] || s.toUpperCase())}
                  </FilterPill>
                )
              })}
            </div>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
            {filtered.length === 0 ? (
              <div className="mono" style={{ color: "var(--dim)", fontSize: 11, textAlign: "center", padding: "28px 0", letterSpacing: "0.1em" }}>
                NO CONTACTS MATCH FILTER
              </div>
            ) : (
              filtered.map(c => <ContactCard key={c.id} contact={c} onClick={handleContactClick} />)
            )}
          </div>
        </div>
      )}

      {tab === "aois" && (
        <div style={{ flex: 1, overflow: "hidden" }}>
          <AOIList aois={aois} onCreateClick={onCreateAOI} onAOISelect={onAOISelect} />
        </div>
      )}

      {tab === "status" && (
        <div style={{ flex: 1, overflowY: "auto" }}>
          <StatusTab selectedAOI={selectedAOI} status={status} />
        </div>
      )}
    </div>
  )
}

function FilterPill({ on, color, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className="mono"
      style={{
        background: on ? `${color}22` : "transparent",
        border: `1px solid ${on ? color : "var(--line)"}`,
        borderRadius: 0, padding: "3px 9px", fontSize: 9.5,
        color: on ? color : "var(--muted)", cursor: "pointer", fontWeight: 700,
        letterSpacing: "0.08em", boxShadow: on ? `0 0 7px ${color}40` : "none", transition: "all 0.12s",
      }}
    >
      {children}
    </button>
  )
}
