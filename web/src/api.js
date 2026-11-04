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
