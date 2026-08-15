async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
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
  sendMessage: (payload) =>
    request('/api/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
