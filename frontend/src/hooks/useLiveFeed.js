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
  const retryDelayRef = useRef(4000)

  useEffect(() => {
    let closed = false

    // Exponential backoff (4s → 60s cap) so a dead backend isn't hammered
    // every 4s by every open tab; resets once a connection succeeds.
    const scheduleRetry = () => {
      if (closed) return
      retryRef.current = setTimeout(connect, retryDelayRef.current)
      retryDelayRef.current = Math.min(retryDelayRef.current * 2, 60000)
    }

    const connect = () => {
      if (closed) return
      let ws
      try {
        ws = new WebSocket(wsUrl())
      } catch {
        scheduleRetry()
        return
      }
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        retryDelayRef.current = 4000
      }
      ws.onclose = () => {
        setConnected(false)
        scheduleRetry()
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (msg) => {
        let evt
        try { evt = JSON.parse(msg.data) } catch { return }
        if (evt.type === "scan_complete" || evt.type === "auto_scan_complete") {
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
