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

export default function PlotCard({ fig }) {
  const { template, recolor } = useDash()
  const { data, layout, frames } = useMemo(() => {
    const f = recolor({ data: fig.data, layout: { ...fig.layout, template }, frames: fig.frames })
    f.layout.autosize = true
    f.layout.paper_bgcolor = 'rgba(0,0,0,0)'
    return f
  }, [fig, template, recolor])
  const height = layout.height || 380
  const title = (() => {
    const t = fig.layout && fig.layout.title
    return (typeof t === 'string' ? t : t && t.text) || 'chart'
  })()
  const rows = useMemo(() => figureRows(fig), [fig])
  return (
    <div className="plotcard">
      {rows.length > 0 && (
        <button
          className="plotdl"
          title="Download the data behind this chart (CSV)"
          onClick={() => downloadCsv(rowsToCsv(rows), String(title).replace(/<br>/g, ' '))}
        >
          <Download size={12} /> CSV
        </button>
      )}
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
