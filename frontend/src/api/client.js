const BASE = import.meta.env.VITE_API_URL || "http://localhost:8002"

async function req(url, opts = {}) {
  const r = await fetch(BASE + url, opts)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

export const api = {
  listAOIs: () => req("/aoi"),
  createAOI: (data) => req("/aoi", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  deleteAOI: (id) => req(`/aoi/${id}`, { method: "DELETE" }),
  toggleAOI: (id, active) => req(`/aoi/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active }) }),
  getAOIStatus: (id) => req(`/aoi/${id}/status`),
  scanAOI: (id, layers = null) => req(`/aoi/${id}/scan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(layers ? { layers } : {}) }),
  getContacts: (params) => req(`/contacts?${new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v)))}`),
  getContact: (id) => req(`/contacts/${id}`),
  simulate: (aoi_id, contact_id) => req(`/aoi/${aoi_id}/simulate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ contact_id }) }),
  generateReport: (id) => req(`/aoi/${id}/report`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ include_fused_contacts: true, threat_threshold: "low" }) }),
  listReports: (id) => req(`/aoi/${id}/reports`),
  downloadReportUrl: (id) => `${BASE}/reports/${id}/pdf`,
  getRegional: () => req("/intel/regional"),
  getTracks: (id) => req(`/intel/aoi/${id}/tracks`),
}
