<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from './api'
import AppHeader from './components/AppHeader.vue'
import ChatPanel from './components/ChatPanel.vue'
import ConversationSidebar from './components/ConversationSidebar.vue'
import DocumentModal from './components/DocumentModal.vue'

const conversations = ref([])
const activeId = ref(null)
const messages = ref([])
const knowledge = ref({ document_count: 0, standards: [] })
const loading = ref(false)
const sidebarOpen = ref(false)
const errorMessage = ref('')
const activeDocument = ref(null)

const activeConversation = computed(() =>
  conversations.value.find((item) => item.conversation_id === activeId.value),
)

async function loadConversations() {
  conversations.value = await api.conversations()
}

async function loadKnowledge() {
  knowledge.value = await api.knowledgeStatus()
}

async function selectConversation(id) {
  activeId.value = id
  messages.value = await api.messages(id)
  sidebarOpen.value = false
}

async function newConversation() {
  const conversation = await api.createConversation()
  conversations.value.unshift(conversation)
  activeId.value = conversation.conversation_id
  messages.value = []
  sidebarOpen.value = false
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
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await api.sendMessage({
      conversation_id: conversationId,
      message: content,
    })
    messages.value.push({
      role: 'assistant',
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
      created_at: new Date().toISOString(),
    })
    await loadConversations()
  } catch (error) {
    errorMessage.value = error.message || '请求失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function followUp(text) {
  send(text)
}

function openDocument(source) {
  const lastUserMessage = [...messages.value].reverse().find((item) => item.role === 'user')
  activeDocument.value = {
    source,
    query: lastUserMessage?.content || '',
  }
}

onMounted(async () => {
  try {
    await Promise.all([loadConversations(), loadKnowledge()])
  } catch (error) {
    errorMessage.value = error.message || '服务连接失败'
  }
})
</script>

<template>
  <div class="app-shell">
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
      />
      <ChatPanel
        :messages="messages"
        :loading="loading"
        :error="errorMessage"
        @send="send"
        @follow-up="followUp"
        @view-source="openDocument"
      />
    </section>
    <DocumentModal
      v-if="activeDocument"
      :source="activeDocument.source"
      :query="activeDocument.query"
      @close="activeDocument = null"
    />
  </div>
</template>
