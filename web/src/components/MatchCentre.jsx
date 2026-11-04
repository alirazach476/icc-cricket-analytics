import React, { useEffect, useMemo, useState } from 'react'
import { Calendar, MapPin, Trophy, Coins, Crown, Target, ChevronLeft, ChevronRight, Info, Star } from 'lucide-react'
import Flag from './Flag.jsx'

const dash = (v) => (v === null || v === undefined || v === '' ? '–' : v)
const fmtDate = (d) => {
  try {
    return new Date(`${d}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  } catch {
    return d
  }
}
const ord = (n) => `${n}${['th', 'st', 'nd', 'rd'][(n % 100 > 10 && n % 100 < 14) || n % 10 > 3 ? 0 : n % 10]}`

function Score({ inn, big }) {
  return (
    <span className={big ? 'mc-score big' : 'mc-score'}>
      <b>{inn.runs}</b>
      <i>{inn.wickets !== null && inn.wickets !== undefined && inn.wickets < 10 ? `/${inn.wickets}` : ''}</i>
    </span>
  )
}

function TeamBlock({ t, d, right }) {
  const lo = d.format !== 'Test'
  return (
    <div className={`mc-team ${t.winner ? 'win' : ''} ${right ? 'right' : ''}`}>
      <Flag team={t.name} h={44} className="mc-flag" />
      <div className="mc-tname">
        {t.winner && <Crown size={16} className="crown" aria-label="winner" />}
        {t.name}
      </div>
      {t.innings.length === 0 ? (
        <div className="mc-noinn">{d.result_kind === 'won' && d.result.includes('WALKOVER') ? 'Walkover' : 'Did not bat'}</div>
      ) : (
        t.innings.map((i, k) => (
          <div key={k} className="mc-line">
            <Score inn={i} big={k === t.innings.length - 1} />
            {lo || true ? <span className="mc-overs">{i.overs ? `${i.overs} ov` : ''}{i.super_over ? ' · super over' : ''}</span> : null}
          </div>
        ))
      )}
    </div>
  )
}

function Hero({ d }) {
  const chase = d.innings.find((i) => i.target && !i.super_over)
  return (
    <section className={`mc-hero kind-${d.result_kind}`}>
      <div className="mc-kicker">
        <span>{d.tournament}</span>
        {d.stage && <em>{d.stage}</em>}
        <span className={`mc-status s-${d.status.toLowerCase().replace(/\s/g, '-')}`}>{d.status}</span>
      </div>
      <div className="mc-meta">
        {d.match_number && <span>Match {d.match_number}</span>}
        {d.group && <span>{d.group}</span>}
        <span><Calendar size={14} /> {fmtDate(d.date)}</span>
        {(d.venue || d.city) && (
          <span><MapPin size={14} /> {[d.venue, d.city].filter(Boolean).join(', ')}</span>
        )}
        <span className="fmt">{d.format}</span>
      </div>
      <div className="mc-board">
        <TeamBlock t={d.teams[0]} d={d} />
        <div className="mc-vs"><span>VS</span></div>
        <TeamBlock t={d.teams[1]} d={d} right />
      </div>
      <div className="mc-result">{d.result}</div>
      <div className="mc-chips">
        {d.toss && <span><Coins size={14} /> {d.toss}</span>}
        {chase && (
          <span>
            <Target size={14} /> Target {chase.target}
            {chase.required_rate_start ? ` · required rate ${chase.required_rate_start.toFixed(2)} at the start` : ''}
          </span>
        )}
        {d.player_of_match && <span><Star size={14} /> Player of the match: <b>{d.player_of_match}</b></span>}
      </div>
    </section>
  )
}

function Stats({ stats }) {
  if (!stats.length) return null
  return (
    <section className="mc-stats" aria-label="Match statistics">
      {stats.map(([label, value, sub]) => (
        <div className="mc-stat" key={label}>
          <span className="mc-slabel">{label}</span>
          <b className="mc-svalue">{dash(value)}</b>
          {sub ? <span className="mc-ssub">{sub}</span> : null}
        </div>
      ))}
    </section>
  )
}

function Batting({ inn, format }) {
  const rows = inn.batting
  const ex = inn.extras
  const exParts = [
    ['b', ex.byes],
    ['lb', ex.legbyes],
    ['w', ex.wides],
    ['nb', ex.noballs],
    ['pen', ex.penalties],
  ].filter(([, v]) => v)
  const best = rows.length ? Math.max(...rows.map((r) => r.runs ?? -1)) : null
  return (
    <div className="mc-card">
      <div className="mc-cardhead">Batting · {inn.team.name}</div>
      {rows.length === 0 ? (
        <div className="mc-empty">The batting scorecard is not available for this innings.</div>
      ) : (
        <div className="mc-scroll">
          <table className="mc-table">
            <thead>
              <tr><th>Batter</th><th className="how">Dismissal</th><th>R</th><th>B</th><th>4s</th><th>6s</th><th>SR</th></tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={`${r.out ? '' : 'notout'} ${r.runs === best && best > 0 ? 'top' : ''}`}>
                  <td className="name">{r.batter}</td>
                  <td className="how">{r.how}</td>
                  <td className="num strong">{dash(r.runs)}</td>
                  <td className="num">{dash(r.balls)}</td>
                  <td className="num">{dash(r.fours)}</td>
                  <td className="num">{dash(r.sixes)}</td>
                  <td className="num">{r.sr !== null && r.sr !== undefined ? r.sr.toFixed(1) : '–'}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className="name">Extras</td>
                <td className="how">{exParts.length ? exParts.map(([k, v]) => `${k} ${v}`).join(', ') : ''}</td>
                <td className="num strong">{dash(ex.total)}</td>
                <td colSpan={4} />
              </tr>
              <tr className="total">
                <td className="name">Total</td>
                <td className="how">
                  {inn.wickets} wkts · {inn.overs} overs{inn.run_rate ? ` · RR ${inn.run_rate.toFixed(2)}` : ''}
                </td>
                <td className="num strong">{inn.runs}</td>
                <td colSpan={4} />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
      {inn.fow.length > 0 && (
        <div className="mc-fow">
          <b>Fall of wickets</b>
          <p>
            {inn.fow.map((w) => (
              <span key={w.wkt}>
                <em>{w.score}-{w.wkt}</em> {w.batter} ({w.over} ov)
              </span>
            ))}
          </p>
        </div>
      )}
    </div>
  )
}

function Bowling({ inn }) {
  const rows = inn.bowling
  const hasDots = rows.some((r) => r.dots !== null && r.dots !== undefined)
  const bestW = rows.length ? Math.max(...rows.map((r) => r.w ?? 0)) : 0
  return (
    <div className="mc-card">
      <div className="mc-cardhead">Bowling · {inn.bowling_team}</div>
      {rows.length === 0 ? (
        <div className="mc-empty">The bowling scorecard is not available for this innings.</div>
      ) : (
        <div className="mc-scroll">
          <table className="mc-table">
            <thead>
              <tr><th>Bowler</th><th>O</th><th>M</th><th>R</th><th>W</th><th>Econ</th>{hasDots && <th>0s</th>}</tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={r.w === bestW && bestW > 0 ? 'top' : ''}>
                  <td className="name">{r.bowler}</td>
                  <td className="num">{dash(r.overs)}</td>
                  <td className="num">{dash(r.m)}</td>
                  <td className="num">{dash(r.runs)}</td>
                  <td className="num strong">{dash(r.w)}</td>
                  <td className="num">{r.econ !== null && r.econ !== undefined ? Number(r.econ).toFixed(2) : '–'}</td>
                  {hasDots && <td className="num">{dash(r.dots)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Partnerships({ inn }) {
  const ps = inn.partnerships
  if (!ps.length) return null
  const max = Math.max(...ps.map((p) => p.runs), 1)
  return (
    <div className="mc-card">
      <div className="mc-cardhead">Partnerships · {inn.team.name}</div>
      <div className="mc-parts">
        {ps.map((p) => (
          <div key={p.wkt} className="mc-part">
            <span className="pw">{ord(p.wkt)} wkt{p.unbroken ? '*' : ''}</span>
            <span className="pn">
              {p.batters.map((b, k) => (
                <span key={k}>{b.name} <em>{b.runs} ({b.balls})</em></span>
              ))}
            </span>
            <span className="pbar"><i style={{ width: `${(p.runs / max) * 100}%` }} /></span>
            <b className="pr">{p.runs}<small> ({p.balls}b)</small></b>
          </div>
        ))}
      </div>
    </div>
  )
}

function Scorecard({ d }) {
  const list = d.innings
  const [k, setK] = useState(0)
  useEffect(() => setK(0), [d.match_id])
  if (!list.length) return null
  const inn = list[Math.min(k, list.length - 1)]
  const label = (i, idx) => {
    const n = list.filter((x, j) => j <= idx && x.team.name === i.team.name).length
    return `${i.team.name}${d.format === 'Test' ? ` ${ord(n)} inns` : i.super_over ? ' super over' : ''}`
  }
  return (
    <section className="mc-section">
      <h3 className="mc-h">Scorecard</h3>
      <div className="mc-seg" role="tablist">
        {list.map((i, idx) => (
          <button key={idx} role="tab" aria-selected={idx === k} className={idx === k ? 'on' : ''} onClick={() => setK(idx)}>
            <Flag team={i.team.name} h={14} /> {label(i, idx)} <b>{i.runs}/{i.wickets}</b>
          </button>
        ))}
      </div>
      {inn.super_over ? (
        <div className="mc-card"><div className="mc-empty">Super over: {inn.team.name} scored {inn.runs}/{inn.wickets}. A player-level scorecard is not stored for super overs.</div></div>
      ) : (
        <>
          <Batting inn={inn} format={d.format} />
          <Bowling inn={inn} />
          <Partnerships inn={inn} />
        </>
      )}
    </section>
  )
}

function Chip({ b }) {
  return <span className={`ball ${b[1]}`} title={`${b[2]} run${b[2] === 1 ? '' : 's'}`}>{b[0]}</span>
}

function BallByBall({ d }) {
  const list = d.chips
  const [ik, setIk] = useState(0)
  const [ov, setOv] = useState(null)
  useEffect(() => {
    setIk(0)
    setOv(null)
  }, [d.match_id])
  if (!list.length) return null
  const idx = Math.min(ik, list.length - 1)
  const set = list[idx]
  const meta = d.innings.find((i) => i.n === set.innings)
  const overs = set.overs
  const sel = ov === null || ov >= overs.length ? overs.length - 1 : ov
  const cur = overs[sel]
  const recent = overs.flatMap((o) => o.balls).slice(-12)
  const lastPart = meta?.partnerships?.[meta.partnerships.length - 1]
  const rr = meta?.run_rate
  const req = meta?.target && meta.required_rate_start
  return (
    <section className="mc-section">
      <h3 className="mc-h">Ball by ball <span className="mc-tag">{d.status}</span></h3>
      <div className="mc-seg">
        {list.map((s, i) => {
          const mi = d.innings.find((x) => x.n === s.innings)
          return (
            <button key={i} className={i === idx ? 'on' : ''} onClick={() => { setIk(i); setOv(null) }}>
              <Flag team={mi?.team.name} h={14} /> {mi?.team.name}{d.format === 'Test' ? ` (inns ${s.innings})` : ''}
            </button>
          )
        })}
      </div>
      <div className="mc-card bb">
        <div className="bb-top">
          <div>
            <span className="bb-label">{sel === overs.length - 1 ? 'Final over' : 'Selected over'}</span>
            <b className="bb-over">Over {cur.over}</b>
            <span className="bb-sub">{cur.bowler} · {cur.runs} runs{cur.wickets ? ` · ${cur.wickets} wkt` : ''} · {cur.score}</span>
          </div>
          <div className="bb-nav">
            <button onClick={() => setOv(Math.max(0, sel - 1))} disabled={sel === 0} aria-label="Previous over"><ChevronLeft size={18} /></button>
            <button onClick={() => setOv(Math.min(overs.length - 1, sel + 1))} disabled={sel === overs.length - 1} aria-label="Next over"><ChevronRight size={18} /></button>
          </div>
        </div>
        <div className="bb-balls">
          {cur.balls.map((b, i) => <Chip key={i} b={b} />)}
          {!cur.complete && <span className="bb-incomplete">over not completed</span>}
        </div>
        <div className="bb-recent">
          <span className="bb-label">Last {recent.length} deliveries of the innings</span>
          <div className="bb-balls small">{recent.map((b, i) => <Chip key={i} b={b} />)}</div>
        </div>
        <div className="bb-facts">
          {rr ? <div><span>Run rate</span><b>{rr.toFixed(2)}</b></div> : null}
          {req ? <div><span>Required at start</span><b>{req.toFixed(2)}</b></div> : null}
          {lastPart ? (
            <div>
              <span>{lastPart.unbroken ? 'Final unbroken partnership' : 'Last partnership'}</span>
              <b>{lastPart.runs} <small>({lastPart.balls} balls)</small></b>
            </div>
          ) : null}
        </div>
        <div className="bb-strip" role="listbox" aria-label="Jump to an over">
          {overs.map((o, i) => (
            <button
              key={i}
              className={`ov ${i === sel ? 'on' : ''} ${o.wickets ? 'w' : o.runs >= 12 ? 'hot' : o.runs <= 3 ? 'cool' : ''}`}
              onClick={() => setOv(i)}
              title={`Over ${o.over}: ${o.runs} runs${o.wickets ? `, ${o.wickets} wkt` : ''} (${o.bowler})`}
            >
              <small>{o.over}</small>
              <b>{o.runs}</b>
            </button>
          ))}
        </div>
        <div className="bb-legend">
          <span className="ball dot">0</span> dot <span className="ball run">1</span> runs <span className="ball four">4</span> four{' '}
          <span className="ball six">6</span> six <span className="ball extra">wd</span> extra <span className="ball wkt">W</span> wicket
        </div>
      </div>
    </section>
  )
}

function Info_({ d }) {
  const rows = [
    ['Tournament', d.tournament],
    ['Format', d.format],
    ['Stage', d.stage],
    ['Match number', d.match_number],
    ['Date', d.date && fmtDate(d.date)],
    ['Venue', [d.venue, d.city].filter(Boolean).join(', ')],
    ['Toss', d.toss],
    ['Player of the match', d.player_of_match],
    ['Ball-by-ball', d.has_ball_by_ball ? 'available' : 'not available'],
  ].filter(([, v]) => v)
  return (
    <section className="mc-section">
      <h3 className="mc-h">Match information</h3>
      <div className="mc-card mc-info">
        {rows.map(([k, v]) => (
          <div key={k}><span>{k}</span><b>{v}</b></div>
        ))}
        {!d.has_ball_by_ball && d.gap_reason && (
          <p className="mc-note"><Info size={14} /> {d.gap_reason}</p>
        )}
      </div>
    </section>
  )
}

export default function MatchCentre({ d }) {
  const view = useMemo(() => d, [d])
  if (!view) return <div className="alert warning">This match could not be loaded.</div>
  return (
    <div className="matchcentre">
      <Hero d={view} />
      {view.innings.length === 0 && (
        <div className="mc-card"><div className="mc-empty"><Trophy size={16} /> No innings were played in this match, so there is no scorecard.</div></div>
      )}
      <Stats stats={view.stats} />
      <Scorecard d={view} />
      <BallByBall d={view} />
      <Info_ d={view} />
    </div>
  )
}
