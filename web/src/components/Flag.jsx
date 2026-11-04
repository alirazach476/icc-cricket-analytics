import React from 'react'

// team name (any known spelling, lower case) -> local flag file code; filled from /api/meta
let FLAGS = {}
export const setFlags = (m) => {
  FLAGS = m || {}
}
export const flagCode = (team) => (team ? FLAGS[String(team).trim().toLowerCase()] || null : null)
export const isTeam = (v) => typeof v === 'string' && !!FLAGS[v.trim().toLowerCase()]

const initials = (n) => {
  const p = String(n || '?').replace(/-/g, ' ').split(/\s+/).filter((w) => /^[A-Za-z]/.test(w))
  return (p.length === 1 ? p[0].slice(0, 3) : p.map((w) => w[0]).join('').slice(0, 3)).toUpperCase()
}

/** Accurate national flag (local SVG, 4:3). Teams without a flag (West Indies, TBD slots) get a neutral badge. */
export default function Flag({ team, h = 18, className = '' }) {
  const code = flagCode(team)
  const w = Math.round((h * 4) / 3)
  if (!code)
    return (
      <span className={`flag flag-fallback ${className}`} style={{ width: w + 4, height: h, fontSize: Math.max(8, h * 0.45) }} title={team || ''} aria-label={team || 'team'}>
        {initials(team)}
      </span>
    )
  return <img className={`flag ${className}`} src={`/flags/${code}.svg`} width={w} height={h} alt={`${team} flag`} title={team} loading="lazy" />
}
