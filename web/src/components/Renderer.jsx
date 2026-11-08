import React, { useState } from 'react'
import { Info, AlertTriangle, XCircle, CheckCircle2, ChevronDown } from 'lucide-react'
import Plot from './Plot.jsx'
import Table from './Table.jsx'
import Markdown from './Markdown.jsx'
import Graphviz from './Graphviz.jsx'
import Widget from './Widgets.jsx'
import { WithFlag } from './Flag.jsx'
import MatchCentre from './MatchCentre.jsx'
import Fixtures from './Fixtures.jsx'

const ALERT_ICON = { info: Info, warning: AlertTriangle, error: XCircle, success: CheckCircle2 }

function Tabs({ node, ctx }) {
  const [i, setI] = useState(0)
  return (
    <div className="tabs">
      <div className="tablist" role="tablist">
        {node.labels.map((l, k) => (
          <button key={k} role="tab" aria-selected={k === i} className={k === i ? 'tab on' : 'tab'} onClick={() => setI(k)}>{l}</button>
        ))}
      </div>
      <div className="tabpanel" key={i}>
        <Nodes nodes={node.items[i]} ctx={ctx} />
      </div>
    </div>
  )
}

function Expander({ node, ctx }) {
  const [open, setOpen] = useState(node.open)
  return (
    <div className={`expander ${open ? 'open' : ''}`}>
      <button onClick={() => setOpen(!open)}>{node.label}<ChevronDown size={16} /></button>
      {open && <div className="expbody"><Nodes nodes={node.items} ctx={ctx} /></div>}
    </div>
  )
}

export function Node({ n, ctx }) {
  switch (n.t) {
    case 'tabs': return <Tabs node={n} ctx={ctx} />
    case 'cols':
      return (
        <div className="cols" style={{ gridTemplateColumns: n.w.map((x) => `minmax(0, ${x}fr)`).join(' ') }}>
          {n.items.map((c, i) => <div className="col" key={i}><Nodes nodes={c} ctx={ctx} /></div>)}
        </div>
      )
    case 'expander': return <Expander node={n} ctx={ctx} />
    case 'box': return <div className="box"><Nodes nodes={n.items} ctx={ctx} /></div>
    case 'md': return <Markdown text={n.text} html={n.html} />
    case 'caption': return <p className="caption">{n.text}</p>
    case 'h1': return <h1 className="h1">{n.text}</h1>
    case 'h2': return <h2 className="h2">{n.text}</h2>
    case 'h3': return <h3 className="h3">{n.text}</h3>
    case 'hr': return <hr />
    case 'code': return <pre className="code"><code>{n.text}</code></pre>
    case 'alert': {
      const Icon = ALERT_ICON[n.kind] || Info
      return <div className={`alert ${n.kind}`}><Icon size={18} /><Markdown text={n.text} html={false} className="md inline" /></div>
    }
    case 'metric':
      return (
        <div className="metric" title={n.help || ''}>
          <div className="mlabel">{n.label}</div>
          <div className="mvalue"><WithFlag text={n.value} h={20} /></div>
          {n.delta && <div className="mdelta">{n.delta}</div>}
        </div>
      )
    case 'plot': return <Plot fig={n.fig} />
    case 'table': return <Table node={n} />
    case 'graphviz': return <div className="plotcard"><Graphviz src={n.src} /></div>
    case 'fixtures': return <Fixtures data={n.data} />
    case 'matchcentre': return <MatchCentre d={n.data} charts={n.charts} />
    case 'w': return <Widget w={n} onChange={ctx.setWidget} />
    default: return null
  }
}

export function Nodes({ nodes, ctx }) {
  return nodes.map((n, i) => <Node key={i} n={n} ctx={ctx} />)
}
