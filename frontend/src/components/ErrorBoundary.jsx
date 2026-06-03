import { Component } from "react"

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null, retried: false }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("ARGUS render fault:", error, info)
    if (!this.state.retried) {
      this.setState({ error: null, retried: true })
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div
          className="mono"
          style={{
            position: "absolute", inset: 0, zIndex: 50,
            display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
            gap: 14, background: "var(--bg)", color: "var(--text)", padding: 24, textAlign: "center",
          }}
        >
          <div style={{ color: "var(--red)", fontSize: 13, letterSpacing: "0.18em" }}>
            ◢ TACTICAL DISPLAY FAULT
          </div>
          <div style={{ fontSize: 11, color: "var(--dim)", maxWidth: 460, lineHeight: 1.6 }}>
            {this.props.label || "A module failed to load."} This is usually a
            transient network/chunk error.
          </div>
          <div style={{ fontSize: 10, color: "var(--dim)", maxWidth: 460, wordBreak: "break-word" }}>
            {String(this.state.error?.message || this.state.error)}
          </div>
          <button
            onClick={() => { this.setState({ error: null, retried: false }); window.location.reload() }}
            className="mono"
            style={{
              marginTop: 6, background: "var(--accent-dim)", border: "1px solid var(--accent)",
              color: "var(--accent)", padding: "8px 18px", fontSize: 11, letterSpacing: "0.12em",
              cursor: "pointer", textTransform: "uppercase",
            }}
          >
            ↻ Reload Display
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
