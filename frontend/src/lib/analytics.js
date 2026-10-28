import { API_BASE, ensureVisitorId } from '../api'

const SESSION_ID_KEY = 'guibao_analytics_session'

function getSessionId() {
  try {
    let sessionId = sessionStorage.getItem(SESSION_ID_KEY)
    if (!sessionId) {
      sessionId =
        (crypto.randomUUID && crypto.randomUUID()) ||
        `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
      sessionStorage.setItem(SESSION_ID_KEY, sessionId)
    }
    return sessionId
  } catch {
    return 'session-unavailable'
  }
}

function cleanPath() {
  return typeof window === 'undefined' ? '/' : window.location.pathname || '/'
}

export function track(name, properties = {}, context = {}) {
  try {
    const visitorId = ensureVisitorId()
    const event = {
      name,
      path: cleanPath(),
      conversation_id: context.conversationId || '',
      message_id: String(context.messageId || ''),
      trace_id: context.traceId || '',
      properties,
    }
    fetch(`${API_BASE}/api/analytics/events`, {
      method: 'POST',
      credentials: 'omit',
      keepalive: true,
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': visitorId,
        'X-Visitor-Id': visitorId,
        'X-Session-Id': getSessionId(),
      },
      body: JSON.stringify({ events: [event] }),
    }).catch(() => {})
  } catch {
    // Analytics must never interrupt the question flow.
  }
}

export function trackPageView(properties = {}) {
  let referrerHost = ''
  try {
    referrerHost = document.referrer
      ? new URL(document.referrer).hostname
      : ''
  } catch {
    referrerHost = ''
  }
  track('page_view', {
    ...properties,
    referrer_host: referrerHost,
    language: navigator.language || '',
    viewport_width: window.innerWidth || 0,
  })
}
