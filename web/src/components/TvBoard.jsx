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
  const total = `${inn.runs}${inn.wickets !== null && inn.wickets < 10 ? `-${inn.wickets}` : ''}`
  return (
    <div className="tv">
      <div className="tv-flags">
        <Flag team={bat} h={22} />
        <span className="tv-stage">{(d.stage || d.format).toUpperCase()}{d.match_number ? ` · MATCH ${d.match_number}` : ''}</span>
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
          <div className="tv-rows">
            <div className="tv-sec bat">{total}</div>
            {batters.map((r) => (
              <div className="tv-row" key={r.batter}>
                <span>{short(r.batter)}</span>
                <b>{r.runs}{r.how && /not out/i.test(r.how) ? '*' : ''}</b>
                <i>{r.balls ?? '–'}</i>
              </div>
            ))}
            <div className="tv-sec ball">{inn.overs} OVERS</div>
            {bowlers.slice(0, 3).map((r) => (
              <div className="tv-row" key={r.bowler}>
                <span>{short(r.bowler)}</span>
                <b>{r.w}-{r.runs}</b>
                <i>{r.overs}</i>
              </div>
            ))}
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
