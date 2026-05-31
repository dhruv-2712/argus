import { useState } from "react"
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts"
import { FileText, Download } from "lucide-react"
import { useGenerateReport } from "../hooks/useArgusData"
import { api } from "../api/client"
import { THREAT_COLORS, THREAT_ORDER } from "../constants"

export default function StatusTab({ selectedAOI, status }) {
  const gen = useGenerateReport()
  const [report, setReport] = useState(null)

  if (!selectedAOI) return (
    <div className="mono" style={{ padding: "28px 20px", color: "var(--dim)", fontSize: 11, textAlign: "center", letterSpacing: "0.08em" }}>
      SELECT AN AREA OF INTEREST TO VIEW STATUS
    </div>
  )

  const tc = status?.fused_contacts_by_threat || {}
  const chartData = Object.entries(tc)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({ name: k, value: v, color: THREAT_COLORS[k] }))

  const handleGenerate = async () => {
    const r = await gen.mutateAsync(selectedAOI.id)
    setReport(r)
  }

  return (
    <div style={{ padding: 14 }}>
      <div className="label" style={{ marginBottom: 4 }}>Area Report</div>
      <div className="mono" style={{ fontSize: 14, fontWeight: 600, color: "var(--text-bright)", marginBottom: 14, letterSpacing: "0.02em" }}>
        {selectedAOI.name}
      </div>

      {status && (
        <>
          {/* Telemetry rows */}
          <div style={{ border: "1px solid var(--line)", marginBottom: 14 }}>
            <TelemetryRow label="Last Scan" value={status.last_scan ? new Date(status.last_scan).toISOString().slice(0, 16).replace("T", " ") + "Z" : "NEVER"} />
            <TelemetryRow label="Total Contacts" value={String(status.total_contacts).padStart(3, "0")} last />
          </div>

          {/* Threat distribution */}
          <div className="label" style={{ marginBottom: 8 }}>Threat Distribution</div>
          {chartData.length > 0 ? (
            <div className="flex items-center" style={{ marginBottom: 16, gap: 8 }}>
              <div style={{ width: 130, height: 130 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={chartData} dataKey="value" cx="50%" cy="50%" innerRadius={32} outerRadius={56} paddingAngle={2} stroke="#070b10" strokeWidth={2}>
                      {chartData.map((e, i) => <Cell key={i} fill={e.color} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: "var(--panel-2)", border: "1px solid var(--line)", borderRadius: 0, color: "var(--text-bright)", fontSize: 11, fontFamily: "var(--font-mono)" }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div style={{ flex: 1 }}>
                {THREAT_ORDER.filter(t => tc[t] > 0).map(t => (
                  <div key={t} className="flex items-center justify-between" style={{ marginBottom: 5 }}>
                    <div className="flex items-center mono" style={{ gap: 7, fontSize: 10.5, color: "var(--text)", letterSpacing: "0.06em" }}>
                      <span style={{ width: 8, height: 8, background: THREAT_COLORS[t], transform: "rotate(45deg)" }} />
                      {t.toUpperCase()}
                    </div>
                    <span className="mono" style={{ fontSize: 12, color: THREAT_COLORS[t], fontWeight: 700 }}>{String(tc[t]).padStart(2, "0")}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="mono" style={{ color: "var(--dim)", fontSize: 10.5, padding: "12px 0", letterSpacing: "0.06em" }}>NO RESOLVED CONTACTS</div>
          )}
        </>
      )}

      <button
        onClick={handleGenerate}
        disabled={gen.isPending}
        className="mono"
        style={{ width: "100%", background: "var(--panel-2)", border: "1px solid var(--line)", borderRadius: 0, padding: "10px 0", color: "var(--text-bright)", fontSize: 11, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 7, marginBottom: 8, letterSpacing: "0.1em", fontWeight: 700, textTransform: "uppercase" }}
      >
        <FileText size={13} /> {gen.isPending ? "Compiling…" : "Generate Report"}
      </button>

      {report?.pdf_path && (
        <a
          href={api.downloadReportUrl(report.id)}
          target="_blank"
          rel="noreferrer"
          className="mono"
          style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 7, background: "rgba(47,224,110,0.08)", border: "1px solid var(--green)", borderRadius: 0, padding: "10px 0", color: "var(--green)", textDecoration: "none", fontSize: 11, letterSpacing: "0.1em", fontWeight: 700, textTransform: "uppercase", boxShadow: "0 0 10px rgba(47,224,110,0.18)" }}
        >
          <Download size={13} /> Download PDF
        </a>
      )}
    </div>
  )
}

function TelemetryRow({ label, value, last }) {
  return (
    <div
      className="flex items-center justify-between"
      style={{ padding: "8px 11px", borderBottom: last ? "none" : "1px solid var(--line)", background: "var(--panel)" }}
    >
      <span className="label">{label}</span>
      <span className="mono" style={{ fontSize: 11.5, color: "var(--text-bright)", letterSpacing: "0.04em" }}>{value}</span>
    </div>
  )
}
