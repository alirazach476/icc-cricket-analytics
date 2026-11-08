import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'
import './matchcentre.css'
import './design.css'
import './matchview.css'
import './fixtures.css'
import './backdrop.css'

createRoot(document.getElementById('root')).render(<App />)

// start fetching the chart library in the background while the first page data loads
setTimeout(() => import('./components/PlotImpl.jsx'), 0)
