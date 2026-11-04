import React, { useMemo } from 'react'
import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'
import { useDash } from '../ctx.js'

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
  return (
    <div className="plotcard">
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
