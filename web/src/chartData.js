// Turn a Plotly figure (as sent by the server) into CSV rows, so any chart's data can be downloaded.
const TYPED = { i1: Int8Array, u1: Uint8Array, i2: Int16Array, u2: Uint16Array, i4: Int32Array, u4: Uint32Array, f4: Float32Array, f8: Float64Array }

function decode(v) {
  if (v && typeof v === 'object' && !Array.isArray(v) && v.bdata && v.dtype) {
    const bin = atob(v.bdata)
    const buf = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i)
    const T = TYPED[v.dtype] || Float64Array
    const arr = Array.from(new T(buf.buffer))
    if (Array.isArray(v.shape) === false && typeof v.shape === 'string' && v.shape.includes(',')) {
      const [r, c] = v.shape.split(',').map(Number)
      const out = []
      for (let i = 0; i < r; i++) out.push(arr.slice(i * c, (i + 1) * c))
      return out
    }
    return arr
  }
  return v
}

const FLAT = ['x', 'y', 'text', 'labels', 'values', 'ids', 'parents', 'r', 'theta', 'locations', 'lat', 'lon', 'low', 'high', 'open', 'close']

export function figureRows(fig) {
  const rows = []
  const add = (row) => rows.push(row)
  for (const [ti, tr] of (fig.data || []).entries()) {
    const name = tr.name ?? `trace ${ti + 1}`
    const type = tr.type || 'scatter'
    if (type === 'indicator') {
      add({ trace: tr.title?.text ?? name, type, value: tr.value, reference: tr.delta?.reference })
      continue
    }
    if (type === 'sankey') {
      const labels = decode(tr.node?.label) || []
      const s = decode(tr.link?.source) || [], t = decode(tr.link?.target) || [], v = decode(tr.link?.value) || []
      s.forEach((si, i) => add({ trace: name, type, source: labels[si] ?? si, target: labels[t[i]] ?? t[i], value: v[i] }))
      continue
    }
    const z = decode(tr.z)
    if (Array.isArray(z) && Array.isArray(z[0])) {
      const xs = decode(tr.x) || [], ys = decode(tr.y) || []
      z.forEach((row, yi) => row.forEach((val, xi) => add({ trace: name, type, x: xs[xi] ?? xi, y: ys[yi] ?? yi, z: val })))
      continue
    }
    const cols = {}
    let n = 0
    for (const k of FLAT) {
      const a = decode(tr[k])
      if (Array.isArray(a) && !Array.isArray(a[0])) {
        cols[k] = a
        n = Math.max(n, a.length)
      }
    }
    if (tr.marker && tr.marker.color && !Array.isArray(tr.marker.color)) {
      /* a single colour: nothing to export */
    } else if (tr.marker) {
      const c = decode(tr.marker.color), sz = decode(tr.marker.size)
      if (Array.isArray(c) && typeof c[0] === 'number') cols.colour_value = c
      if (Array.isArray(sz)) cols.size_value = sz
    }
    if (decode(tr.marker?.color) && Array.isArray(decode(tr.marker.color))) n = Math.max(n, decode(tr.marker.color).length)
    for (let i = 0; i < n; i++) {
      const row = { trace: name, type }
      for (const k of Object.keys(cols)) row[k] = cols[k][i]
      add(row)
    }
  }
  return rows
}

export function rowsToCsv(rows) {
  if (!rows.length) return ''
  const cols = []
  rows.forEach((r) => Object.keys(r).forEach((k) => cols.includes(k) || cols.push(k)))
  const esc = (v) => (v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v)) ? '' : `"${String(v).replace(/"/g, '""')}"`)
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
}

export function downloadCsv(text, name) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  a.download = `${name.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 60) || 'chart'}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}
