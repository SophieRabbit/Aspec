<script setup>
import { Gauge, Layers, Tag } from 'lucide-vue-next'

defineProps({
  intent: { type: String, default: '' },
  label: { type: String, default: '' },
  source: { type: String, default: '' },
  confidence: { type: Number, default: 0 },
  alias: { type: String, default: '' },
})

const sourceLabels = {
  rules: '规则匹配',
  llm: 'LLM 分类',
  fallback: '低置信度兜底',
}
</script>

<template>
  <div class="intent-trace">
    <span class="intent-trace-item">
      <Tag :size="13" />
      意图：{{ label || intent }}
    </span>
    <span class="intent-trace-item">
      <Layers :size="13" />
      层级：{{ sourceLabels[source] || source || '未知' }}
    </span>
    <span class="intent-trace-item">
      <Gauge :size="13" />
      置信度：{{ Math.round((confidence || 0) * 100) }}%
    </span>
    <span v-if="alias" class="intent-trace-alias">{{ alias }}</span>
  </div>
</template>
