const BASE = import.meta.env.VITE_API_URL || "http://localhost:8002"

// crypto.randomUUID is only defined in secure contexts (HTTPS/localhost).
// Fall back so a non-secure origin never hard-crashes the first API call.
function uuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID()
  return "dev-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10)
}

function getDeviceId() {
  let id = localStorage.getItem("argus_device_id")
  if (!id) {
    id = uuid()
    localStorage.setItem("argus_device_id", id)
  }
  return id
}

// Default 30s timeout; scans get longer (free-tier cold starts + heavy work).
async function req(url, opts = {}) {
  const { timeoutMs = 30000, ...fetchOpts } = opts
  const headers = { "X-Device-ID": getDeviceId(), ...(fetchOpts.headers || {}) }
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const r = await fetch(BASE + url, { ...fetchOpts, headers, signal: ctrl.signal })
    if (!r.ok) {
      const body = await r.text()
      let detail = body
      try {
        const j = JSON.parse(body)
        detail = typeof j.detail === "string" ? j.detail : (j.detail?.detail || body)
      } catch { /* non-JSON body */ }
      throw new Error(detail || `Request failed (${r.status})`)
    }
    return await r.json()
  } catch (e) {
    if (e.name === "AbortError") {
      throw new Error("Request timed out — the backend may be waking from sleep (free tier). Try again in ~30s.")
    }
    throw e
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  listAOIs: () => req("/aoi"),
  createAOI: (data) => req("/aoi", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  deleteAOI: (id) => req(`/aoi/${id}`, { method: "DELETE" }),
  toggleAOI: (id, active) => req(`/aoi/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active }) }),
  getAOIStatus: (id) => req(`/aoi/${id}/status`),
  scanAOI: (id, layers = null) => req(`/aoi/${id}/scan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(layers ? { layers } : {}), timeoutMs: 150000 }),
  getContacts: (params) => req(`/contacts?${new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v)))}`),
  getContact: (id) => req(`/contacts/${id}`),
  simulate: (aoi_id, contact_id) => req(`/aoi/${aoi_id}/simulate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ contact_id }), timeoutMs: 60000 }),
  generateReport: (id) => req(`/aoi/${id}/report`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ include_fused_contacts: true, threat_threshold: "low" }), timeoutMs: 60000 }),
  listReports: (id) => req(`/aoi/${id}/reports`),
  downloadReportUrl: (id) => `${BASE}/reports/${id}/pdf`,
  getRegional: () => req("/intel/regional"),
  getTracks: (id) => req(`/intel/aoi/${id}/tracks`),
  getTerrain: (lat, lon) => req(`/intel/terrain?lat=${lat}&lon=${lon}`),
}
