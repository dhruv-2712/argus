// Tactical signal palette — desaturated military C2 / Gotham aesthetic.
export const THREAT_COLORS = {
  critical: "#ff4242",
  high: "#ff9e2c",
  medium: "#ffce3a",
  low: "#6c8090",
}

export const SOURCE_COLORS = {
  optical: "#4a9eff",
  sar: "#b07cff",
  events: "#ff7a45",
  thermal: "#ff6b35",
  flights: "#e0d45a",
}

export const THREAT_ORDER = ["critical", "high", "medium", "low"]

// Short tactical glyph codes for source feeds.
export const SOURCE_CODE = {
  optical: "EO",
  sar: "SAR",
  events: "SIGINT",
  thermal: "THRM",
  flights: "FLGT",
}

// Temporal lifecycle states: color, label, and trend glyph.
export const LIFECYCLE = {
  new: { color: "#36dceb", label: "NEW", glyph: "✦" },
  persistent: { color: "#8aa0b0", label: "PERSISTENT", glyph: "≡" },
  escalating: { color: "#ff4242", label: "ESCALATING", glyph: "▲" },
  deescalating: { color: "#2fe06e", label: "DE-ESCALATING", glyph: "▼" },
  resolved: { color: "#44545f", label: "RESOLVED", glyph: "○" },
}
