<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from './api'
import AppHeader from './components/AppHeader.vue'
import ChatPanel from './components/ChatPanel.vue'
import ConversationSidebar from './components/ConversationSidebar.vue'
import DocumentModal from './components/DocumentModal.vue'
import FeedbackDashboard from './components/FeedbackDashboard.vue'
import { track, trackPageView } from './lib/analytics'

const isDashboardRoute = window.location.pathname.replace(/\/+$/, '') === '/dashboard'
const conversations = ref([])
const activeId = ref(null)
const messages = ref([])
const knowledge = ref({ document_count: 0, standards: [] })
const loading = ref(false)
const sidebarOpen = ref(false)
const errorMessage = ref('')
const activeDocument = ref(null)
const chatPanelRef = ref(null)

const activeConversation = computed(() =>
  conversations.value.find((item) => item.conversation_id === activeId.value),
)

function shouldSearchStandards(result) {
  if (['chitchat', 'fallback', 'outside_region'].includes(result.intent_alias)) {
    return false
  }
  return Boolean(result.intent || result.sources?.length)
}

function filterSearchItems(result, items) {
  if (result.intent_alias !== 'compare_query') return items
  const comparedStandards = new Set(
    (result.sources || []).map((source) =>
      String(source.standard || '').replace(/\s+/g, ''),
    ),
  )
  if (!comparedStandards.size) return []
  return items.filter((item) =>
    comparedStandards.has(String(item.standard || '').replace(/\s+/g, '')),
  )
}

async function loadConversations() {
  conversations.value = await api.conversations()
}

async function loadKnowledge() {
  knowledge.value = await api.knowledgeStatus()
}

async function selectConversation(id) {
  activeId.value = id
  messages.value = await restoreHistorySearch(id)
  sidebarOpen.value = false
  track('conversation_open', {}, { conversationId: id })
}

async function restoreHistorySearch(id) {
  const records = await api.messages(id)
  const restored = []
  let lastUserContent = ''
  for (const record of records) {
    const item = { ...record }
    if (item.role === 'user') {
      lastUserContent = item.content || ''
    }
    if (
      item.role === 'assistant' &&
      lastUserContent &&
      shouldSearchStandards(item)
    ) {
      try {
        const searchResult = await api.search(lastUserContent)
        item.search_items = filterSearchItems(
          item,
          searchResult.items || [],
        )
      } catch {
        item.search_items = item.search_items || []
      }
    }
    restored.push(item)
  }
  return restored
}

async function newConversation() {
  const conversation = await api.createConversation()
  conversations.value.unshift(conversation)
  activeId.value = conversation.conversation_id
  messages.value = []
  sidebarOpen.value = false
  track('new_conversation', {}, { conversationId: conversation.conversation_id })
}

async function removeConversation(id) {
  if (!window.confirm('删除这个会话？')) return
  await api.deleteConversation(id)
  if (activeId.value === id) {
    activeId.value = null
    messages.value = []
  }
  await loadConversations()
}

async function send(text) {
  const content = text.trim()
  if (!content || loading.value) return
  const startedAt = performance.now()
  const requestId =
    (crypto.randomUUID && crypto.randomUUID()) ||
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`

  let conversationId = activeId.value
  if (!conversationId) {
    const conversation = await api.createConversation()
    conversationId = conversation.conversation_id
    activeId.value = conversationId
    await loadConversations()
  }

  messages.value.push({
    role: 'user',
    content,
    created_at: new Date().toISOString(),
  })
  track(
    'question_submit',
    {
      request_id: requestId,
      question: content.slice(0, 500),
      question_length: content.length,
    },
    { conversationId },
  )
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await api.sendMessage({
      conversation_id: conversationId,
      message: content,
    })
    track(
      'answer_complete',
      {
        request_id: requestId,
        question: content.slice(0, 500),
        intent: result.intent || '',
        source_count: result.sources?.length || 0,
        latency_ms: Math.round(performance.now() - startedAt),
        answer_chars: result.reply?.length || 0,
      },
      {
        conversationId: result.conversation_id,
        messageId: result.message_id,
        traceId: result.trace_id,
      },
    )
    let searchItems = []
    if (shouldSearchStandards(result)) {
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const searchResult = await api.search(content)
          searchItems = filterSearchItems(result, searchResult.items || [])
          if (searchItems.length) break
        } catch {
          searchItems = []
        }
        if (attempt === 0) {
          await new Promise((resolve) => setTimeout(resolve, 400))
        }
      }
    }
    messages.value.push({
      role: 'assistant',
      conversation_id: result.conversation_id,
      message_id: result.message_id,
      trace_id: result.trace_id,
      content: result.reply,
      sources: result.sources,
      reasoning: result.reasoning,
      follow_ups: result.follow_ups,
      recommendations: result.recommendations,
      region_path: result.region_path,
      keywords: result.keywords,
      web_results: result.web_results,
      web_note: result.web_note,
      memory: result.memory,
      intent: result.intent,
      intent_label: result.intent_label,
      intent_source: result.intent_source,
      intent_confidence: result.intent_confidence,
      intent_alias: result.intent_alias,
      search_items: searchItems,
      created_at: new Date().toISOString(),
    })
    await loadConversations()
  } catch (error) {
    errorMessage.value = error.message || '请求失败，请稍后重试'
    track(
      'answer_error',
      {
        request_id: requestId,
        question: content.slice(0, 500),
        latency_ms: Math.round(performance.now() - startedAt),
      },
      { conversationId },
    )
  } finally {
    loading.value = false
  }
}

function followUp(text) {
  track('follow_up_click')
  send(text)
}

function goHome() {
  sidebarOpen.value = false
  activeDocument.value = null
  chatPanelRef.value?.scrollToTop()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function openDocument(detail) {
  const lastUserMessage = [...messages.value].reverse().find((item) => item.role === 'user')
  activeDocument.value = {
    doc_id: detail.doc_id,
    query: lastUserMessage?.content || '',
    article: detail.article || '',
    page: detail.book_page || detail.page || null,
  }
  track(
    'source_open',
    {
      doc_id: detail.doc_id || '',
      article: detail.article || '',
      page: detail.book_page || detail.page || null,
    },
    { conversationId: activeId.value },
  )
}

onMounted(async () => {
  if (isDashboardRoute) return
  trackPageView({ page_name: '规范问答' })
  if ('scrollRestoration' in history) {
    history.scrollRestoration = 'manual'
  }
  window.scrollTo(0, 0)
  try {
    await Promise.all([loadConversations(), loadKnowledge()])
  } catch (error) {
    errorMessage.value = error.message || '服务连接失败'
  }
})
</script>

<template>
  <FeedbackDashboard v-if="isDashboardRoute" />
  <div v-else class="app-shell">
    <div
      v-if="sidebarOpen"
      class="sidebar-overlay"
      @click="sidebarOpen = false"
    ></div>
    <ConversationSidebar
      :class="{ open: sidebarOpen }"
      :conversations="conversations"
      :active-id="activeId"
      @select="selectConversation"
      @new="newConversation"
      @delete="removeConversation"
      @close="sidebarOpen = false"
    />
    <section class="main-pane">
      <AppHeader
        :title="activeConversation?.title"
        :document-count="knowledge.document_count"
        :standard-count="knowledge.standards.length"
        @menu="sidebarOpen = true"
        @new="newConversation"
        @home="goHome"
      />
      <ChatPanel
        ref="chatPanelRef"
        :messages="messages"
        :loading="loading"
        :error="errorMessage"
        @send="send"
        @follow-up="followUp"
        @view-source="openDocument"
        @view-detail="openDocument"
      />
    </section>
    <DocumentModal
      v-if="activeDocument"
      :doc-id="activeDocument.doc_id"
      :query="activeDocument.query"
      :article="activeDocument.article"
      :page="activeDocument.page"
      @close="activeDocument = null"
    />
  </div>
</template>
