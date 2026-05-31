import { Plus, Zap, Power, PowerOff } from "lucide-react"
import { api } from "../api/client"
import { useQueryClient } from "@tanstack/react-query"
import { useScan } from "../hooks/useArgusData"

export default function AOIList({ aois, onCreateClick, onAOISelect }) {
  const qc = useQueryClient()
  const scan = useScan()

  const toggle = async (aoi) => {
    await api.toggleAOI(aoi.id, !aoi.active)
    qc.invalidateQueries({ queryKey: ["aois"] })
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div
        className="flex items-center justify-between"
        style={{ padding: "11px 13px", borderBottom: "1px solid var(--line)", background: "rgba(0,0,0,0.2)" }}
      >
        <span className="label" style={{ fontSize: 10 }}>Areas of Interest</span>
        <button
          onClick={onCreateClick}
          className="mono"
          style={{ background: "var(--accent-dim)", border: "1px solid var(--accent)", borderRadius: 0, padding: "4px 10px", color: "var(--accent)", fontSize: 10, cursor: "pointer", display: "flex", alignItems: "center", gap: 5, fontWeight: 700, letterSpacing: "0.08em" }}
        >
          <Plus size={12} /> NEW
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
        {aois.length === 0 && (
          <div className="mono" style={{ color: "var(--dim)", fontSize: 11, textAlign: "center", padding: "28px 0", letterSpacing: "0.08em" }}>
            NO AREAS DEFINED · PLOT ONE ON MAP
          </div>
        )}
        {aois.map(a => (
          <div
            key={a.id}
            onClick={() => onAOISelect(a)}
            style={{ background: "var(--panel-2)", border: "1px solid var(--line)", borderLeft: `3px solid ${a.active ? "var(--green)" : "var(--dim)"}`, padding: 11, marginBottom: 8, cursor: "pointer", transition: "all 0.13s" }}
            onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent)"}
            onMouseLeave={e => e.currentTarget.style.borderColor = "var(--line)"}
          >
            <div className="flex items-center justify-between" style={{ marginBottom: 5 }}>
              <span className="mono" style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-bright)", letterSpacing: "0.02em" }}>{a.name}</span>
              <span className="mono flex items-center" style={{ gap: 5, color: a.active ? "var(--green)" : "var(--dim)", fontSize: 9, fontWeight: 700, letterSpacing: "0.1em" }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: a.active ? "var(--green)" : "var(--dim)", boxShadow: a.active ? "0 0 6px var(--green)" : "none" }} />
                {a.active ? "ACTIVE" : "STANDBY"}
              </span>
            </div>
            <div className="mono" style={{ fontSize: 10, color: "var(--muted)", marginBottom: 9, letterSpacing: "0.04em" }}>
              {a.domain?.toUpperCase()} · REVISIT {a.revisit_hours}H
            </div>
            <div className="flex" style={{ gap: 6 }}>
              <button
                onClick={e => { e.stopPropagation(); toggle(a) }}
                className="mono"
                style={{ background: "transparent", border: "1px solid var(--line)", borderRadius: 0, padding: "4px 9px", fontSize: 9.5, color: a.active ? "var(--green)" : "var(--muted)", cursor: "pointer", display: "flex", alignItems: "center", gap: 5, fontWeight: 700, letterSpacing: "0.06em" }}
              >
                {a.active ? <Power size={11} /> : <PowerOff size={11} />}
                {a.active ? "DEACTIVATE" : "ACTIVATE"}
              </button>
              <button
                onClick={e => { e.stopPropagation(); scan.mutate({ id: a.id }) }}
                disabled={scan.isPending}
                className="mono"
                style={{ background: "var(--accent-dim)", border: "1px solid var(--accent)", borderRadius: 0, padding: "4px 9px", fontSize: 9.5, color: "var(--accent)", cursor: "pointer", display: "flex", alignItems: "center", gap: 5, fontWeight: 700, letterSpacing: "0.06em" }}
              >
                <Zap size={11} /> SCAN
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
