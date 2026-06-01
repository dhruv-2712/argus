import { useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { scanComplete, criticalAlert } from "../lib/sound"

// Derive the WS URL from the configured API base.
function wsUrl() {
  const base = import.meta.env.VITE_API_URL || "http://localhost:8002"
  return base.replace(/^http/, "ws") + "/ws/contacts"
}

// Subscribes to the live contact feed. Returns connection status and the
// most recent event (for transient banners). Invalidates queries + plays
// audio cues when a scan resolves server-side.
export function useLiveFeed() {
  const qc = useQueryClient()
  const [connected, setConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState(null)
  const wsRef = useRef(null)
  const retryRef = useRef(null)

  useEffect(() => {
    let closed = false

    const connect = () => {
      if (closed) return
      let ws
      try {
        ws = new WebSocket(wsUrl())
      } catch {
        retryRef.current = setTimeout(connect, 4000)
        return
      }
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retryRef.current = setTimeout(connect, 4000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (msg) => {
        let evt
        try { evt = JSON.parse(msg.data) } catch { return }
        if (evt.type === "scan_complete") {
          qc.invalidateQueries({ queryKey: ["contacts"] })
          qc.invalidateQueries({ queryKey: ["regional"] })
          qc.invalidateQueries({ queryKey: ["aois"] })
          setLastEvent({ ...evt, at: Date.now() })
          if (evt.has_critical) criticalAlert()
          else scanComplete()
        }
      }
    }

    connect()
    return () => {
      closed = true
      clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, [qc])

  return { connected, lastEvent }
}
