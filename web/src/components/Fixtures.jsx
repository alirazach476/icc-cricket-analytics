import React, { useMemo, useState } from 'react'
import { Crown, MapPin, Calendar, ChevronRight } from 'lucide-react'
import Flag from './Flag.jsx'
import { useDash } from '../ctx.js'
import { teamColor } from '../teamColors.js'

const GROUP = {
  'First Round': 'Group stage',
  'Group Stage': 'Group stage',
  'Super Six': 'Second stage',
  'Super Eight': 'Second stage',
  'Super Ten': 'Second stage',
  'Super 12': 'Second stage',
  Quarterfinal: 'Knockout',
  Semifinal: 'Knockout',
  Final: 'Knockout',
}
const GROUP_ORDER = ['Group stage', 'Second stage', 'Knockout', 'Other']
const FILTERS = [
  ['all', 'All matches'],
  ['Group stage', 'Group stage'],
  ['Second stage', 'Second stage'],
  ['Knockout', 'Knockout'],
  ['Semifinal', 'Semi-finals'],
  ['Final', 'Final'],
]
const fmtDate = (d) => {
  try {
    return new Date(`${d}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  } catch {
    return d
  }
}
const scoreText = (inns) =>
  inns.map((i) => `${i.runs}${i.wickets !== null && i.wickets < 10 ? `/${i.wickets}` : ''}`).join(' & ')

function Card({ f, onOpen }) {
  const played = f.teams.some((t) => t.innings.length)
  const dim = ['Abandoned', 'No result', 'Upcoming'].includes(f.status)
  return (
    <button className={`fx-card s-${f.status.toLowerCase().replace(/\s/g, '-')}`} onClick={() => onOpen(f.id)} aria-label={`${f.teams[0].name} v ${f.teams[1].name}, ${f.result}`}>
      <div className="fx-top">
        <span className="fx-stage">{f.stage || 'Match'}</span>
        {f.no && <span>Match {f.no}</span>}
        {f.group && f.group !== 'Overall' && <span>{f.group}</span>}
        <span className="fx-date"><Calendar size={12} /> {fmtDate(f.date)}</span>
        <span className={`fx-status ${dim ? 'dim' : ''}`}>{f.status}</span>
      </div>
      <div className="fx-teams">
        {f.teams.map((t) => {
          const win = f.winner && f.winner === t.name
          const last = t.innings[t.innings.length - 1]
          return (
            <div key={t.name} className={`fx-team ${win ? 'win' : ''}`} style={{ '--tc': teamColor(t.name) }}>
              <Flag team={t.name} h={26} className="fx-flag" />
              <b className="fx-name">{t.name}</b>
              {win && <Crown size={14} className="fx-crown" aria-label="winner" />}
              <span className="fx-score">{played && t.innings.length ? scoreText(t.innings) : <i>{f.status === 'Upcoming' ? 'v' : '–'}</i>}</span>
              <small className="fx-ov">{last && last.overs ? `${last.overs} ov` : ''}</small>
            </div>
          )
        })}
      </div>
      <div className="fx-result">
        <span>{f.result}</span>
        <ChevronRight size={16} />
      </div>
      <div className="fx-venue">
        <MapPin size={12} /> {[f.venue, f.city].filter(Boolean).join(', ') || 'Venue not recorded'}
        {f.bbb && <em title="Ball-by-ball available">ball by ball</em>}
      </div>
    </button>
  )
}

/** Tournament results centre: the fixtures as television-graphic cards, grouped by stage, with filters. */
export default function Fixtures({ data }) {
  const { openMatch } = useDash()
  const [f, setF] = useState('all')
  const [team, setTeam] = useState('All teams')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const all = data.fixtures
  const teams = useMemo(() => [...new Set(all.flatMap((x) => x.teams.map((t) => t.name)))].sort(), [all])
  const dates = useMemo(() => [...new Set(all.map((x) => x.date))].sort(), [all])
  const present = useMemo(() => {
    const g = new Set(all.map((x) => GROUP[x.stage] || 'Other'))
    return FILTERS.filter(([k]) => k === 'all' || g.has(k) || (k === 'Semifinal' && all.some((x) => x.stage === 'Semifinal')) || (k === 'Final' && all.some((x) => x.stage === 'Final')))
  }, [all])
  const shown = useMemo(
    () =>
      all.filter((x) => {
        if (f === 'Semifinal' || f === 'Final') {
          if (x.stage !== f) return false
        } else if (f !== 'all' && (GROUP[x.stage] || 'Other') !== f) return false
        if (team !== 'All teams' && !x.teams.some((t) => t.name === team)) return false
        if (from && x.date < from) return false
        if (to && x.date > to) return false
        return true
      }),
    [all, f, team, from, to],
  )
  const groups = useMemo(() => {
    const m = {}
    shown.forEach((x) => {
      const k = GROUP[x.stage] || 'Other'
      ;(m[k] = m[k] || []).push(x)
    })
    return GROUP_ORDER.filter((k) => m[k]).map((k) => [k, m[k]])
  }, [shown])

  return (
    <section className="fx">
      <div className="fx-hero">
        <div>
          <span className="fx-kicker">Results centre</span>
          <h3>{data.tournament}</h3>
          <p>
            {all.length} fixtures · {teams.length} teams · {fmtDate(dates[0])} to {fmtDate(dates[dates.length - 1])}
          </p>
        </div>
        <div className="fx-flags" aria-label="Participating teams">
          {teams.map((t) => (
            <Flag key={t} team={t} h={22} />
          ))}
        </div>
      </div>
      <div className="fx-filters">
        <div className="mc-seg" role="tablist">
          {present.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={f === k} className={f === k ? 'on' : ''} onClick={() => setF(k)}>
              {label}
            </button>
          ))}
        </div>
        <select value={team} onChange={(e) => setTeam(e.target.value)} aria-label="Team">
          <option>All teams</option>
          {teams.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <select value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From date">
          <option value="">From any date</option>
          {dates.map((d) => (
            <option key={d} value={d}>{fmtDate(d)}</option>
          ))}
        </select>
        <select value={to} onChange={(e) => setTo(e.target.value)} aria-label="To date">
          <option value="">To any date</option>
          {dates.map((d) => (
            <option key={d} value={d}>{fmtDate(d)}</option>
          ))}
        </select>
        <span className="fx-count">{shown.length} of {all.length}</span>
      </div>
      {groups.length === 0 && <div className="alert info">No fixtures match these filters.</div>}
      {groups.map(([name, list]) => (
        <div key={name} className="fx-group">
          <h4 className="fx-gh"><span>{name}</span><i>{list.length} matches</i></h4>
          <div className="fx-grid">
            {list.map((x) => (
              <Card key={x.id} f={x} onOpen={openMatch} />
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}
