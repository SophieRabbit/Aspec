export function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

export function richText(value) {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/\n/g, '<br />')
}

export function linkifyUrls(html) {
  return html.replace(
    /https?:\/\/[^\s<]+/g,
    (url) => {
      const cleanUrl = url.replace(/[.,;:!?]+$/, '')
      return `<a href="${escapeHtml(cleanUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(cleanUrl)}</a>`
    },
  )
}

export function highlightKeywords(html, keywords) {
  const sorted = [...keywords].sort((a, b) => b.text.length - a.text.length)
  for (const item of sorted) {
    const token = escapeHtml(item.text)
    const className =
      item.kind === 'region' ? 'kw-region' : item.kind === 'code' ? 'kw-code' : 'kw-topic'
    html = html.replaceAll(token, `<span class="${className}">${token}</span>`)
  }
  return html
}

export function formatTime(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  return new Intl.DateTimeFormat('zh-CN', {
    month: sameDay ? undefined : 'numeric',
    day: sameDay ? undefined : 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
