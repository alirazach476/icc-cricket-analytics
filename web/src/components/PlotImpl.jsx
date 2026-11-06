import React, { useMemo } from 'react'
// A custom Plotly build with only the chart types this dashboard draws (the full bundle also carries 3D,
// WebGL, mapbox, contour, ...). Add a module here if a page starts using a new chart type.
import Plotly from 'plotly.js/lib/core'
import scatter from 'plotly.js/lib/scatter'
import bar from 'plotly.js/lib/bar'
import pie from 'plotly.js/lib/pie'
import heatmap from 'plotly.js/lib/heatmap'
import box from 'plotly.js/lib/box'
import violin from 'plotly.js/lib/violin'
import histogram from 'plotly.js/lib/histogram'
import scatterpolar from 'plotly.js/lib/scatterpolar'
import sankey from 'plotly.js/lib/sankey'
import treemap from 'plotly.js/lib/treemap'
import sunburst from 'plotly.js/lib/sunburst'
import waterfall from 'plotly.js/lib/waterfall'
import indicator from 'plotly.js/lib/indicator'
import choropleth from 'plotly.js/lib/choropleth'
import scattergeo from 'plotly.js/lib/scattergeo'
import createPlotlyComponent from 'react-plotly.js/factory'
import { Download } from 'lucide-react'
import { useDash } from '../ctx.js'
import { downloadCsv, figureRows, rowsToCsv } from '../chartData.js'

Plotly.register([scatter, bar, pie, heatmap, box, violin, histogram, scatterpolar, sankey, treemap, sunburst, waterfall, indicator, choropleth, scattergeo])

const Plot = createPlotlyComponent(Plotly)

const AXIS = { showline: false, zeroline: false, ticklen: 0, tickfont: { size: 11, color: '#9aa8c7' }, gridcolor: 'rgba(255,255,255,.065)' }
const strip = (t) => String(t || '').replace(/<[^>]+>/g, '')

// One consistent, designed look for every chart (the data and colours come from the server).
function style(f) {
  const stacked = ['stack', 'relative'].includes(f.layout.barmode)
  f.layout.title = { text: '' } // the title is shown in the card header instead
  const m = f.layout.margin || {}
  f.layout.margin = { ...m, t: m.t != null ? Math.max(12, m.t - 52) : 44 }
  f.layout.hoverlabel = { bgcolor: 'rgba(9,13,26,.97)', bordercolor: 'rgba(255,255,255,.28)', font: { size: 12, color: '#f1f5ff' }, align: 'left', ...(f.layout.hoverlabel || {}) }
  for (const k of Object.keys(f.layout)) {
    if (/^[xy]axis\d*$/.test(k)) {
      const ax = f.layout[k] || {}
      const title = typeof ax.title === 'string' ? { text: ax.title } : ax.title
      f.layout[k] = { ...AXIS, ...ax, ...(title ? { title: { ...title, font: { size: 12, color: '#9aa8c7', ...(title.font || {}) } } } : {}) }
    }
  }
  if (!f.layout.xaxis) f.layout.xaxis = { ...AXIS }
  if (!f.layout.yaxis) f.layout.yaxis = { ...AXIS }
  f.data = f.data.map((tr) => {
    const type = tr.type || 'scatter'
    if (type === 'bar') return { ...tr, opacity: tr.opacity ?? 0.94, marker: { cornerradius: stacked ? 3 : 7, ...(tr.marker || {}) } }
    if (type === 'scatter') {
      const mode = tr.mode || 'lines+markers'
      const out = { ...tr }
      if (mode.includes('markers')) out.marker = { ...(tr.marker || {}), line: { width: 1, color: 'rgba(255,255,255,.55)', ...((tr.marker || {}).line || {}) } }
      if (mode.includes('lines')) out.line = { width: 3, ...(tr.line || {}) }
      return out
    }
    if (type === 'heatmap') return { xgap: 2, ygap: 2, hoverongaps: false, ...tr }
    if (type === 'pie') return { hole: 0.5, ...tr, marker: { ...(tr.marker || {}), line: { color: 'rgba(8,12,24,.9)', width: 2, ...((tr.marker || {}).line || {}) } } }
    if (type === 'box') return { line: { width: 2 }, ...tr }
    return tr
  })
  return f
}

export default function PlotCard({ fig }) {
  const { template, recolor } = useDash()
  const { data, layout, frames } = useMemo(() => {
    const f = recolor({ data: fig.data, layout: { ...fig.layout, template }, frames: fig.frames })
    f.layout.autosize = true
    f.layout.paper_bgcolor = 'rgba(0,0,0,0)'
    return style(f)
  }, [fig, template, recolor])
  const height = layout.height || 380
  const rawTitle = (() => {
    const t = fig.layout && fig.layout.title
    return (typeof t === 'string' ? t : t && t.text) || ''
  })()
  const [head, ...rest] = String(rawTitle).split(/<br\s*\/?>/i)
  const sub = strip(rest.join(' '))
  const rows = useMemo(() => figureRows(fig), [fig])
  return (
    <div className="plotcard">
      <header className={`plot-head ${head ? '' : 'notitle'}`}>
        {head ? (
          <div className="plot-titles">
            <h4>{strip(head)}</h4>
            {sub && <small>{sub}</small>}
          </div>
        ) : null}
        {rows.length > 0 && (
          <button className="plotdl" title="Download the data behind this chart (CSV)" onClick={() => downloadCsv(rowsToCsv(rows), strip(rawTitle.replace(/<br\s*\/?>/gi, ' ')) || 'chart')}>
            <Download size={12} /> CSV
          </button>
        )}
      </header>
      <Plot
        data={data}
        layout={{ ...layout, width: undefined }}
        frames={frames}
        config={{ displaylogo: false, responsive: true, displayModeBar: 'hover', modeBarButtonsToRemove: ['lasso2d', 'select2d'] }}
        useResizeHandler
        style={{ width: '100%', height }}
      />
    </div>
  )
}
