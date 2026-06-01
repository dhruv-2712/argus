// Synthesized tactical sound — no audio assets, pure WebAudio.
// Muteable; preference persists in localStorage.

let ctx = null
let muted = localStorage.getItem("argus_muted") === "1"

function ac() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext
    if (AC) ctx = new AC()
  }
  // Browsers suspend audio until a user gesture; resume on demand.
  if (ctx && ctx.state === "suspended") ctx.resume()
  return ctx
}

export function isMuted() {
  return muted
}

export function setMuted(v) {
  muted = v
  localStorage.setItem("argus_muted", v ? "1" : "0")
}

export function toggleMuted() {
  setMuted(!muted)
  if (!muted) blip()
  return muted
}

// Core tone generator — frequency sweep with an exponential decay envelope.
function tone({ freq = 440, type = "sine", dur = 0.15, gain = 0.08, sweepTo = null } = {}) {
  if (muted) return
  const c = ac()
  if (!c) return
  const osc = c.createOscillator()
  const g = c.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, c.currentTime)
  if (sweepTo) osc.frequency.exponentialRampToValueAtTime(sweepTo, c.currentTime + dur)
  g.gain.setValueAtTime(gain, c.currentTime)
  g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + dur)
  osc.connect(g).connect(c.destination)
  osc.start()
  osc.stop(c.currentTime + dur + 0.02)
}

// UI feedback blip
export function blip() {
  tone({ freq: 660, type: "square", dur: 0.06, gain: 0.04 })
}

// Scan initiated — rising sweep
export function scanStart() {
  tone({ freq: 220, sweepTo: 880, type: "sawtooth", dur: 0.4, gain: 0.05 })
}

// Scan complete — soft two-note confirm
export function scanComplete() {
  tone({ freq: 520, type: "sine", dur: 0.12, gain: 0.05 })
  setTimeout(() => tone({ freq: 780, type: "sine", dur: 0.16, gain: 0.05 }), 110)
}

// CRITICAL contact — urgent radar ping, triple
export function criticalAlert() {
  let n = 0
  const ping = () => {
    tone({ freq: 1040, type: "triangle", dur: 0.18, gain: 0.07, sweepTo: 620 })
    if (++n < 3) setTimeout(ping, 240)
  }
  ping()
}

// Low boot hum on system start
export function bootHum() {
  tone({ freq: 80, type: "sawtooth", dur: 1.2, gain: 0.03, sweepTo: 160 })
}
