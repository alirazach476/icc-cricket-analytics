import React from 'react'
import { teamColor } from '../teamColors.js'

const initials = (n) => {
  const p = String(n || '?').replace(/[^A-Za-zÀ-ɏ' -]/g, '').split(/\s+/).filter(Boolean)
  return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase()
}

/** Player portrait. A genuine photograph is shown only when `src` is supplied (licensed assets);
 *  otherwise a consistent team-coloured monogram, never a made-up likeness. */
export default function Portrait({ name, team, src, size = 30 }) {
  const c = teamColor(team, '#4c8dff')
  if (src) return <img className="pt pt-img" src={src} alt={name} width={size} height={size} loading="lazy" />
  return (
    <span className="pt" style={{ '--tc': c, width: size, height: size }} title={name} aria-hidden="true">
      {initials(name)}
    </span>
  )
}
