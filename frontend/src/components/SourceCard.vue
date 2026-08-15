<script setup>
import { FileText, MapPin } from 'lucide-vue-next'

defineProps({
  source: { type: Object, required: true },
})

defineEmits(['open'])
</script>

<template>
  <div
    class="source-card source-card-clickable"
    role="button"
    tabindex="0"
    @click="$emit('open')"
    @keydown.enter="$emit('open')"
  >
    <div class="source-card-top">
      <span class="source-badge">{{ source.document_type }}</span>
      <span class="source-region"><MapPin :size="12" />{{ source.region }}</span>
    </div>
    <div class="source-title">{{ source.standard }}</div>
    <div class="source-subtitle">{{ source.title }}</div>
    <div class="source-location">
      <FileText :size="13" />
      <span>{{ source.chapter }} · {{ source.article }} · 第 {{ source.page }} 页</span>
    </div>
    <div class="source-score">相关度 {{ Number(source.score).toFixed(2) }}</div>
    <p class="source-snippet">{{ source.snippet }}</p>
  </div>
</template>
