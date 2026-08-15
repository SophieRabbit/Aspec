<script setup>
import { Calculator, ChevronDown, Search, Scale } from 'lucide-vue-next'
import { ref } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
})

const expanded = ref(false)

function stepIcon(tool) {
  if (tool === 'calculate') return Calculator
  if (tool === 'compare') return Scale
  return Search
}
</script>

<template>
  <details class="reasoning-trace" :open="expanded" @toggle="expanded = $event.target.open">
    <summary>
      <span class="reasoning-summary">
        <span class="reasoning-dot"></span>
        Agent 推理轨迹
      </span>
      <ChevronDown :size="15" class="chevron" />
    </summary>
    <ol class="reasoning-steps">
      <li v-for="(step, index) in props.steps" :key="index" class="reasoning-step">
        <component :is="stepIcon(step.tool)" :size="15" class="step-icon" />
        <div class="step-text">
          <div class="step-title">{{ step.title }}<span class="step-duration">{{ step.duration_ms }}ms</span></div>
          <div class="step-detail">{{ step.detail }}</div>
        </div>
      </li>
    </ol>
  </details>
</template>
