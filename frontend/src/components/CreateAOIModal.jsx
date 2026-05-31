import { useState } from "react"
import { X, Crosshair } from "lucide-react"
import { useCreateAOI } from "../hooks/useArgusData"

const fieldStyle = {
  width: "100%", background: "#060b10", border: "1px solid var(--line)", borderRadius: 0,
  padding: "8px 11px", color: "var(--text-bright)", fontSize: 12.5, outline: "none",
  fontFamily: "var(--font-mono)", letterSpacing: "0.03em",
}
const labelStyle = {
  fontSize: 9, color: "var(--muted)", marginBottom: 5, display: "block",
  letterSpacing: "0.16em", textTransform: "uppercase", fontWeight: 600,
}

export default function CreateAOIModal({ bbox, onClose }) {
  const create = useCreateAOI()
  const [form, setForm] = useState({ name: "", domain: "land", revisit_hours: 24 })

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!bbox) return
    await create.mutateAsync({
      name: form.name,
      domain: form.domain,
      revisit_hours: Number(form.revisit_hours),
      bbox,
    })
    onClose()
  }

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(2,5,8,0.82)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, backdropFilter: "blur(3px)" }}>
      <div
        className="brkt"
        style={{ position: "relative", background: "linear-gradient(180deg, #0c141d, #0a0f15)", border: "1px solid var(--line-2)", padding: 22, width: 380, boxShadow: "0 0 40px rgba(0,0,0,0.7), 0 0 0 1px rgba(54,220,235,0.08)" }}
      >
        <span className="frame-corner br" style={{ bottom: -1, right: -1, borderColor: "var(--accent)" }} />

        <div className="flex items-center justify-between" style={{ marginBottom: 18 }}>
          <div className="flex items-center" style={{ gap: 9 }}>
            <Crosshair size={16} style={{ color: "var(--accent)" }} />
            <span className="mono" style={{ fontSize: 13, fontWeight: 700, color: "var(--text-bright)", letterSpacing: "0.14em" }}>DEFINE AREA OF INTEREST</span>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", display: "flex" }}><X size={16} /></button>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 13 }}>
            <label style={labelStyle}>Designation</label>
            <input required style={fieldStyle} value={form.name} onChange={set("name")} placeholder="e.g. SECTOR ALPHA" />
          </div>
          <div style={{ marginBottom: 13 }}>
            <label style={labelStyle}>Domain</label>
            <select style={fieldStyle} value={form.domain} onChange={set("domain")}>
              <option value="land">LAND</option>
              <option value="maritime">MARITIME</option>
              <option value="mixed">MIXED</option>
            </select>
          </div>
          <div style={{ marginBottom: 13 }}>
            <label style={labelStyle}>Revisit Interval (Hours)</label>
            <input type="number" min="1" max="168" style={fieldStyle} value={form.revisit_hours} onChange={set("revisit_hours")} />
          </div>

          {bbox && (
            <div style={{ marginBottom: 18, background: "#060b10", border: "1px solid var(--line)", padding: "8px 11px" }}>
              <div style={labelStyle}>Bounding Box</div>
              <div className="mono" style={{ fontSize: 11, color: "var(--accent)", letterSpacing: "0.04em" }}>
                [{bbox.map(v => v.toFixed(4)).join(", ")}]
              </div>
            </div>
          )}

          <div className="flex" style={{ gap: 8 }}>
            <button
              type="button"
              onClick={onClose}
              className="mono"
              style={{ flex: 1, background: "transparent", border: "1px solid var(--line)", borderRadius: 0, padding: "9px 0", color: "var(--muted)", cursor: "pointer", fontSize: 11, letterSpacing: "0.1em", fontWeight: 700, textTransform: "uppercase" }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={create.isPending}
              className="mono"
              style={{ flex: 1, background: "var(--accent-dim)", border: "1px solid var(--accent)", borderRadius: 0, padding: "9px 0", color: "var(--accent)", cursor: "pointer", fontSize: 11, letterSpacing: "0.1em", fontWeight: 700, textTransform: "uppercase", boxShadow: "0 0 10px rgba(54,220,235,0.2)" }}
            >
              {create.isPending ? "Creating…" : "Commit AO"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
