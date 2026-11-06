export async function getMeta() {
  const r = await fetch('/api/meta')
  if (!r.ok) throw new Error(`meta ${r.status}`)
  return r.json()
}

export async function getPage(slug, state, edition, competition, signal) {
  const r = await fetch(`/api/page/${slug}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state, edition, competition }),
    signal,
  })
  if (!r.ok) throw new Error(`page ${slug}: ${r.status}`)
  return r.json()
}

export async function getMatch(id, competition, signal) {
  const r = await fetch(`/api/match/${encodeURIComponent(id)}?competition=${competition || 'wc'}`, { signal })
  if (!r.ok) throw new Error(r.status === 404 ? 'This match could not be found.' : `match ${id}: ${r.status}`)
  return r.json()
}
