<script setup>
import { FileText, MapPin } from 'lucide-vue-next'
import { computed } from 'vue'
import { richTextPreview } from '../lib/format'

const props = defineProps({
  source: { type: Object, required: true },
})

const preview = computed(() => richTextPreview(props.source.snippet))

defineEmits(['open'])
</script>

<template>
  <div
    class="source-card source-card-clickable"
    role="button"
    tabindex="0"
    @click="$emit('open', source)"
    @keydown.enter="$emit('open', source)"
  >
    <div class="source-card-top">
      <span class="source-badge">{{ source.document_type }}</span>
      <span class="source-region"><MapPin :size="12" />{{ source.region }}</span>
    </div>
    <div class="source-title">{{ source.standard }}</div>
    <div class="source-subtitle">{{ source.title }}</div>
    <div class="source-location">
      <FileText :size="13" />
      <span>
        {{ source.chapter }} · {{ source.article }} · 第 {{ source.book_page || source.page }} 页
        <span v-if="source.book_page && source.book_page !== source.page">
          （PDF 第 {{ source.page }} 页）
        </span>
      </span>
    </div>
    <div class="source-score">相关度 {{ Number(source.score).toFixed(2) }}</div>
    <p class="source-snippet">{{ preview }}</p>
  </div>
</template>
