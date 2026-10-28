<script setup>
import { ArrowUp, LoaderCircle } from 'lucide-vue-next'
import { computed, nextTick, ref } from 'vue'

const MAX_QUESTION_LENGTH = 4000
const props = defineProps({
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['send'])
const text = ref('')
const textarea = ref(null)
const error = ref('')

const remaining = computed(() => MAX_QUESTION_LENGTH - text.value.length)
const nearLimit = computed(() => remaining.value <= 400)

function resize() {
  const element = textarea.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(element.scrollHeight, 160)}px`
}

function submit() {
  const value = text.value.trim()
  if (!value || props.loading) return
  if (text.value.length > MAX_QUESTION_LENGTH) {
    error.value = `问题最多 ${MAX_QUESTION_LENGTH} 字，请精简后再发送`
    return
  }
  error.value = ''
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
        :maxlength="MAX_QUESTION_LENGTH"
        placeholder="输入规范问题，Enter 发送"
        :disabled="loading"
        :aria-describedby="'composer-limit'"
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
    <div class="composer-meta">
      <span v-if="error" class="composer-error">{{ error }}</span>
      <span v-else class="composer-guidance">支持多行输入，Shift + Enter 换行</span>
      <span
        id="composer-limit"
        class="composer-limit"
        :class="{ 'near-limit': nearLimit }"
      >
        {{ text.length }} / {{ MAX_QUESTION_LENGTH }}
      </span>
    </div>
  </footer>
</template>
