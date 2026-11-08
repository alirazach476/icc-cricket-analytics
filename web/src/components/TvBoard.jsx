import React from 'react'
import Flag from './Flag.jsx'

// "#CWC23"-style hashtag from the tournament name and year (never invented for unknown names)
export function hashtag(d) {
  const n = d.tournament || ''
  const yy = String(d.year || '').slice(-2)
  if (/champions trophy/i.test(n)) return `#CT${yy}`
  if (/test championship/i.test(n)) return '#WTC'
  if (/twenty20|t20/i.test(n)) return `#T20WC${yy}`
  if (/world cup/i.test(n)) return `#CWC${yy}`
  return ''
}

const fshort = (t) => t.replace(/^(c & |c |st |run out ?\(?)(.*)$/, (_, p, n) => p + (n.trim().split(' ').slice(-1)[0] || '').toUpperCase().replace(/\)$/, ''))
const short = (name) => (name || '').split(' ').slice(-1)[0].toUpperCase()

function Board({ d, inn, kind }) {
  const bat = inn.team.name
  const bowl = inn.bowling_team
  const tag = hashtag(d)
  const ex = inn.extras || {}
  const batters = [...inn.batting].filter((r) => r.runs !== null && r.runs !== undefined)
    .sort((a, b) => b.runs - a.runs).slice(0, 4)
  const bowlers = [...inn.bowling].sort((a, b) => (b.w || 0) - (a.w || 0) || (a.runs || 0) - (b.runs || 0)).slice(0, 4)
  const ed = d.edition
  const topRuns = Math.max(0, ...inn.batting.map((r) => r.runs ?? 0))
  const total = `${inn.runs}${inn.wickets !== null && inn.wickets < 10 ? `-${inn.wickets}` : ''}`
  return (
    <div className="tv">
      <div className="tv-flags">
        <Flag team={bat} h={22} />
        <span className="tv-stage">{d.match_number ? `MATCH ${d.match_number}${d.match_total ? ` OF ${d.match_total}` : ''}` : (d.stage || d.format).toUpperCase()}</span>
        <Flag team={bowl} h={22} />
      </div>
      <div className="tv-body">
        <div className="tv-title">
          <span className={`tv-side ${kind === 'bat' ? 'on' : ''}`}>{bat.toUpperCase()}</span>
          {ed && <img className="tv-logo" src={ed.logo} alt="" />}
          <span className={`tv-side ${kind === 'bowl' ? 'on' : ''}`}>{bowl.toUpperCase()}</span>
        </div>
        <div className="tv-venue">{(d.city || d.venue || '').toUpperCase()}</div>
        {kind === 'bat' ? (
          <div className="tv-card">
            {inn.batting.map((r, i) => {
              const out = r.how && !/not out|retired hurt|^$/i.test(r.how)
              const m = out ? r.how.match(/^(.*?)\s+b\s+(.+)$/) : null
              const field = m ? m[1].replace(/^c & /, 'c & ') : out ? r.how : ''
              const hot = !out || (i === 0 && false)
              return (
                <div className={`tv-bat ${r.runs === topRuns && topRuns > 0 ? 'top' : ''} ${!out ? 'live' : ''}`} key={i}>
                  <span className="n">{short(r.batter)}</span>
                  <span className="f">{m ? fshort(m[1]) : (out && !/^b /.test(r.how) ? r.how : '')}</span>
                  <span className="bw">{m ? `b ${short(m[2])}` : /^b /.test(r.how || '') ? `b ${short(r.how.slice(2))}` : (!out ? (r.how || '') : '')}</span>
                  <b>{r.runs ?? '–'}</b>
                  <i>{r.balls ?? ''}</i>
                </div>
              )
            })}
            {inn.batting.length < 11 && <div className="tv-dnb">{11 - inn.batting.length} yet to bat or did not bat</div>}
          </div>
        ) : (
          <table className="tv-bowl">
            <thead><tr><th /><th>OVERS</th><th>MAIDENS</th><th>RUNS</th><th>WICKETS</th><th>ECONOMY</th></tr></thead>
            <tbody>
              {inn.bowling.slice(0, 6).map((r) => (
                <tr key={r.bowler}>
                  <td>{short(r.bowler)}</td><td>{r.overs}</td><td>{r.m ?? '–'}</td><td>{r.runs}</td><td>{r.w}</td>
                  <td>{r.econ !== null && r.econ !== undefined ? Number(r.econ).toFixed(2) : '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {kind === 'bowl' && inn.fow && inn.fow.length > 0 && (
          <div className="tv-fow"><b>FALL OF WICKETS</b>{inn.fow.slice(0, 10).map((f, i) => <span key={i}>{f.score ?? f.runs ?? ''}</span>)}</div>
        )}
        <div className="tv-foot">
          <span className="tv-tag">{tag}</span>
          <span className="tv-ex">{ex.total ?? '–'} <small>EXTRAS</small></span>
          <span className="tv-ov">{inn.overs} <small>OVERS</small></span>
          <span className="tv-tot">{total}</span>
        </div>
      </div>
      <div className="tv-result">{d.result}</div>
    </div>
  )
}

export default function TvBoards({ d }) {
  const inns = d.innings.filter((i) => !i.super_over && i.batting && i.batting.length)
  if (!inns.length) return null
  return (
    <section className="tvwrap" aria-label="Broadcast scoreboards">
      {inns.slice(0, 2).map((i) => (
        <div className="tvpair" key={i.n}>
          <Board d={d} inn={i} kind="bat" />
          {i.bowling && i.bowling.length > 0 && <Board d={d} inn={i} kind="bowl" />}
        </div>
      ))}
    </section>
  )
}
