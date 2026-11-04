import React, { useMemo } from 'react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: true })

export function Html({ html, className }) {
  const clean = useMemo(() => DOMPurify.sanitize(html, { ADD_ATTR: ['style', 'target'] }), [html])
  return <div className={className} dangerouslySetInnerHTML={{ __html: clean }} />
}

export default function Markdown({ text, html, className = 'md' }) {
  const out = useMemo(() => (html ? text : marked.parse(text)), [text, html])
  return <Html html={out} className={className} />
}
