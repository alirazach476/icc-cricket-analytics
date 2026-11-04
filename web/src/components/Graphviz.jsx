import React, { useEffect, useState } from 'react'
import { instance } from '@viz-js/viz'

let vizPromise = null

export default function Graphviz({ src }) {
  const [svg, setSvg] = useState('')
  useEffect(() => {
    let live = true
    vizPromise = vizPromise || instance()
    vizPromise
      .then((v) => {
        const el = v.renderSVGElement(src)
        el.removeAttribute('width')
        el.removeAttribute('height')
        el.style.maxWidth = '100%'
        el.style.height = 'auto'
        if (live) setSvg(el.outerHTML)
      })
      .catch(() => live && setSvg('<p>Could not draw this diagram.</p>'))
    return () => { live = false }
  }, [src])
  return <div className="graphviz" dangerouslySetInnerHTML={{ __html: svg }} />
}
