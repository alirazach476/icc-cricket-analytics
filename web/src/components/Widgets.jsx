import { stageInfo } from '../stage.js'
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import Flag, { isTeam } from './Flag.jsx'
import { useDash } from '../ctx.js'

const same = (a, b) => a === b || String(a) === String(b)

function useDebounced(value, commit, ms = 350) {
  const [local, setLocal] = useState(value)
  const first = useRef(true)
  useEffect(() => setLocal(value), [value])
  useEffect(() => {
    if (first.current) { first.current = false; return }
    if (same(local, value)) return
    const t = setTimeout(() => commit(local), ms)
    return () => clearTimeout(t)
  }, [local])
  return [local, setLocal]
}

function MatchPicker({ w, onChange }) {
  const { openMatch } = useDash()
  const [q, setQ] = useState('')
  const items = useMemo(() => w.options.map((o, i) => ({ o, r: w.rich[i] || {} })), [w])
  const view = useMemo(() => {
    const s = q.trim().toLowerCase()
    return s ? items.filter(({ o, r }) => `${o.l} ${r.venue || ''} ${r.result || ''}`.toLowerCase().includes(s)) : items
  }, [items, q])
  const ref = useRef(null)
  useEffect(() => {
    ref.current?.querySelector('.mp-item.on')?.scrollIntoView({ block: 'nearest' })
  }, [w.value])
  return (
    <div className="matchpicker">
      <label className="search mp-search">
        <Search size={14} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${items.length} matches by team, stage, venue or result`} />
      </label>
      <div className="mp-list" ref={ref} role="listbox" aria-label="Choose a match">
        {view.map(({ o, r }, i) => (
          <button key={i} role="option" aria-selected={same(o.v, w.value)} className={`mp-item ${same(o.v, w.value) ? 'on' : ''}`} onClick={() => (r.id && openMatch ? openMatch(r.id) : onChange(o.v))}>
            {stageInfo(r.stage).ko ? <span className="mp-no ko"><small>{stageInfo(r.stage).long.toUpperCase().slice(0, 4)}</small>{stageInfo(r.stage).short}</span> : r.no ? <span className="mp-no"><small>M</small>{r.no}</span> : null}
            <span className="mp-teams">
              <Flag team={r.t1} h={18} /> <b className={r.result && r.result.startsWith(r.t1) ? 'w' : ''}>{r.t1}</b> <i>v</i> <Flag team={r.t2} h={18} /> <b className={r.result && r.result.startsWith(r.t2) ? 'w' : ''}>{r.t2}</b>
            </span>
            <span className="mp-meta">
              {r.date}
              {r.stage ? ` · ${stageInfo(r.stage).long}` : ''}
              {r.no ? ` · Match ${r.no}` : ''}
            </span>
            <span className="mp-result">{r.result}</span>
            {!r.bbb && <span className="mp-tag" title="No ball-by-ball for this match">scorecard</span>}
          </button>
        ))}
        {!view.length && <div className="mp-empty">No match matches “{q}”.</div>}
      </div>
    </div>
  )
}

function Select({ w, onChange }) {
  if (w.rich && w.rich.some(Boolean)) return <MatchPicker w={w} onChange={onChange} />
  const big = w.options.length > 400
  const sel = (
    <select value={String(w.value)} onChange={(e) => onChange(w.options.find((o) => String(o.v) === e.target.value)?.v)}>
      {(big ? w.options.slice(0, 400) : w.options).map((o, i) => (
        <option key={i} value={String(o.v)}>{o.l}</option>
      ))}
    </select>
  )
  // a team is selected: show its flag next to the dropdown
  return isTeam(w.value) ? <div className="flagselect"><Flag team={w.value} h={22} />{sel}</div> : sel
}

function Radio({ w, onChange }) {
  return (
    <div className="seg">
      {w.options.map((o, i) => (
        <button key={i} className={same(o.v, w.value) ? 'on' : ''} onClick={() => onChange(o.v)}>{isTeam(o.l) && <Flag team={o.l} h={13} className="inline" />}{o.l}</button>
      ))}
    </div>
  )
}

function OptSlider({ w, onChange }) {
  const idx = Math.max(0, w.options.findIndex((o) => same(o.v, w.value)))
  const [i, setI] = useDebounced(idx, (n) => onChange(w.options[n].v))
  if (w.options.length < 2) return <Select w={w} onChange={onChange} />
  return (
    <div className="optslider">
      <div className="optval">{w.options[i]?.l}</div>
      <input type="range" min={0} max={w.options.length - 1} step={1} value={i} onChange={(e) => setI(Number(e.target.value))} />
      <div className="ticks">
        {w.options.map((o, k) => (
          <span key={k} className={k === i ? 'on' : ''} onClick={() => setI(k)}>{o.l}</span>
        ))}
      </div>
    </div>
  )
}

function Slider({ w, onChange }) {
  const [v, setV] = useDebounced(w.value, onChange)
  return (
    <div className="optslider">
      <div className="optval">{v}</div>
      <input type="range" min={w.min} max={w.max} step={w.step} value={v} onChange={(e) => setV(Number(e.target.value))} />
      <div className="ticks two"><span>{w.min}</span><span>{w.max}</span></div>
    </div>
  )
}

function Multi({ w, onChange }) {
  const chosen = new Set(w.value.map(String))
  const toggle = (v) => {
    const s = new Set(chosen)
    s.has(String(v)) ? s.delete(String(v)) : s.add(String(v))
    onChange(w.options.filter((o) => s.has(String(o.v))).map((o) => o.v))
  }
  return (
    <div className="chips">
      {w.options.map((o, i) => (
        <button key={i} className={chosen.has(String(o.v)) ? 'chip on' : 'chip'} onClick={() => toggle(o.v)}>{isTeam(o.l) && <Flag team={o.l} h={13} className="inline" />}{o.l}</button>
      ))}
    </div>
  )
}

function Check({ w, onChange }) {
  return (
    <label className="switch">
      <input type="checkbox" checked={!!w.value} onChange={(e) => onChange(e.target.checked)} />
      <span className="track"><span className="thumb" /></span>
      <span>{w.label}</span>
    </label>
  )
}

function Text({ w, onChange }) {
  const [v, setV] = useDebounced(w.value, onChange, 500)
  return <input className="text" value={v} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && onChange(v)} />
}

export default function Widget({ w, onChange }) {
  const set = (v) => onChange(w.id, v)
  const body = {
    select: <Select w={w} onChange={set} />,
    radio: <Radio w={w} onChange={set} />,
    slider_opts: <OptSlider w={w} onChange={set} />,
    slider: <Slider w={w} onChange={set} />,
    multi: <Multi w={w} onChange={set} />,
    check: <Check w={w} onChange={set} />,
    text: <Text w={w} onChange={set} />,
  }[w.kind]
  return (
    <div className={`widget ${w.kind}`}>
      {w.kind !== 'check' && <label className="wlabel">{w.label}</label>}
      {body}
    </div>
  )
}
