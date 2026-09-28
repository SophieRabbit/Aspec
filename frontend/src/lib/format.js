export function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function escapeAndFormatInline(value) {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<u>$1</u>')
}

function stripClauseWrapper(line) {
  return String(line || '')
    .trim()
    .replace(/^<u\s+class=["']clause-hit["']>\s*/i, '')
    .replace(/\s*<\/u>$/i, '')
}

export function isMarkdownTableLine(line) {
  const normalized = stripClauseWrapper(line)
  if (!normalized.includes('|')) return false
  if (normalized.startsWith('|')) return true
  const pipeCount = (normalized.match(/\|/g) || []).length
  return pipeCount >= 2 && /@(?:rowspan|colspan)=\d+/i.test(normalized)
}

function normalizeMarkdownTableLine(line) {
  const normalized = stripClauseWrapper(line)
  return normalized.startsWith('|') ? normalized : `| ${normalized}`
}

export function richTextPreview(value) {
  return String(value || '')
    .split('\n')
    .map((line) =>
      stripClauseWrapper(line)
        .replace(/<[^>]+>/g, '')
        .replace(/\s*@(?:rowspan|colspan)=\d+/gi, '')
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map((cell) => cell.trim())
        .filter(Boolean)
        .join('  '),
    )
    .map((line) => line.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .join(' ')
}

function splitTableRow(line) {
  const trimmed = String(line).trim().replace(/^\|/, '').replace(/\|$/, '')
  const cells = []
  let current = ''
  for (let index = 0; index < trimmed.length; index += 1) {
    const character = trimmed[index]
    if (character === '\\' && trimmed[index + 1] === '|') {
      current += '|'
      index += 1
    } else if (character === '|') {
      cells.push(current.trim())
      current = ''
    } else {
      current += character
    }
  }
  cells.push(current.trim())
  return cells
}

function parseTableCell(raw) {
  let value = String(raw || '').trim()
  const span = { rowspan: 1, colspan: 1 }
  value = value
    .replace(/\s*@(rowspan|colspan)=(\d+)/gi, (_, name, amount) => {
      span[name.toLowerCase()] = Math.max(1, Number(amount) || 1)
      return ''
    })
    .trim()
  return { value, ...span }
}

function tableGridKey(row, column) {
  return `${row}:${column}`
}

function fillTableGrid(grid, latestByColumn, record) {
  for (let row = record.startRow; row <= record.endRow; row += 1) {
    for (let column = record.startColumn; column <= record.endColumn; column += 1) {
      grid.set(tableGridKey(row, column), record)
    }
  }
  for (
    let column = record.startColumn;
    column <= record.endColumn;
    column += 1
  ) {
    latestByColumn.set(column, record)
  }
}

function normalizeTableSpans(rows) {
  const grid = new Map()
  const latestByColumn = new Map()
  const normalizedRows = []

  rows.forEach((row, rowIndex) => {
    const normalizedRow = []
    let columnIndex = 0
    let inputStart = 0

    if (rowIndex > 0) {
      let leadingPlaceholderCount = 0
      while (
        leadingPlaceholderCount < row.length &&
        !row[leadingPlaceholderCount].value &&
        (row[leadingPlaceholderCount].rowspan > 1 ||
          row[leadingPlaceholderCount].colspan > 1)
      ) {
        leadingPlaceholderCount += 1
      }
      const leadingRecord = latestByColumn.get(0)
      if (
        leadingPlaceholderCount > 0 &&
        !grid.has(tableGridKey(rowIndex, 0)) &&
        leadingRecord?.cell.value
      ) {
        leadingRecord.endRow = Math.max(
          leadingRecord.endRow,
          rows.length - 1,
        )
        leadingRecord.cell.rowspan =
          leadingRecord.endRow - leadingRecord.startRow + 1
        fillTableGrid(grid, latestByColumn, leadingRecord)
        inputStart = leadingPlaceholderCount
        columnIndex = leadingRecord.endColumn + 1
      }
    }

    for (
      let inputIndex = inputStart;
      inputIndex < row.length;
      inputIndex += 1
    ) {
      const cell = row[inputIndex]
      const isSpanPlaceholder =
        !cell.value && (cell.rowspan > 1 || cell.colspan > 1)
      const occupied = grid.get(tableGridKey(rowIndex, columnIndex))
      const continued = latestByColumn.get(columnIndex)
      const active =
        occupied ||
        (isSpanPlaceholder &&
        !continued?.cell.value &&
        continued?.endRow === rowIndex - 1
          ? continued
          : null)

      if (isSpanPlaceholder && active) {
        const endRow = Math.min(
          rows.length - 1,
          rowIndex + cell.rowspan - 1,
        )
        const endColumn = columnIndex + cell.colspan - 1
        if (active.startRow <= rowIndex && active.endColumn >= endColumn) {
          active.endRow = Math.max(active.endRow, endRow)
          active.cell.rowspan = active.endRow - active.startRow + 1
          fillTableGrid(grid, latestByColumn, active)
          columnIndex = active.endColumn + 1
          continue
        }
      }

      while (grid.has(tableGridKey(rowIndex, columnIndex))) {
        const active = grid.get(tableGridKey(rowIndex, columnIndex))
        columnIndex = active.endColumn + 1
      }

      const record = {
        cell,
        startRow: rowIndex,
        endRow: Math.min(rows.length - 1, rowIndex + cell.rowspan - 1),
        startColumn: columnIndex,
        endColumn: columnIndex + cell.colspan - 1,
      }
      fillTableGrid(grid, latestByColumn, record)
      normalizedRow.push(cell)
      columnIndex = record.endColumn + 1
    }

    normalizedRows.push(normalizedRow)
  })

  return normalizedRows
}

export function markdownTableToHtml(
  block,
  { tableClass = 'msg-table', allowHtml = false } = {},
) {
  const lines = String(block)
    .split('\n')
    .map((line) => line.trim())
    .filter(isMarkdownTableLine)
    .map(normalizeMarkdownTableLine)
  if (!lines.length) return ''
  let rows = lines.map((line) => splitTableRow(line).map(parseTableCell))
  rows = rows.filter((row) =>
    row.some((cell) => cell.value && cell.value !== '~'),
  )
  rows = normalizeTableSpans(rows)
  const hasHeaderSeparator =
    rows.length >= 2 &&
    rows[1].every((cell) => /^:?-+:?$/.test(cell.value))
  if (hasHeaderSeparator) {
    rows.splice(1, 1)
  }
  if (!rows.length) return ''
  const renderCell = (cell, tag) => {
    const rowspan = cell.rowspan > 1 ? ` rowspan="${cell.rowspan}"` : ''
    const colspan = cell.colspan > 1 ? ` colspan="${cell.colspan}"` : ''
    const content = allowHtml ? cell.value : escapeAndFormatInline(cell.value)
    return `<${tag}${rowspan}${colspan}>${content}</${tag}>`
  }
  const renderRow = (row, tag) =>
    row
      .filter((cell) => cell.value !== '~')
      .map((cell) => renderCell(cell, tag))
      .join('')
  const headerRowCount = hasHeaderSeparator ? 1 : 0
  let html = `<table class="${tableClass}">`
  if (headerRowCount) {
    html += '<thead>'
    for (const row of rows.slice(0, headerRowCount)) {
      html += '<tr>'
      html += renderRow(row, 'th')
      html += '</tr>'
    }
    html += '</thead>'
  }
  html += '<tbody>'
  for (const row of rows.slice(headerRowCount)) {
    html += '<tr>'
    html += renderRow(row, 'td')
    html += '</tr>'
  }
  return html + '</tbody></table>'
}

export function richText(value) {
  const text = String(value || '')
  const parts = []
  const lines = text.split('\n')
  let index = 0
  while (index < lines.length) {
    if (!isMarkdownTableLine(lines[index])) {
      parts.push(escapeHtml(lines[index]))
      index += 1
      continue
    }

    const tableLines = []
    while (index < lines.length) {
      const line = lines[index].trim()
      if (isMarkdownTableLine(line)) {
        tableLines.push(normalizeMarkdownTableLine(line))
        index += 1
        continue
      }
      if (!line) {
        let nextIndex = index + 1
        while (nextIndex < lines.length && !lines[nextIndex].trim()) {
          nextIndex += 1
        }
        if (nextIndex < lines.length && isMarkdownTableLine(lines[nextIndex])) {
          index = nextIndex
          continue
        }
      }
      break
    }
    parts.push(markdownTableToHtml(tableLines.join('\n')))
  }
  return parts
    .join('\n')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<u>$1</u>')
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
