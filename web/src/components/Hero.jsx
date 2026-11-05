import React from 'react'
import { Trophy, MapPin, Swords, Crown, Medal, Flame, Calendar } from 'lucide-react'
import { LogoTile } from './EditionRail.jsx'
import { WithFlag } from './Flag.jsx'

const fmtN = (v, d = 0) => (v === null || v === undefined ? '–' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }))

export function EditionBanner({ e, comp }) {
  const stats = [
    [Crown, 'Champion', e.winner || 'TBD'],
    [Medal, 'Runner-up', e.runner_up || '–'],
    [Trophy, comp && comp.code === 'wtc' ? 'Player of the final' : 'Player of the tournament', e.player_of_tournament || '–'],
    [Swords, 'Matches', fmtN(e.matches)],
    [Flame, 'Runs per match', fmtN(e.runs_per_match)],
    [Flame, 'Sixes', fmtN(e.sixes)],
  ]
  const shown = e.stats ? e.stats.map(([label, value]) => [Calendar, label, value]) : stats
  return (
    <section className="edition" style={e.banner ? { '--banner': `url(${e.banner})` } : undefined}>
      <div className="edbg" />
      <LogoTile e={e} size={132} />
      <div className="edtext">
        <div className="edkicker">{comp && comp.kicker ? comp.kicker : e.format === 'ODI' ? "ICC Men's Cricket World Cup" : "ICC Men's T20 World Cup"}</div>
        <h2>{e.name}</h2>
        <div className="edhost">
          <MapPin size={15} /> {e.host || 'Host n/a'} · {e.start.slice(0, 10)} → {e.end.slice(0, 10)}
        </div>
        <div className="edstats">
          {shown.map(([Icon, label, value]) => (
            <div className="edstat" key={label}>
              <Icon size={15} />
              <div>
                <span>{label}</span>
                <b><WithFlag text={value} /></b>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export function PageHero({ hero }) {
  if (!hero) return null
  return (
    <header className="hero">
      <h1>{hero.title}</h1>
      <p>{hero.subtitle}</p>
      <div className="chiprow">
        {hero.chips.map((c) => (
          <span className="herochip" key={c}>{c}</span>
        ))}
      </div>
    </header>
  )
}

export function Gallery({ comp, onSelect }) {
  const editions = comp.editions
  const groups =
    comp.code === 'wc'
      ? [
          ['ODI World Cups', editions.filter((e) => e.format === 'ODI')],
          ['T20 World Cups', editions.filter((e) => e.format === 'T20')],
        ]
      : [[comp.long, editions]]
  return (
    <section className="gallery">
      {groups.map(([title, list]) => (
        <div key={title}>
          <div className="section-title">{title}</div>
          <div className="section-sub">Pick a tournament to open its own page, filters and colour theme.</div>
          <div className="gallerygrid">
            {list.map((e) => (
              <button key={e.id} className="gcard" onClick={() => onSelect(e.id)} style={{ '--gp': e.theme.primary, '--gs': e.theme.secondary, '--gbg': e.theme.bg }}>
                <LogoTile e={e} size={96} />
                <div className="gyear">{e.label || e.year}</div>
                <div className="gname">{e.host || ''}</div>
                <div className="gwin"><Crown size={13} /> {e.upcoming ? 'Upcoming' : <WithFlag text={e.winner || 'TBD'} h={13} />}</div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}
