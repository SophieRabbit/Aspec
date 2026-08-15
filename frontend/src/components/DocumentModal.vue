<script setup>
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  FileText,
  LoaderCircle,
  MapPin,
  X,
} from 'lucide-vue-next'
import { computed, nextTick, onMounted, ref } from 'vue'
import { api } from '../api'
import { escapeHtml } from '../lib/format'

const props = defineProps({
  source: { type: Object, required: true },
  query: { type: String, default: '' },
})

const emit = defineEmits(['close'])

const context = ref(null)
const loading = ref(true)
const error = ref('')
const activeIndex = ref(0)

const matches = computed(() => context.value?.matches || [])

function highlight(text) {
  const cleanQuery = props.query.replace(/[？?。！!\s]/g, '')
  const terms = cleanQuery.match(/[\u4e00-\u9fff]{2,6}|[a-zA-Z0-9]+/g) || []
  const keys = []
  if (cleanQuery && text.includes(cleanQuery)) keys.push(cleanQuery)
  for (const term of terms) {
    if (term.length >= 2 && text.includes(term) && !keys.includes(term)) {
      keys.push(term)
    }
  }
  keys.sort((a, b) => b.length - a.length)

  let html = escapeHtml(text)
  for (const key of keys) {
    html = html.replaceAll(escapeHtml(key), `<mark>${escapeHtml(key)}</mark>`)
  }
  return html
}

function scrollToMatch(index) {
  activeIndex.value = index
  nextTick(() => {
    document
      .getElementById(`doc-match-${index}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function previousMatch() {
  if (!matches.value.length) return
  scrollToMatch((activeIndex.value - 1 + matches.value.length) % matches.value.length)
}

function nextMatch() {
  if (!matches.value.length) return
  scrollToMatch((activeIndex.value + 1) % matches.value.length)
}

onMounted(async () => {
  try {
    context.value = await api.documentContext(props.source.doc_id, props.query)
    if (matches.value.length) {
      scrollToMatch(0)
    }
  } catch (requestError) {
    error.value = requestError.message || '原文加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <section class="document-modal">
      <header class="modal-header">
        <div class="modal-title-block">
          <div class="modal-badges">
            <span class="modal-badge">{{ context?.document_type || source.document_type }}</span>
            <span class="modal-region">
              <MapPin :size="12" />
              {{ context?.region || source.region }}
            </span>
          </div>
          <h2>{{ context?.standard || source.standard }}</h2>
          <p>{{ context?.title || source.title }}</p>
        </div>
        <div class="modal-header-actions">
          <button class="icon-button" type="button" title="关闭" @click="emit('close')">
            <X :size="18" />
          </button>
        </div>
      </header>

      <div class="modal-toolbar">
        <div class="context-count">
          <FileText :size="14" />
          <span v-if="context">共 {{ context.total_snippets }} 段原文 · 命中 {{ matches.length }} 段</span>
          <span v-else>加载原文</span>
        </div>
        <div v-if="matches.length" class="match-nav">
          <button class="icon-button" type="button" title="上一处" @click="previousMatch">
            <ChevronUp :size="16" />
          </button>
          <span>{{ activeIndex + 1 }} / {{ matches.length }}</span>
          <button class="icon-button" type="button" title="下一处" @click="nextMatch">
            <ChevronDown :size="16" />
          </button>
        </div>
      </div>

      <div class="modal-body">
        <div v-if="loading" class="modal-state">
          <LoaderCircle :size="22" class="spin" />
          <span>正在定位原文</span>
        </div>
        <div v-else-if="error" class="modal-state modal-error">{{ error }}</div>
        <div v-else-if="!matches.length" class="modal-state">
          <BookOpen :size="22" />
          <span>未找到与当前问题直接相关的原文段落</span>
        </div>
        <article
          v-for="(match, index) in matches"
          :id="`doc-match-${index}`"
          :key="index"
          class="doc-match"
          :class="{ active: index === activeIndex }"
        >
          <div class="doc-match-meta">
            <span v-if="match.chapter">{{ match.chapter }}</span>
            <span v-if="match.article">{{ match.article }}</span>
            <span v-if="match.page">第 {{ match.page }} 页</span>
          </div>
          <p v-html="highlight(match.text)"></p>
        </article>
      </div>
    </section>
  </div>
</template>
