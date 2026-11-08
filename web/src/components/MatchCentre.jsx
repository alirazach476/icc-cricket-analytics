import React, { useEffect, useMemo, useState } from 'react'
import { Calendar, MapPin, Trophy, Coins, Crown, Target, ChevronLeft, ChevronRight, Info, Star } from 'lucide-react'
import Flag from './Flag.jsx'
import { teamColor } from '../teamColors.js'
import { mix } from '../theme.js'
import Portrait from './Portrait.jsx'
import TvBoards from './TvBoard.jsx'

const dash = (v) => (v === null || v === undefined || v === '' ? '–' : v)
const fmtDate = (d) => {
  try {
    return new Date(`${d}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  } catch {
    return d
  }
}
const ord = (n) => `${n}${['th', 'st', 'nd', 'rd'][(n % 100 > 10 && n % 100 < 14) || n % 10 > 3 ? 0 : n % 10]}`

const MAX_OVERS = { ODI: 50, T20: 20 }
const legalBalls = (ov) => {
  if (!ov) return null
  const [o, b] = String(ov).split('.')
  return Number(o) * 6 + Number(b || 0)
}

// tiny over-by-over bars (runs per over; a red dot marks an over with a wicket)
function Spark({ overs, color }) {
  if (!overs || overs.length < 2) return null
  const max = Math.max(8, ...overs.map((o) => o.runs))
  const w = 6, gap = 2, h = 38
  const width = overs.length * (w + gap)
  return (
    <svg className="sb-spark" viewBox={`0 0 ${width} ${h + 6}`} preserveAspectRatio="none" role="img" aria-label="Runs in each over">
      {overs.map((o, i) => {
        const bh = Math.max(2, (o.runs / max) * h)
        return (
          <g key={i}>
            <rect x={i * (w + gap)} y={h - bh + 6} width={w} height={bh} rx="1.5" fill={color} opacity={o.wickets ? 1 : 0.7} />
            {o.wickets > 0 && <circle cx={i * (w + gap) + w / 2} cy="3" r="2.4" fill="#ff4d6d" />}
          </g>
        )
      })}
    </svg>
  )
}

function Band({ t, d, overs, right }) {
  const color = teamColor(t.name)
  const last = t.innings[t.innings.length - 1]
  const inn = d.innings.find((i) => last && i.n === last.n)
  const rr = inn && inn.run_rate
  return (
    <div className={`sb-band ${t.winner ? 'win' : ''}`} style={{ '--tc': color }}>
      <div className="sb-flag"><Flag team={t.name} h={46} className="mc-flag" /></div>
      <div className="sb-name">
        <b>{t.name}</b>
        <span>
          {t.winner && <em className="sb-won"><Crown size={12} /> WINNER</em>}
          {t.innings.length > 1 ? t.innings.slice(0, -1).map((i) => `${i.runs}${i.wickets < 10 ? `/${i.wickets}` : ''}`).join(' & ') + ' &' : inn && inn.target ? 'chasing' : inn ? 'batted first' : ''}
        </span>
      </div>
      <div className="sb-score">
        {last ? (
          <>
            <b>{last.runs}</b>
            {last.wickets !== null && last.wickets < 10 && <i>/{last.wickets}</i>}
          </>
        ) : (
          <span className="sb-dnb">{d.result_kind === 'won' && d.result.includes('WALKOVER') ? 'W/O' : '–'}</span>
        )}
      </div>
      <div className="sb-meta">
        {last && <b>{last.overs} <small>ov</small></b>}
        {rr ? <span>RR {rr.toFixed(2)}</span> : null}
      </div>
      {overs && <div className="sb-sparkwrap"><Spark overs={overs} color={color} /></div>}
    </div>
  )
}

function Hero({ d }) {
  const chase = d.innings.find((i) => i.target && !i.super_over)
  const oversOf = (name) => {
    const i = d.innings.find((x) => x.team.name === name && !x.super_over)
    const set = i && d.chips.find((c) => c.innings === i.n)
    return d.format === 'Test' ? null : set && set.overs
  }
  // "won with N balls to spare" for a successful limited-overs chase
  const cap = MAX_OVERS[d.format]
  let spare = null
  if (chase && cap && d.result_kind === 'won' && chase.team.name && d.teams.find((t) => t.winner && t.name === chase.team.name)) {
    const used = legalBalls(chase.overs)
    if (used !== null && cap * 6 - used > 0 && !d.result.includes('DLS')) spare = cap * 6 - used
  }
  const ed = d.edition
  const th = ed && ed.theme
  // the scoreboard carries its tournament's own colours and logo
  const brand = th
    ? { '--primary': th.primary, '--secondary': th.secondary, '--tertiary': th.tertiary, '--bg': th.bg, '--panel': mix(th.bg, '#ffffff', 0.06), '--panel2': mix(th.bg, '#ffffff', 0.11), '--border': mix(th.bg, '#ffffff', 0.17) }
    : undefined
  return (
    <section className={`mc-hero sb kind-${d.result_kind}`} style={brand}>
      {ed && <img className="sb-watermark" src={ed.logo} alt="" aria-hidden="true" />}
      <div className="sb-ticker">
        {ed && (
          <span className="sb-logo">
            <img src={ed.logo} alt={`${d.tournament} logo`} />
          </span>
        )}
        <span className="sb-tournament">{d.tournament}</span>
        {d.stage && <em>{d.stage}</em>}
        {d.match_number && <span>Match {d.match_number}</span>}
        {d.group && <span>{d.group}</span>}
        <span className="fmt">{d.format}</span>
        <span className={`mc-status s-${d.status.toLowerCase().replace(/\s/g, '-')}`}>{d.status}</span>
      </div>
      <div className="sb-venue">
        <span><Calendar size={13} /> {fmtDate(d.date)}</span>
        {(d.venue || d.city) && <span><MapPin size={13} /> {[d.venue, d.city].filter(Boolean).join(', ')}</span>}
      </div>
      <div className="sb-bands">
        <Band t={d.teams[0]} d={d} overs={oversOf(d.teams[0].name)} />
        <Band t={d.teams[1]} d={d} overs={oversOf(d.teams[1].name)} right />
      </div>
      <div className="sb-result"><span>{d.result}</span></div>
      <div className="mc-chips">
        {spare !== null && <span><Target size={14} /> won with <b>{spare}</b> ball{spare === 1 ? '' : 's'} to spare</span>}
        {d.toss && <span><Coins size={14} /> {d.toss}</span>}
        {chase && (
          <span>
            <Target size={14} /> Target <b>{chase.target}</b>
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
  const maxRuns = Math.max(1, best || 1)
  return (
    <div className="mc-card sc" style={{ '--sc': teamColor(inn.team.name) }}>
      <div className="sc-head">
        <Flag team={inn.team.name} h={20} />
        <b>Batting</b>
        <span className="sc-team">{inn.team.name}</span>
        <span className="sc-total">{inn.runs}{inn.wickets !== null && inn.wickets < 10 ? `/${inn.wickets}` : ''} <small>{inn.overs} ov</small></span>
      </div>
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
                  <td className="name"><span className="ord">{i + 1}</span><Portrait name={r.batter} team={inn.team.name} /> {r.batter}</td>
                  <td className="how">{r.how}</td>
                  <td className="num runs"><span className="bar" style={{ width: `${((r.runs || 0) / maxRuns) * 100}%` }} /><b>{dash(r.runs)}</b></td>
                  <td className="num">{dash(r.balls)}</td>
                  <td className={`num ${r.fours ? 'bd4' : ''}`}>{dash(r.fours)}</td>
                  <td className={`num ${r.sixes ? 'bd6' : ''}`}>{dash(r.sixes)}</td>
                  <td className="num">{r.sr !== null && r.sr !== undefined ? <span className={`srb ${r.sr >= (format === 'Test' ? 70 : format === 'T20' ? 150 : 100) ? 'hot' : r.sr < (format === 'Test' ? 35 : format === 'T20' ? 100 : 65) ? 'cool' : ''}`}>{r.sr.toFixed(1)}</span> : '–'}</td>
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
  const hasBd = rows.some((r) => r.fours !== null && r.fours !== undefined)
  const hasWn = rows.some((r) => (r.wd || 0) + (r.nb || 0) > 0)
  const bestW = rows.length ? Math.max(...rows.map((r) => r.w ?? 0)) : 0
  const econs = rows.map((r) => r.econ).filter((e) => e !== null && e !== undefined).sort((a, b) => a - b)
  const med = econs.length ? econs[Math.floor(econs.length / 2)] : null
  return (
    <div className="mc-card sc" style={{ '--sc': teamColor(inn.bowling_team) }}>
      <div className="sc-head">
        <Flag team={inn.bowling_team} h={20} />
        <b>Bowling</b>
        <span className="sc-team">{inn.bowling_team}</span>
        <span className="sc-total">{inn.wickets}{inn.wickets === 1 ? ' wicket' : ' wickets'} <small>{inn.overs} ov</small></span>
      </div>
      {rows.length === 0 ? (
        <div className="mc-empty">The bowling scorecard is not available for this innings.</div>
      ) : (
        <div className="mc-scroll">
          <table className="mc-table">
            <thead>
              <tr><th>Bowler</th><th>O</th><th>M</th><th>R</th><th>W</th><th>Econ</th>{hasDots && <th>0s</th>}{hasBd && <th>4s</th>}{hasBd && <th>6s</th>}{hasWn && <th>Wd</th>}{hasWn && <th>Nb</th>}</tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={r.w === bestW && bestW > 0 ? 'top' : ''}>
                  <td className="name"><Portrait name={r.bowler} team={inn.bowling_team} /> {r.bowler}</td>
                  <td className="num">{dash(r.overs)}</td>
                  <td className="num">{dash(r.m)}</td>
                  <td className="num">{dash(r.runs)}</td>
                  <td className="num">{r.w ? <span className="wk">{r.w}</span> : dash(r.w)}</td>
                  <td className="num">{r.econ !== null && r.econ !== undefined ? <span className={`ecb ${med && r.econ <= med * 0.85 ? 'good' : med && r.econ >= med * 1.25 ? 'poor' : ''}`}>{Number(r.econ).toFixed(2)}</span> : '–'}</td>
                  {hasDots && <td className="num">{dash(r.dots)}</td>}
                  {hasBd && <td className="num">{dash(r.fours)}</td>}
                  {hasBd && <td className="num">{dash(r.sixes)}</td>}
                  {hasWn && <td className="num">{dash(r.wd)}</td>}
                  {hasWn && <td className="num">{dash(r.nb)}</td>}
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
      <TvBoards d={view} />
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
