import { useState, useEffect, useRef, useMemo } from "react"
import { Search, MapPin, Zap, Volume2, VolumeX, Crosshair } from "lucide-react"
import { toggleMuted, isMuted } from "../lib/sound"

// ⌘K / Ctrl-K tactical command palette. Fuzzy-ish prefix search over AOIs
// and global actions.
export default function CommandPalette({ aois, onSelectAOI, onScan }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const [active, setActive] = useState(0)
  const [muted, setMutedState] = useState(isMuted())
  const inputRef = useRef(null)

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen((o) => !o)
      } else if (e.key === "Escape") {
        setOpen(false)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  useEffect(() => {
    if (open) { setQ(""); setActive(0); setTimeout(() => inputRef.current?.focus(), 30) }
  }, [open])

  const items = useMemo(() => {
    const actions = [
      { kind: "action", id: "mute", label: muted ? "Unmute Audio" : "Mute Audio", icon: muted ? VolumeX : Volume2,
        run: () => setMutedState(toggleMuted()) },
    ]
    const aoiItems = (aois || []).map((a) => ({
      kind: "aoi", id: a.id, label: a.name, sub: a.domain?.toUpperCase(), icon: MapPin,
      run: () => { onSelectAOI(a); setOpen(false) },
      scan: () => { onScan(a.id); setOpen(false) },
    }))
    const scanItems = (aois || []).map((a) => ({
      kind: "scan", id: "scan-" + a.id, label: `Scan ${a.name}`, icon: Zap,
      run: () => { onScan(a.id); setOpen(false) },
    }))
    const all = [...actions, ...aoiItems, ...scanItems]
    if (!q.trim()) return all
    const needle = q.toLowerCase()
    return all.filter((i) => i.label.toLowerCase().includes(needle))
  }, [aois, q, muted, onSelectAOI, onScan])

  useEffect(() => { if (active >= items.length) setActive(0) }, [items, active])

  if (!open) return null

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)) }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === "Enter") { e.preventDefault(); items[active]?.run() }
  }

  return (
    <div
      onClick={() => setOpen(false)}
      style={{ position: "fixed", inset: 0, zIndex: 9500, background: "rgba(2,6,10,0.7)", backdropFilter: "blur(3px)", display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: "12vh" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="brkt"
        style={{ width: "min(560px, 92vw)", background: "var(--panel)", border: "1px solid var(--accent)", boxShadow: "0 0 40px rgba(54,220,235,0.25)" }}
      >
        <div className="flex items-center" style={{ gap: 9, padding: "12px 14px", borderBottom: "1px solid var(--line)" }}>
          <Crosshair size={15} style={{ color: "var(--accent)" }} />
          <Search size={14} style={{ color: "var(--muted)" }} />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Command — jump to area, run scan…"
            className="mono"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--text-bright)", fontSize: 13, letterSpacing: "0.03em" }}
          />
          <span className="mono label" style={{ fontSize: 8 }}>ESC</span>
        </div>

        <div style={{ maxHeight: 360, overflowY: "auto", padding: 6 }}>
          {items.length === 0 && (
            <div className="mono" style={{ color: "var(--dim)", fontSize: 11, textAlign: "center", padding: 20, letterSpacing: "0.1em" }}>
              NO MATCHING COMMANDS
            </div>
          )}
          {items.map((it, i) => {
            const Icon = it.icon
            const on = i === active
            return (
              <div
                key={it.id}
                onMouseEnter={() => setActive(i)}
                onClick={it.run}
                className="mono flex items-center"
                style={{
                  gap: 10, padding: "9px 11px", cursor: "pointer",
                  background: on ? "var(--accent-dim)" : "transparent",
                  borderLeft: `2px solid ${on ? "var(--accent)" : "transparent"}`,
                }}
              >
                <Icon size={14} style={{ color: it.kind === "scan" ? "var(--accent)" : "var(--muted)", flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: 12.5, color: on ? "var(--text-bright)" : "var(--text)" }}>{it.label}</span>
                {it.sub && <span className="label" style={{ fontSize: 8 }}>{it.sub}</span>}
                <span className="label" style={{ fontSize: 8, color: "var(--dim)" }}>
                  {it.kind === "aoi" ? "GO" : it.kind === "scan" ? "RUN" : "TOGGLE"}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
