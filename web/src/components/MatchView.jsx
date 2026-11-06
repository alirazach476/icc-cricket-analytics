import React, { useEffect, useState } from 'react'
import { ArrowLeft, ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react'
import { getMatch } from '../api.js'
import MatchCentre from './MatchCentre.jsx'
import Plot from './Plot.jsx'

/** A match opens straight into its scoreboard: the whole page is the broadcast graphic, the scorecard and the charts. */
export default function MatchView({ id, comp, onEdition, onBack, go }) {
  const [st, setSt] = useState({ loading: true })
  const [g, setG] = useState(0)
  useEffect(() => {
    const ctl = new AbortController()
    setSt({ loading: true })
    setG(0)
    window.scrollTo({ top: 0 })
    getMatch(id, comp, ctl.signal)
      .then((d) => {
        setSt({ data: d })
        onEdition(d.payload.edition ? d.payload.edition.id : null)
      })
      .catch((e) => e.name !== 'AbortError' && setSt({ error: String(e.message || e) }))
    return () => ctl.abort()
  }, [id, comp])

  const d = st.data
  const nb = d && d.neighbours
  const ed = d && d.payload.edition
  const jump = (m) => m && go(`match/${m.id}`, null, comp)
  return (
    <div className="matchview">
      <div className="mv-bar">
        <button className="mv-back" onClick={onBack}>
          <ArrowLeft size={16} /> Back
        </button>
        {ed && (
          <div className="mv-crumb">
            <img src={ed.logo} alt="" />
            <span>{ed.name}</span>
          </div>
        )}
        <div className="mv-nav">
          <button disabled={!nb || !nb.prev} onClick={() => jump(nb.prev)} title={nb && nb.prev ? `${nb.prev.label} (${nb.prev.date})` : ''}>
            <ChevronLeft size={16} /> <span>Previous match</span>
          </button>
          <button disabled={!nb || !nb.next} onClick={() => jump(nb.next)} title={nb && nb.next ? `${nb.next.label} (${nb.next.date})` : ''}>
            <span>Next match</span> <ChevronRight size={16} />
          </button>
        </div>
      </div>
      {st.loading && (
        <div className="mv-loading">
          <div className="skeleton hero" />
          <div className="skeleton" style={{ height: 120 }} />
          <div className="skeleton" style={{ height: 320 }} />
        </div>
      )}
      {st.error && (
        <div className="alert error">
          <AlertTriangle size={18} /> {st.error}
        </div>
      )}
      {d && (
        <>
          <MatchCentre d={d.payload} />
          {d.charts.length > 0 && (
            <section className="mc-section">
              <h3 className="mc-h">Match analysis</h3>
              <div className="mc-seg" role="tablist">
                {d.charts.map((c, i) => (
                  <button key={c.group} role="tab" aria-selected={i === g} className={i === g ? 'on' : ''} onClick={() => setG(i)}>
                    {c.group}
                  </button>
                ))}
              </div>
              <div className="mv-charts">
                {d.charts[Math.min(g, d.charts.length - 1)].figs.map((f) => (
                  <Plot key={f.name} fig={f.fig} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
