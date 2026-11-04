import React from 'react'
import { Globe2 } from 'lucide-react'

export function LogoTile({ e, size = 56 }) {
  return (
    <span className="logotile" style={{ width: size, height: size }}>
      <img src={e.logo} alt={`${e.name} logo`} loading="lazy" />
    </span>
  )
}

export function CompetitionTabs({ competitions, active, onSelect }) {
  return (
    <div className="comptabs" role="tablist" aria-label="Competition">
      {competitions.map((c) => (
        <button key={c.code} role="tab" aria-selected={c.code === active} className={c.code === active ? 'comptab on' : 'comptab'} onClick={() => onSelect(c.code)}>
          <b>{c.name}</b>
          <span>{c.note ? c.note : `${c.editions.filter((e) => !e.upcoming).length} ${c.editions.length === 1 ? 'edition' : 'editions'}`}</span>
        </button>
      ))}
    </div>
  )
}

export default function EditionRail({ comp, selected, onSelect }) {
  const editions = comp.editions
  const groups =
    comp.code === 'wc'
      ? [
          ['ODI World Cup', editions.filter((e) => e.format === 'ODI')],
          ['T20 World Cup', editions.filter((e) => e.format === 'T20')],
        ]
      : [[comp.long, editions]]
  return (
    <div className="rail" role="listbox" aria-label="Choose an edition">
      <button className={`railitem all ${!selected ? 'on' : ''}`} onClick={() => onSelect(null)}>
        <span className="logotile allicon"><Globe2 size={26} /></span>
        <span className="raillabel">All editions</span>
      </button>
      {groups.map(([title, list]) => (
        <div className="railgroup" key={title}>
          <div className="railtitle">{title}</div>
          <div className="railrow">
            {list.map((e) => (
              <button key={e.id} className={`railitem ${selected === e.id ? 'on' : ''}`} onClick={() => onSelect(e.id)} title={`${e.name} - ${e.host || ''}`}>
                {e.upcoming && <span className="soon">Soon</span>}
                <LogoTile e={e} />
                <span className="raillabel">{e.label || e.year}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
