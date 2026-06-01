import { useState, useEffect, lazy, Suspense } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { PenLine, X, AlertTriangle, CheckCircle2, History, Radio } from "lucide-react"
import Header from "./components/Header"
import RightPanel from "./components/RightPanel"
import CreateAOIModal from "./components/CreateAOIModal"
import TheaterPosture from "./components/TheaterPosture"
import BootSequence from "./components/BootSequence"
import ScanOverlay from "./components/ScanOverlay"
import CommandPalette from "./components/CommandPalette"
import TimelineScrubber from "./components/TimelineScrubber"
import { useAOIs, useContacts, useScan } from "./hooks/useArgusData"
import { useLiveFeed } from "./hooks/useLiveFeed"
import { scanStart, bootHum } from "./lib/sound"

// Code-split the heavy map bundle (MapLibre) so first paint is fast.
const Map = lazy(() => import("./components/Map"))

const qc = new QueryClient()

function ArgusApp() {
  const { data: aois = [] } = useAOIs()
  const [selectedAOI, setSelectedAOI] = useState(null)
  const [contactFilters, setContactFilters] = useState({})
  const { data: contacts = [] } = useContacts(contactFilters)
  const scan = useScan()
  const { connected: liveConnected, lastEvent } = useLiveFeed()
  const [selectedContact, setSelectedContact] = useState(null)
  const [booted, setBooted] = useState(() => sessionStorage.getItem("argus_booted") === "1")
  const [drawMode, setDrawMode] = useState(false)
  const [pendingBbox, setPendingBbox] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [scanError, setScanError] = useState(null)
  const [showTimeline, setShowTimeline] = useState(false)

  useEffect(() => {
    setContactFilters(selectedAOI ? { aoi_id: selectedAOI.id } : {})
  }, [selectedAOI])

  const handleScan = async (id) => {
    setScanError(null)
    scanStart()
    try {
      await scan.mutateAsync({ id })
    } catch (e) {
      setScanError(e.message)
      setTimeout(() => setScanError(null), 5000)
    }
  }

  const handleDrawComplete = (bbox) => {
    setDrawMode(false)
    setPendingBbox(bbox)
    setShowModal(true)
  }

  const layerErrors = scan.data?.layer_errors && Object.keys(scan.data.layer_errors).length > 0
    ? Object.keys(scan.data.layer_errors)
    : null

  if (!booted) {
    return <BootSequence onDone={() => { sessionStorage.setItem("argus_booted", "1"); bootHum(); setBooted(true) }} />
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg)" }}>
      {/* Cinematic atmosphere */}
      <div className="crt-overlay" />
      <div className="uplink-sheen" />

      {/* Classification banner */}
      <div
        className="mono"
        style={{
          height: 18, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center",
          background: "#0c1a12", borderBottom: "1px solid #163424", color: "var(--green)",
          fontSize: 9, letterSpacing: "0.28em", textTransform: "uppercase",
        }}
      >
        Unclassified // Open-Source Intelligence // ARGUS C2 — For Research Use Only
      </div>

      <Header
        aois={aois}
        selectedAOI={selectedAOI}
        onSelectAOI={setSelectedAOI}
        onScan={handleScan}
        scanning={scan.isPending}
      />

      <TheaterPosture aois={aois} onSelectAOI={setSelectedAOI} />

      {/* Live-feed flash banner */}
      {lastEvent && Date.now() - lastEvent.at < 6000 && (
        <AlertStrip kind={lastEvent.has_critical ? "error" : "ok"} icon={<Radio size={13} />}>
          LIVE — {lastEvent.aoi_name?.toUpperCase()}: {lastEvent.fused_count} CONTACT(S), MAX THREAT {String(lastEvent.max_threat).toUpperCase()}
        </AlertStrip>
      )}

      {scanError && (
        <AlertStrip kind="error" icon={<AlertTriangle size={13} />}>
          SCAN FAULT — {scanError}
        </AlertStrip>
      )}

      {scan.isSuccess && (
        <AlertStrip kind="ok" icon={<CheckCircle2 size={13} />}>
          SCAN COMPLETE — {scan.data?.fused_contacts?.length ?? 0} FUSED CONTACT(S) RESOLVED
          {layerErrors && (
            <span style={{ color: "var(--amber)", marginLeft: 14 }}>
              ⚠ SENSORS OFFLINE: {layerErrors.join(", ").toUpperCase()}
            </span>
          )}
        </AlertStrip>
      )}

      <div style={{ display: "flex", flex: 1, overflow: "hidden", minHeight: 0 }}>
        <div style={{ flex: 1, position: "relative", overflow: "hidden", minHeight: 0 }}>
          {/* Draw AOI command */}
          <button
            onClick={() => setDrawMode((m) => !m)}
            className="mono"
            style={{
              position: "absolute", top: 52, left: 14, zIndex: 10,
              background: drawMode ? "var(--accent)" : "rgba(11,18,26,0.92)",
              border: `1px solid ${drawMode ? "var(--accent)" : "var(--line)"}`,
              borderRadius: 0, padding: "7px 11px",
              color: drawMode ? "#04141a" : "var(--text)", cursor: "pointer",
              fontSize: 10.5, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase",
              display: "flex", alignItems: "center", gap: 6,
              boxShadow: drawMode ? "0 0 14px var(--accent-glow)" : "0 2px 8px rgba(0,0,0,0.5)",
              backdropFilter: "blur(4px)",
            }}
          >
            {drawMode ? <X size={13} /> : <PenLine size={13} />}
            {drawMode ? "Cancel Plot" : "Plot AO"}
          </button>

          {/* Timeline toggle (only when an AOI is selected) */}
          {selectedAOI && (
            <button
              onClick={() => setShowTimeline((t) => !t)}
              className="mono"
              style={{
                position: "absolute", top: 52, left: 128, zIndex: 10,
                background: showTimeline ? "var(--accent)" : "rgba(11,18,26,0.92)",
                border: `1px solid ${showTimeline ? "var(--accent)" : "var(--line)"}`,
                borderRadius: 0, padding: "7px 11px",
                color: showTimeline ? "#04141a" : "var(--text)", cursor: "pointer",
                fontSize: 10.5, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase",
                display: "flex", alignItems: "center", gap: 6,
                boxShadow: showTimeline ? "0 0 14px var(--accent-glow)" : "0 2px 8px rgba(0,0,0,0.5)",
                backdropFilter: "blur(4px)",
              }}
            >
              <History size={13} /> Timeline
            </button>
          )}

          {/* Live feed status pill */}
          <div
            className="mono"
            style={{
              position: "absolute", top: 52, right: 14, zIndex: 10,
              display: "flex", alignItems: "center", gap: 6,
              background: "rgba(7,11,16,0.88)", border: "1px solid var(--line)", padding: "5px 10px",
              fontSize: 9.5, letterSpacing: "0.12em",
              color: liveConnected ? "var(--green)" : "var(--dim)",
            }}
          >
            <span className="status-dot" style={{ color: liveConnected ? "var(--green)" : "var(--dim)", background: liveConnected ? "var(--green)" : "var(--dim)" }} />
            {liveConnected ? "LIVE FEED" : "OFFLINE"}
          </div>

          <Suspense fallback={<div className="mono" style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--accent)", letterSpacing: "0.2em", fontSize: 12 }}>INITIALIZING TACTICAL DISPLAY…</div>}>
            <Map
              aois={aois}
              contacts={contacts}
              selectedAOI={selectedAOI}
              selectedContact={selectedContact}
              onContactClick={setSelectedContact}
              drawMode={drawMode}
              onDrawComplete={handleDrawComplete}
            />
          </Suspense>
          <ScanOverlay active={scan.isPending} />

          {showTimeline && selectedAOI && (
            <TimelineScrubber
              aoiId={selectedAOI.id}
              aoiName={selectedAOI.name}
              onClose={() => setShowTimeline(false)}
              onSeekContact={(t) => setSelectedContact({ ...t, id: t.track_id, simulation_run: false, threat_level: t.latest_threat })}
            />
          )}
        </div>

        <RightPanel
          contacts={contacts}
          aois={aois}
          selectedAOI={selectedAOI}
          onAOISelect={setSelectedAOI}
          onContactSelect={setSelectedContact}
          onCreateAOI={() => { setPendingBbox(null); setShowModal(true) }}
        />
      </div>

      {showModal && (
        <CreateAOIModal bbox={pendingBbox} onClose={() => { setShowModal(false); setPendingBbox(null) }} />
      )}

      <CommandPalette aois={aois} onSelectAOI={setSelectedAOI} onScan={handleScan} />
    </div>
  )
}

function AlertStrip({ kind, icon, children }) {
  const c = kind === "error" ? "var(--red)" : "var(--green)"
  const bg = kind === "error" ? "rgba(255,66,66,0.07)" : "rgba(47,224,110,0.06)"
  return (
    <div
      className="mono flex items-center shrink-0"
      style={{
        gap: 9, background: bg, borderBottom: `1px solid ${c}33`, borderLeft: `3px solid ${c}`,
        color: c, fontSize: 11, letterSpacing: "0.08em", padding: "7px 16px",
      }}
    >
      {icon}
      {children}
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <ArgusApp />
    </QueryClientProvider>
  )
}
