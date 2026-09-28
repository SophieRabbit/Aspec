<script setup>
import { BookOpen, LoaderCircle, MapPin, X } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { isMarkdownTableLine, markdownTableToHtml } from '../lib/format'

const props = defineProps({
  docId: { type: String, required: true },
  query: { type: String, default: '' },
  article: { type: String, default: '' },
  page: { type: Number, default: null },
})

defineEmits(['close'])

const detail = ref(null)
const loading = ref(true)
const error = ref('')

function docTableHtml(block) {
  return markdownTableToHtml(block, {
    tableClass: 'doc-table',
    allowHtml: true,
  })
}

function docContentBlocks(htmlText) {
  const blocks = []
  let tableBuffer = []
  const flushTable = () => {
    if (tableBuffer.length) {
      blocks.push({ type: 'table', html: docTableHtml(tableBuffer.join('\n')) })
      tableBuffer = []
    }
  }
  for (const line of String(htmlText || '').split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    if (isMarkdownTableLine(trimmed)) {
      tableBuffer.push(trimmed)
    } else {
      flushTable()
      blocks.push({ type: 'paragraph', html: trimmed })
    }
  }
  flushTable()
  return blocks
}

onMounted(async () => {
  try {
    detail.value = await api.specDetail(
      props.docId,
      props.query,
      props.article,
      props.page,
    )
  } catch (requestError) {
    error.value = requestError.message || '规范详情加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <section class="document-modal">
      <header class="modal-header">
        <div class="modal-title-block">
          <div class="modal-badges">
            <span class="modal-badge">{{ detail?.document_type || '规范' }}</span>
            <span class="modal-region">
              <MapPin :size="12" />
              {{ detail?.region || '' }}
            </span>
          </div>
          <h2>{{ detail?.standard || '' }}</h2>
          <p>{{ detail?.title || '' }}</p>
          <p class="modal-status">
            {{ detail?.status || '' }}
            <span v-if="detail?.effective_date"> · {{ detail.effective_date }} 实施</span>
          </p>
        </div>
        <div class="modal-header-actions">
          <button class="icon-button" type="button" title="关闭" @click="$emit('close')">
            <X :size="18" />
          </button>
        </div>
      </header>

      <div class="modal-body">
        <div v-if="loading" class="modal-state">
          <LoaderCircle :size="22" class="spin" />
          <span>正在加载规范详情</span>
        </div>
        <div v-else-if="error" class="modal-state modal-error">{{ error }}</div>
        <div v-else-if="!detail?.snippets?.length" class="modal-state">
          <BookOpen :size="22" />
          <span>未找到与当前问题直接相关的原文段落</span>
        </div>
        <div
          v-if="detail?.matched === false && detail?.snippets?.length"
          class="modal-note"
        >
          当前问题未直接命中该规范，以下为该规范部分正文
        </div>
        <article
          v-for="(snippet, index) in detail?.snippets"
          :key="index"
          class="doc-match"
        >
          <div class="doc-match-meta">
            <span v-if="snippet.chapter">{{ snippet.chapter }}</span>
            <span v-if="snippet.article">{{ snippet.article }}</span>
            <span v-if="snippet.book_page || snippet.page">
              第 {{ snippet.book_page || snippet.page }} 页
              <span v-if="snippet.book_page && snippet.book_page !== snippet.page">
                （PDF 第 {{ snippet.page }} 页）
              </span>
            </span>
          </div>
          <template
            v-for="(block, paragraphIndex) in docContentBlocks(snippet.text)"
            :key="paragraphIndex"
          >
            <div
              v-if="block.type === 'table'"
              class="doc-table-wrap"
              v-html="block.html"
            ></div>
            <p v-else v-html="block.html"></p>
          </template>
        </article>
      </div>
    </section>
  </div>
</template>
