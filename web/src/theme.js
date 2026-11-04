// Applies an edition's palette: CSS variables for the UI and a hex re-map for the Plotly charts.
export function mix(a, b, t) {
  const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16)
  const ch = (s) => Math.round(((pa >> s) & 255) * (1 - t) + ((pb >> s) & 255) * t)
  return '#' + [16, 8, 0].map((s) => ch(s).toString(16).padStart(2, '0')).join('')
}

export function applyTheme(theme) {
  const r = document.documentElement.style
  r.setProperty('--bg', theme.bg)
  r.setProperty('--primary', theme.primary)
  r.setProperty('--secondary', theme.secondary)
  r.setProperty('--tertiary', theme.tertiary)
  r.setProperty('--panel', mix(theme.bg, '#ffffff', 0.06))
  r.setProperty('--panel2', mix(theme.bg, '#ffffff', 0.11))
  r.setProperty('--border', mix(theme.bg, '#ffffff', 0.17))
  theme.chart.forEach((c, i) => r.setProperty(`--c${i + 1}`, c))
}

// Plotly figures are built in Python with a fixed base palette; swap those hex codes for the edition's.
export function makeRecolor(baseSlots, theme, defaultBg = '#0A0F1E') {
  const map = {}
  baseSlots.forEach((h, i) => (map[h.toLowerCase()] = theme.chart[i]))
  map['#c58bff'] = mix(theme.chart[4], '#ffffff', 0.25)
  map['#ffd166'] = mix(theme.chart[1], '#ffffff', 0.35)
  map['#1f4fa3'] = mix(theme.chart[0], theme.bg, 0.55)
  map['#101a33'] = mix(theme.bg, '#ffffff', 0.05)
  map['#6b3fa0'] = mix(theme.chart[4], theme.bg, 0.45)
  map['#1b2540'] = mix(theme.bg, '#ffffff', 0.09)
  map['#0a0f1e'] = theme.bg
  const keys = Object.keys(map)
  const re = new RegExp(keys.join('|'), 'gi')
  const same = theme.chart.every((c, i) => c.toLowerCase() === baseSlots[i].toLowerCase()) && theme.bg.toLowerCase() === defaultBg.toLowerCase()
  return (obj) => (same ? obj : JSON.parse(JSON.stringify(obj).replace(re, (m) => map[m.toLowerCase()])))
}
