<script setup>
import { MessageSquare, Plus, Trash2, X } from 'lucide-vue-next'
import { formatTime } from '../lib/format'

defineProps({
  conversations: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
})

defineEmits(['select', 'new', 'delete', 'close'])
</script>

<template>
  <aside class="conversation-sidebar">
    <div class="sidebar-head">
      <span class="sidebar-title">会话</span>
      <button class="icon-button mobile-close" type="button" @click="$emit('close')">
        <X :size="18" />
      </button>
    </div>
    <button class="new-chat-button" type="button" @click="$emit('new')">
      <Plus :size="16" />
      <span>新建会话</span>
    </button>
    <div class="conversation-list">
      <button
        v-for="conversation in conversations"
        :key="conversation.conversation_id"
        class="conversation-item"
        :class="{ active: conversation.conversation_id === activeId }"
        type="button"
        @click="$emit('select', conversation.conversation_id)"
      >
        <MessageSquare :size="16" class="conversation-icon" />
        <span class="conversation-content">
          <span class="conversation-title">{{ conversation.title }}</span>
          <span class="conversation-meta">{{ conversation.message_count }} 条消息 · {{ formatTime(conversation.updated_at) }}</span>
        </span>
        <span
          class="conversation-delete"
          role="button"
          tabindex="0"
          @click.stop="$emit('delete', conversation.conversation_id)"
          @keydown.enter.stop="$emit('delete', conversation.conversation_id)"
        >
          <Trash2 :size="14" />
        </span>
      </button>
      <div v-if="!conversations.length" class="sidebar-empty">暂无会话</div>
    </div>
  </aside>
</template>
