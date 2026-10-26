const API_BASE = (import.meta.env?.VITE_API_BASE || '').replace(/\/$/, '')

function ensureUserId() {
  try {
    let userId = localStorage.getItem('guibao_user_id')
    if (!userId) {
      userId =
        (crypto.randomUUID && crypto.randomUUID()) ||
        `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
      localStorage.setItem('guibao_user_id', userId)
    }
    return userId
  } catch {
    return 'default'
  }
}

async function request(path, options = {}) {
  const { headers, ...rest } = options
  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': ensureUserId(),
      ...(headers || {}),
    },
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `请求失败：${response.status}`)
  }
  return response.json()
}

export const api = {
  health: () => request('/api/health'),
  knowledgeStatus: () => request('/api/knowledge/status'),
  conversations: () => request('/api/conversations'),
  createConversation: () =>
    request('/api/conversations', { method: 'POST' }),
  deleteConversation: (id) =>
    request(`/api/conversations/${id}`, { method: 'DELETE' }),
  messages: (id) => request(`/api/conversations/${id}/messages`),
  documentContext: (docId, query) =>
    request(
      `/api/knowledge/documents/${encodeURIComponent(docId)}/context?query=${encodeURIComponent(query)}`,
    ),
  search: (query) =>
    request(`/api/search?q=${encodeURIComponent(query)}`),
  specDetail: (docId, query, article = '', page = null) => {
    const params = new URLSearchParams({ q: query || '' })
    if (article) params.set('article', article)
    if (page) params.set('page', String(page))
    return request(
      `/api/spec/${encodeURIComponent(docId)}/detail?${params.toString()}`,
    )
  },
  sendMessage: (payload) =>
    request('/api/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  submitFeedback: (payload) =>
    request('/api/feedback', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
