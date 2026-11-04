import React, { Suspense, lazy } from 'react'

// Plotly is ~4.7 MB: load it as its own chunk so the page chrome, tables and text appear first.
const PlotImpl = lazy(() => import('./PlotImpl.jsx'))

export default function PlotCard({ fig }) {
  const height = fig?.layout?.height || 380
  return (
    <Suspense
      fallback={
        <div className="plotcard">
          <div className="skeleton" style={{ height, margin: 0 }} aria-label="Loading chart" />
        </div>
      }
    >
      <PlotImpl fig={fig} />
    </Suspense>
  )
}
