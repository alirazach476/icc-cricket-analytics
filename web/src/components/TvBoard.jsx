import React from 'react'
import { stageInfo } from '../stage.js'
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

const Bat = () => (
  <svg className="tv-ico" viewBox="0 0 24 24" width="20" height="20" aria-label="batting" role="img">
    <title>Batting</title>
    <path fill="currentColor" d="M3.2 20.8l-.9-.9 2-4.5 3.4 3.4-4.5 2zM6 14.3l8.5-8.5a3 3 0 0 1 4.2 0l.5.5a3 3 0 0 1 0 4.2L10.7 19 6 14.3z" />
  </svg>
)
const Ball = () => (
  <svg className="tv-ico" viewBox="0 0 24 24" width="20" height="20" aria-label="bowling" role="img">
    <title>Bowling</title>
    <circle cx="12" cy="12" r="9" fill="currentColor" />
    <path d="M6 5.5c3 3 3 10 0 13M18 5.5c-3 3-3 10 0 13" fill="none" stroke="#fff" strokeWidth="1.3" strokeDasharray="2 1.6" />
  </svg>
)

// full names: a dismissal such as "c Khan b Riaz" only carries surnames, so look the person up among the fielding team's players
const lastTok = (n) => (n || '').trim().split(' ').slice(-1)[0].toLowerCase()
function fullFrom(text, pool) {
  const t = (text || '').trim().replace(/\)$/, '')
  if (!t) return ''
  const exact = pool.filter((n) => n.toLowerCase() === t.toLowerCase())
  if (exact.length === 1) return exact[0]
  const k = lastTok(t)
  const hits = pool.filter((n) => lastTok(n) === k)
  if (hits.length === 1) return hits[0]
  const sub = hits.filter((n) => n.toLowerCase().includes(t.toLowerCase()))
  return sub.length === 1 ? sub[0] : t
}
const fshort = (t) => t.replace(/^(c & |c |st |run out ?\(?)(.*)$/, (_, p, n) => p + (n.trim().split(' ').slice(-1)[0] || '').toUpperCase().replace(/\)$/, ''))
const short = (name) => (name || '').split(' ').slice(-1)[0].toUpperCase()

const ORD = { 1: '1ST', 2: '2ND', 3: '3RD', 4: '4TH' }

function Board({ d, inn, kind, other }) {
  const bat = inn.team.name
  const bowl = inn.bowling_team
  const tag = hashtag(d)
  const ex = inn.extras || {}
  const batters = [...inn.batting].filter((r) => r.runs !== null && r.runs !== undefined)
    .sort((a, b) => b.runs - a.runs).slice(0, 4)
  const bowlers = [...inn.bowling].sort((a, b) => (b.w || 0) - (a.w || 0) || (a.runs || 0) - (b.runs || 0)).slice(0, 4)
  const ed = d.edition
  const pool = [...new Set([...(inn.bowling || []).map((r) => r.bowler), ...((other && other.batting) || []).map((r) => r.batter)])].filter(Boolean)
  const full = (t) => fullFrom(t, pool)
  const dism = (t) => (t || '').replace(/^(c & |c |st |run out ?\(?)(.*)$/, (_, p, n) => p + full(n))
  const topRuns = Math.max(0, ...inn.batting.map((r) => r.runs ?? 0))
  const total = `${inn.runs}${inn.wickets !== null && inn.wickets < 10 ? `-${inn.wickets}` : ''}`
  return (
    <div className="tv">
      <div className="tv-flags">
        <Flag team={bat} h={22} />
        <span className="tv-stage">{stageInfo(d.stage).ko ? `${stageInfo(d.stage).short} · ${stageInfo(d.stage).long.toUpperCase()}` : d.match_number ? `MATCH ${d.match_number}${d.match_total ? ` OF ${d.match_total}` : ''}` : (d.stage || d.format).toUpperCase()}</span>
        <Flag team={bowl} h={22} />
      </div>
      <div className="tv-body">
        <div className="tv-title">
          <span className={`tv-side ${kind === 'bat' ? 'on' : ''}`}>{kind === 'bat' && <Bat />}{bat.toUpperCase()}</span>
          {ed && <img className="tv-logo" src={ed.logo} alt="" />}
          <span className={`tv-side ${kind === 'bowl' ? 'on' : ''}`}>{kind === 'bowl' && <Ball />}{bowl.toUpperCase()}</span>
        </div>
        <div className="tv-venue">{(d.city || d.venue || '').toUpperCase()}<b>{ORD[inn.n] ? ` · ${ORD[inn.n]} INNINGS` : ''}</b></div>
        {kind === 'bat' ? (
          <div className="tv-card">
            {inn.batting.map((r, i) => {
              const out = r.how && !/not out|retired hurt|^$/i.test(r.how)
              const m = out ? r.how.match(/^(.*?)\s+b\s+(.+)$/) : null
              const field = m ? m[1].replace(/^c & /, 'c & ') : out ? r.how : ''
              const hot = !out || (i === 0 && false)
              return (
                <div className={`tv-bat ${r.runs === topRuns && topRuns > 0 ? 'top' : ''} ${!out ? 'live' : ''}`} key={i}>
                  <span className="n">{r.batter}</span>
                  <span className="f">{m ? dism(m[1]) : (out && !/^b /.test(r.how) ? dism(r.how) : '')}</span>
                  <span className="bw">{m ? `b ${full(m[2])}` : /^b /.test(r.how || '') ? `b ${full(r.how.slice(2))}` : (!out ? (r.how || '') : '')}</span>
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
                  <td>{r.bowler}</td><td>{r.overs}</td><td>{r.m ?? '–'}</td><td>{r.runs}</td><td>{r.w}</td>
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
  const [sel, setSel] = React.useState(0)
  React.useEffect(() => setSel(0), [d.match_id])
  if (!inns.length) return null
  const shown = [inns[Math.min(sel, inns.length - 1)]]
  // the other side's batting card supplies fielders' full names
  const oppo = (i) => inns.find((x) => x.team.name === i.bowling_team && x.n !== i.n) || inns.find((x) => x.n !== i.n)
  return (
    <section className="tvwrap" aria-label="Broadcast scoreboards">
      {inns.length > 1 && (
        <div className="mc-seg tv-seg" role="tablist" aria-label="Innings">
          {inns.map((i, ix) => (
            <button key={i.n} role="tab" aria-selected={ix === sel} className={ix === sel ? 'on' : ''} onClick={() => setSel(ix)}>
              {ORD[i.n] || `${i.n}TH`} innings <b>{i.team.name} {i.runs}{i.wickets !== null && i.wickets < 10 ? `/${i.wickets}` : ''}</b>
            </button>
          ))}
        </div>
      )}
      {shown.map((i) => (
        <div className="tvpair" key={i.n}>
          <Board d={d} inn={i} kind="bat" other={oppo(i)} />
          {i.bowling && i.bowling.length > 0 && <Board d={d} inn={i} kind="bowl" other={oppo(i)} />}
        </div>
      ))}
    </section>
  )
}
