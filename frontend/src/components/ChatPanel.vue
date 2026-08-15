<script setup>
import { BookOpen, Sparkles } from 'lucide-vue-next'
import Composer from './Composer.vue'
import MessageBubble from './MessageBubble.vue'

defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

defineEmits(['send', 'follow-up', 'view-source', 'feedback'])

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
    <div v-else class="message-list">
      <MessageBubble
        v-for="(message, index) in messages"
        :key="index"
        :message="message"
        @follow-up="$emit('follow-up', $event)"
        @view-source="$emit('view-source', $event)"
        @feedback="$emit('feedback', $event)"
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
