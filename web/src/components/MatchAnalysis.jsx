import React, { useState } from 'react'
import Plot from './Plot.jsx'

/** The match analysis charts, shown straight under the match header on every page that has one. */
export default function MatchAnalysis({ groups }) {
  const [g, setG] = useState(0)
  if (!groups || !groups.length) return null
  const cur = groups[Math.min(g, groups.length - 1)]
  return (
    <section className="mc-section">
      <h3 className="mc-h">Match analysis</h3>
      <div className="mc-seg" role="tablist">
        {groups.map((c, i) => (
          <button key={c.group} role="tab" aria-selected={i === g} className={i === g ? 'on' : ''} onClick={() => setG(i)}>
            {c.group}
          </button>
        ))}
      </div>
      <div className="mv-charts">
        {cur.figs.map((f) => (
          <Plot key={f.name} fig={f.fig} />
        ))}
      </div>
    </section>
  )
}
