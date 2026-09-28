<script setup>
import { BookOpen, Sparkles } from 'lucide-vue-next'
import { nextTick, ref, watch } from 'vue'
import Composer from './Composer.vue'
import MessageBubble from './MessageBubble.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

defineEmits(['send', 'follow-up', 'view-source', 'view-detail'])

const listRef = ref(null)

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight
    }
  })
}

function scrollToTop() {
  if (listRef.value) {
    listRef.value.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

defineExpose({ scrollToTop })

watch(
  () => props.messages,
  () => scrollToBottom(),
  { deep: false },
)

watch(
  () => props.loading,
  (loading) => {
    if (!loading) scrollToBottom()
  },
)

const suggestions = [
  '住宅楼梯踏步宽度和高度有什么要求？',
  '高层公共建筑防火分区最大允许面积是多少？',
  '比较住宅设计规范和民用建筑通用规范的楼梯规定',
]
</script>

<template>
  <div class="chat-panel">
    <div v-if="!messages.length && !loading" class="chat-empty">
      <div class="empty-mark"><BookOpen :size="28" /></div>
      <h2>规宝</h2>
      <p>工程规范智能问答</p>
      <div class="suggestion-list">
        <button
          v-for="item in suggestions"
          :key="item"
          class="suggestion-button"
          type="button"
          @click="$emit('send', item)"
        >
          <Sparkles :size="15" />
          <span>{{ item }}</span>
        </button>
      </div>
    </div>
    <div v-else ref="listRef" class="message-list">
      <MessageBubble
        v-for="(message, index) in messages"
        :key="index"
        :message="message"
        @follow-up="$emit('follow-up', $event)"
        @view-source="$emit('view-source', $event)"
        @view-detail="$emit('view-detail', $event)"
      />
      <div v-if="loading" class="thinking-bubble">
        <span class="thinking-dot"></span>
        <span class="thinking-dot"></span>
        <span class="thinking-dot"></span>
      </div>
      <div v-if="error" class="chat-error">{{ error }}</div>
    </div>
    <Composer :loading="loading" @send="$emit('send', $event)" />
  </div>
</template>
