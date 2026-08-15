<script setup>
import { ArrowUp, LoaderCircle } from 'lucide-vue-next'
import { nextTick, ref } from 'vue'

const props = defineProps({
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['send'])
const text = ref('')
const textarea = ref(null)

function resize() {
  const element = textarea.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(element.scrollHeight, 160)}px`
}

function submit() {
  const value = text.value.trim()
  if (!value || props.loading) return
  emit('send', value)
  text.value = ''
  nextTick(() => {
    resize()
    textarea.value?.focus()
  })
}

function onKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    submit()
  }
}
</script>

<template>
  <footer class="composer-wrap">
    <div class="composer">
      <textarea
        ref="textarea"
        v-model="text"
        rows="1"
        placeholder="输入规范问题，Enter 发送"
        :disabled="loading"
        @input="resize"
        @keydown="onKeydown"
      ></textarea>
      <button
        class="send-button"
        type="button"
        :disabled="loading || !text.trim()"
        @click="submit"
      >
        <LoaderCircle v-if="loading" :size="18" class="spin" />
        <ArrowUp v-else :size="18" />
      </button>
    </div>
  </footer>
</template>
