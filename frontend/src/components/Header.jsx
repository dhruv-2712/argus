import { useState, useEffect } from "react"
import { Scan, ChevronDown } from "lucide-react"

function useUtcClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

export default function Header({ aois, selectedAOI, onSelectAOI, onScan, scanning, isMobile }) {
  const now = useUtcClock()
  const hh = String(now.getUTCHours()).padStart(2, "0")
  const mm = String(now.getUTCMinutes()).padStart(2, "0")
  const ss = String(now.getUTCSeconds()).padStart(2, "0")
  const day = now.toUTCString().slice(5, 16).toUpperCase()

  return (
    <header
      className="flex items-center shrink-0 relative"
      style={{
        background: "linear-gradient(180deg, #0c141d, #0a1017)",
        borderBottom: "1px solid var(--line)",
        height: isMobile ? 48 : 56,
        padding: isMobile ? "0 10px" : "0 16px",
        gap: isMobile ? 10 : 16,
      }}
    >
      <div className="scanbar" style={{ opacity: scanning ? 1 : 0 }} />

      {/* Wordmark */}
      <div className="flex items-center" style={{ gap: isMobile ? 8 : 11 }}>
        <div style={{ width: 3, height: isMobile ? 24 : 30, background: "var(--accent)", boxShadow: "0 0 10px var(--accent-glow)" }} />
        <div style={{ lineHeight: 1.1 }}>
          <div
            className="mono glow-text"
            style={{ fontSize: isMobile ? 17 : 21, fontWeight: 700, letterSpacing: "0.34em", color: "var(--text-bright)" }}
          >
            ARGUS
          </div>
          {!isMobile && (
            <div className="label" style={{ fontSize: 7.5, letterSpacing: "0.22em", marginTop: 1 }}>
              Geospatial Intelligence Fusion
            </div>
          )}
        </div>
      </div>

      <div style={{ width: 1, height: isMobile ? 24 : 30, background: "var(--line)" }} />

      {/* AO selector */}
      <div className="flex items-center" style={{ gap: 8 }}>
        <span className="label">AO</span>
        <div className="relative">
          <select
            value={selectedAOI?.id || ""}
            onChange={(e) => {
              const found = aois.find((a) => a.id === e.target.value)
              onSelectAOI(found || null)
            }}
            className="mono"
            style={{
              background: "#060b10", border: "1px solid var(--line)", color: "var(--text-bright)",
              borderRadius: 0, padding: isMobile ? "5px 26px 5px 8px" : "6px 30px 6px 11px", fontSize: isMobile ? 11 : 12.5,
              appearance: "none", cursor: "pointer", letterSpacing: "0.04em", minWidth: isMobile ? 110 : 190,
            }}
          >
            <option value="">{isMobile ? "— SELECT —" : "— SELECT AREA —"}</option>
            {aois.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
          <ChevronDown
            size={14}
            style={{ position: "absolute", right: 9, top: "50%", transform: "translateY(-50%)", pointerEvents: "none", color: "var(--accent)" }}
          />
        </div>
      </div>

      {/* SCAN command */}
      <button
        disabled={!selectedAOI || scanning}
        onClick={() => selectedAOI && onScan(selectedAOI.id)}
        className="mono"
        style={{
          background: scanning ? "rgba(54,220,235,0.08)" : (selectedAOI ? "var(--accent-dim)" : "#0c1219"),
          border: `1px solid ${selectedAOI && !scanning ? "var(--accent)" : "var(--line)"}`,
          color: selectedAOI && !scanning ? "var(--accent)" : "var(--dim)",
          borderRadius: 0, padding: isMobile ? "6px 10px" : "7px 16px", fontSize: isMobile ? 11 : 12, letterSpacing: "0.14em", fontWeight: 700,
          cursor: selectedAOI && !scanning ? "pointer" : "not-allowed",
          display: "flex", alignItems: "center", gap: 7, textTransform: "uppercase",
          boxShadow: selectedAOI && !scanning ? "0 0 10px rgba(54,220,235,0.25)" : "none",
          transition: "all 0.15s",
        }}
      >
        {scanning ? (
          <>
            <span style={{ display: "inline-block", animation: "spin 0.9s linear infinite", width: 13, height: 13, border: "2px solid rgba(54,220,235,0.25)", borderTopColor: "var(--accent)", borderRadius: "50%" }} />
            {!isMobile && "Scanning"}
          </>
        ) : (
          <><Scan size={14} /> {isMobile ? "Scan" : "Initiate Scan"}</>
        )}
      </button>

      {/* Right telemetry cluster (desktop only) */}
      {!isMobile && (
        <div className="flex items-center" style={{ marginLeft: "auto", gap: 16 }}>
          <Telemetry label={`UTC · ${day}`} value={`${hh}:${mm}:${ss}`} accent />
          <div style={{ width: 1, height: 30, background: "var(--line)" }} />
          <Telemetry label="Tracked AO" value={String(aois.length).padStart(2, "0")} />
          <div style={{ width: 1, height: 30, background: "var(--line)" }} />
          <div className="flex items-center" style={{ gap: 7 }}>
            <span className="status-dot" style={{ color: "var(--green)", background: "var(--green)" }} />
            <div style={{ lineHeight: 1.15 }}>
              <div className="label" style={{ fontSize: 7.5 }}>System</div>
              <div className="mono" style={{ fontSize: 11, color: "var(--green)", letterSpacing: "0.1em" }}>NOMINAL</div>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}

function Telemetry({ label, value, accent }) {
  return (
    <div style={{ textAlign: "right", lineHeight: 1.15 }}>
      <div className="label" style={{ fontSize: 7.5 }}>{label}</div>
      <div className="mono" style={{ fontSize: 13, letterSpacing: "0.08em", color: accent ? "var(--accent)" : "var(--text-bright)" }}>
        {value}
      </div>
    </div>
  )
}
