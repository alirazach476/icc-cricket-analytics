import React, { useMemo, useState } from 'react'
import { Download, Search, ArrowDown, ArrowUp, MousePointerClick } from 'lucide-react'
import { useDash } from '../ctx.js'
import Flag, { isTeam } from './Flag.jsx'

function fmt(v, numeric) {
  if (v === null || v === undefined) return '–'
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return Math.abs(v) >= 10000 && numeric ? v.toLocaleString('en-US') : String(v)
    return Math.abs(v) >= 1000 ? v.toLocaleString('en-US', { maximumFractionDigits: 1 }) : String(Math.round(v * 1000) / 1000)
  }
  if (typeof v === 'boolean') return v ? '✓' : '✗'
  return String(v)
}

export default function Table({ node }) {
  const { columns, numeric, rows: plain, total, links } = node
  const { openMatch } = useDash()
  const rows = useMemo(() => plain.map((r, i) => ({ r, link: links ? links[i] : null })), [plain, links])
  const clickable = !!links && links.some(Boolean)
  const [q, setQ] = useState('')
  const [sort, setSort] = useState(null)
  const [shown, setShown] = useState(60)

  const view = useMemo(() => {
    let r = rows
    if (q.trim()) {
      const s = q.toLowerCase()
      r = r.filter(({ r: row }) => row.some((c) => c !== null && String(c).toLowerCase().includes(s)))
    }
    if (sort) {
      const { i, dir } = sort
      r = [...r].sort((a, b) => {
        const x = a.r[i], y = b.r[i]
        if (x === y) return 0
        if (x === null) return 1
        if (y === null) return -1
        return (x > y ? 1 : -1) * dir
      })
    }
    return r
  }, [rows, q, sort])

  const csv = () => {
    const esc = (c) => (c === null ? '' : `"${String(c).replace(/"/g, '""')}"`)
    const text = [columns.map(esc).join(','), ...rows.map(({ r }) => r.map(esc).join(','))].join('\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
    a.download = 'table.csv'
    a.click()
  }

  return (
    <div className="tablecard">
      <div className="tablebar">
        <span className="tablecount">
          {total.toLocaleString()} rows
          {clickable && <em className="clickhint"><MousePointerClick size={13} /> click a match to open its scorecard</em>}
        </span>
        {rows.length > 8 && (
          <label className="search">
            <Search size={14} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter rows" />
          </label>
        )}
        <button className="ghost" onClick={csv} title="Download CSV"><Download size={14} /> CSV</button>
      </div>
      <div className="tablescroll">
        <table>
          <thead>
            <tr>
              {columns.map((c, i) => (
                <th key={i} className={numeric[i] ? 'num' : ''} onClick={() => setSort(sort && sort.i === i ? { i, dir: -sort.dir } : { i, dir: 1 })}>
                  {c.replace(/_/g, ' ')}
                  {sort && sort.i === i && (sort.dir === 1 ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {view.slice(0, shown).map(({ r, link }, ri) => (
              <tr key={ri} className={link ? 'link' : ''} onClick={link ? () => openMatch(link) : undefined}>
                {r.map((c, ci) => (
                  <td key={ci} className={numeric[ci] ? 'num' : ''}>{isTeam(c) && <Flag team={c} h={14} className="inline" />}{fmt(c, numeric[ci])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {view.length > shown && (
        <button className="more" onClick={() => setShown(shown + 100)}>Show more ({view.length - shown} left)</button>
      )}
    </div>
  )
}
