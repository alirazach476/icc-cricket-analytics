import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Home, Trophy, User, Shield, Users, Swords, Target, FlaskConical, Brain, Database, ScrollText, Loader2, SlidersHorizontal } from 'lucide-react'
import { getMeta, getPage } from './api.js'
import MatchView from './components/MatchView.jsx'
import { setFlags } from './components/Flag.jsx'
import { applyTheme, makeRecolor } from './theme.js'
import { DashCtx } from './ctx.js'
import { Nodes } from './components/Renderer.jsx'
import Widget from './components/Widgets.jsx'
import EditionRail, { CompetitionTabs } from './components/EditionRail.jsx'
import { EditionBanner, PageHero, Gallery } from './components/Hero.jsx'

const ICONS = { home: Home, trophy: Trophy, user: User, shield: Shield, users: Users, swords: Swords, target: Target, flask: FlaskConical, brain: Brain, database: Database, scroll: ScrollText }

function readHash() {
  const h = window.location.hash.replace(/^#\/?/, '')
  const [path, qs] = h.split('?')
  const q = new URLSearchParams(qs || '')
  return { slug: path || 'home', edition: q.get('e') || null, comp: q.get('c') || 'wc' }
}

const hashFor = (slug, edition, comp) => {
  const q = []
  if (comp && comp !== 'wc') q.push(`c=${comp}`)
  if (edition) q.push(`e=${edition}`)
  return `/${slug}${q.length ? `?${q.join('&')}` : ''}`
}

export default function App() {
  const [meta, setMeta] = useState(null)
  const [fatal, setFatal] = useState(null)
  const [route, setRoute] = useState(readHash())
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [matchEdId, setMatchEdId] = useState(null)
  const states = useRef({})
  const reqId = useRef(0)
  const abort = useRef(null)

  useEffect(() => {
    getMeta().then((m) => { setFlags(m.flags); setMeta(m) }).catch((e) => setFatal(String(e)))
  }, [])
  useEffect(() => {
    const on = () => setRoute(readHash())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])

  // every page opens at its top (never mid-page); the browser back button still returns to the previous page
  useEffect(() => {
    try { window.history.scrollRestoration = 'manual' } catch { /* older browsers */ }
  }, [])
  useEffect(() => {
    window.scrollTo(0, 0)
    document.querySelectorAll('.main, main, .content').forEach((el) => { el.scrollTop = 0 })
  }, [route.slug, route.edition, route.comp])

  const go = useCallback((slug, edition, comp) => {
    window.location.hash = hashFor(slug, edition, comp)
  }, [])

  const allEditions = useMemo(() => (meta ? meta.competitions.flatMap((c) => c.editions) : []), [meta])
  const isMatch = route.slug.startsWith('match/')
  const matchId = isMatch ? route.slug.slice(6) : null
  const edId = route.edition || (isMatch ? matchEdId : null)
  const edition = useMemo(() => allEditions.find((e) => e.id === edId) || null, [allEditions, edId])
  const compCode = edition ? edition.tab || edition.competition : route.comp
  const comp = useMemo(() => meta?.competitions.find((c) => c.code === compCode) || meta?.competitions[0], [meta, compCode])
  // backend competition that serves the page (the 2027 World Cup lives under the World Cups tab)
  const dc = edition ? edition.competition : comp?.code
  const pages = edition?.pages || comp?.pages || []
  const theme = edition ? edition.theme : comp && comp.code !== 'wc' && comp.editions.length ? comp.editions[0].theme : meta?.default_theme

  useEffect(() => {
    if (theme) applyTheme(theme)
  }, [theme])
  // the whole page wears the selected tournament's artwork
  useEffect(() => {
    document.documentElement.style.setProperty('--page-bg', edition && edition.banner ? `url(${edition.banner})` : 'none')
  }, [edition])
  const recolor = useMemo(() => (meta ? makeRecolor(meta.base_slots, theme) : (x) => x), [meta, theme])
  const template = useMemo(() => (meta ? recolor(meta.template) : null), [meta, recolor])

  const load = useCallback(async (slug, edId, cc) => {
    if (abort.current) abort.current.abort()
    const ctl = new AbortController()
    abort.current = ctl
    const id = ++reqId.current
    setLoading(true)
    setErr(null)
    try {
      const st = states.current[`${cc}|${slug}|${edId || ''}`] || {}
      const d = await getPage(slug, st, edId, cc, ctl.signal)
      if (id === reqId.current) {
        setData(d)
        setLoading(false)
      }
    } catch (e) {
      if (e.name !== 'AbortError' && id === reqId.current) {
        setErr(String(e))
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    if (!meta || !comp || isMatch) return
    if (!pages.includes(route.slug)) {
      go('home', route.edition, comp.code)
      return
    }
    load(route.slug, route.edition, dc)
  }, [meta, comp, dc, pages, isMatch, route.slug, route.edition, load, go])

  const setWidget = useCallback(
    (wid, value) => {
      const k = `${dc}|${route.slug}|${route.edition || ''}`
      states.current[k] = { ...(states.current[k] || {}), [wid]: value }
      load(route.slug, route.edition, dc)
    },
    [route, dc, load],
  )

  const openMatch = useCallback(
    (matchId) => {
      // a match opens straight into its own scoreboard view
      go(`match/${matchId}`, null, dc)
    },
    [dc, go],
  )

  const back = useCallback(() => {
    if (window.history.length > 1) window.history.back()
    else go('matches', matchEdId, comp ? comp.code : 'wc')
  }, [go, matchEdId, comp])

  const selectEdition = useCallback(
    (id) => {
      const up = id && allEditions.find((e) => e.id === id)?.upcoming
      const slug = up ? 'home' : route.slug === 'home' && id ? 'tournaments' : route.slug
      go(slug, id, comp.code)
    },
    [route.slug, comp, allEditions, go],
  )

  const selectCompetition = useCallback(
    (code) => {
      const target = meta.competitions.find((c) => c.code === code)
      go(target.pages.includes(route.slug) ? route.slug : 'home', null, code)
    },
    [meta, route.slug, go],
  )

  if (fatal)
    return (
      <div className="fatal">
        <h2>Backend not reachable</h2>
        <p>
          Start it with <code>python -m uvicorn server.api:app --port 8000</code>
        </p>
        <pre>{fatal}</pre>
      </div>
    )
  if (!meta)
    return (
      <div className="splash">
        <Loader2 className="spin" size={36} />
        <p>Loading World Cup data…</p>
      </div>
    )

  const ctx = { template, recolor, setWidget, openMatch }
  const side = data?.sidebar || []
  const sideWidgets = side.filter((n) => n.t === 'w')
  const sideOther = side.filter((n) => n.t !== 'w')
  const ready = data && data.slug === route.slug && data.competition === dc

  return (
    <DashCtx.Provider value={ctx}>
      <div className="shell">
        <aside className="nav">
          <div className="brand" onClick={() => go('home', null, 'wc')}>
            <span className="icclogo"><img src="/icc-logo.png" alt="ICC" /></span>
            <div>
              <b>CricketWorldCup</b>
              <span>Analytics</span>
            </div>
          </div>
          <nav>
            {meta.pages.filter((p) => pages.includes(p.slug)).map((p) => {
              const Icon = ICONS[p.icon] || Home
              return (
                <a key={p.slug} className={p.slug === route.slug ? 'navitem on' : 'navitem'} href={`#${hashFor(p.slug, route.edition || (isMatch ? matchEdId : null), comp.code)}`}>
                  <Icon size={18} /> <span>{p.title}</span>
                </a>
              )
            })}
          </nav>
          {edition && (
            <div className="navedition">
              <img src={edition.logo} alt="" />
              <div>
                <span>Filtered to</span>
                <b>{edition.name}</b>
              </div>
              <button onClick={() => selectEdition(null)}>Clear</button>
            </div>
          )}
          <div className="navfoot">
            Men's ODI &amp; T20 World Cups
            <br />
            ESPNcricinfo + Cricsheet
          </div>
        </aside>

        <main className="main">
          {isMatch ? (
            <MatchView key={matchId} id={matchId} comp={route.comp} onEdition={setMatchEdId} onBack={back} go={go} />
          ) : (
            <>
          <CompetitionTabs competitions={meta.competitions.filter((c) => !c.hidden)} active={comp.code} onSelect={selectCompetition} />
          <EditionRail comp={comp} selected={route.edition} onSelect={selectEdition} />
          {loading && <div className="progress" />}
          <div className={`content ${loading ? 'dim' : ''}`}>
            {edition && <EditionBanner e={edition} comp={comp} />}
            {ready ? <PageHero hero={data.hero} /> : <div className="skeleton hero" />}
            {route.slug === 'home' && !edition && <Gallery comp={comp} onSelect={selectEdition} />}
            {err && <div className="alert error">{err}</div>}
            {ready && data.notes?.length > 0 && <div className="alert info">{data.notes[0]}</div>}
            {ready && (
              <>
                {side.length > 0 && (
                  <section className="filters">
                    <div className="filtertitle">
                      <SlidersHorizontal size={15} /> Filters{edition ? ` · ${edition.name}` : ''}
                    </div>
                    <div className="filtergrid">
                      {sideWidgets.map((w) => (
                        <Widget key={w.id} w={w} onChange={setWidget} />
                      ))}
                    </div>
                    <Nodes nodes={sideOther} ctx={ctx} />
                  </section>
                )}
                <div className="page" key={`${comp.code}|${route.slug}|${route.edition}`}>
                  <Nodes nodes={data.body} ctx={ctx} />
                </div>
              </>
            )}
            {!data && !err && (
              <div className="skeletons">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="skeleton" />
                ))}
              </div>
            )}
          </div>
            </>
          )}
        </main>
      </div>
    </DashCtx.Provider>
  )
}
