<script setup>
import { BookOpen, Database, Menu, Plus } from 'lucide-vue-next'

defineProps({
  title: { type: String, default: '' },
  documentCount: { type: Number, default: 0 },
  standardCount: { type: Number, default: 0 },
})

defineEmits(['menu', 'new', 'home'])
</script>

<template>
  <header class="app-header">
    <button class="icon-button mobile-menu" type="button" @click="$emit('menu')">
      <Menu :size="18" />
    </button>
    <div class="brand">
      <span class="brand-mark"><BookOpen :size="18" /></span>
      <span class="brand-name">规宝</span>
    </div>
    <nav class="header-nav" aria-label="主导航">
      <button class="header-nav-link active" type="button" @click="$emit('home')">
        首页
      </button>
    </nav>
    <div class="conversation-title" :title="title">{{ title || '工程规范智能问答' }}</div>
    <div class="header-actions">
      <div class="knowledge-chip" title="知识库状态">
        <Database :size="14" />
        <span>{{ documentCount }} 份规范 · {{ standardCount }} 项标准</span>
      </div>
      <button class="primary-button" type="button" @click="$emit('new')">
        <Plus :size="16" />
        <span>新对话</span>
      </button>
    </div>
  </header>
</template>
