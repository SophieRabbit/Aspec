<script setup>
import { Bot } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { highlightKeywords, linkifyUrls, richText } from '../lib/format'
import IntentTrace from './IntentTrace.vue'

const props = defineProps({
  message: { type: Object, required: true },
})

defineEmits(['follow-up', 'view-source', 'view-detail'])

const followupsOpen = ref(false)
const showIntentTrace =
  import.meta.env.DEV || import.meta.env.VITE_SHOW_INTENT_TRACE === 'true'

const searchGroups = computed(() => {
  const groups = new Map()
  for (const item of props.message.search_items || []) {
    const level = item.level || '相关规范'
    if (!groups.has(level)) groups.set(level, [])
    groups.get(level).push(item)
  }
  return [...groups.entries()].map(([level, items]) => ({ level, items }))
})
</script>

<template>
  <article class="message-row" :class="message.role">
    <div v-if="message.role === 'assistant'" class="message-avatar">
      <Bot :size="17" />
    </div>
    <div class="message-body">
      <div v-if="message.role === 'user'" class="user-bubble">{{ message.content }}</div>

      <IntentTrace
        v-if="showIntentTrace && message.intent"
        :intent="message.intent"
        :label="message.intent_label"
        :source="message.intent_source"
        :confidence="message.intent_confidence"
        :alias="message.intent_alias"
      />

      <div v-if="searchGroups.length" class="search-section">
        <template v-for="group in searchGroups" :key="group.level">
          <div class="search-group-title">【{{ group.level }}】</div>
          <table class="search-table">
            <thead>
              <tr>
                <th>规范编号</th>
                <th>规范名称</th>
                <th>状态</th>
                <th>实施日期</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in group.items" :key="item.doc_id">
                <td>{{ item.standard }}</td>
                <td>{{ item.title }}</td>
                <td>{{ item.status }}</td>
                <td>{{ item.effective_date }}</td>
                <td>
                  <button
                    class="search-detail-link"
                    type="button"
                    @click="$emit('view-detail', { doc_id: item.doc_id })"
                  >
                    点击查看详情 →
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>

      <div
        v-if="message.role === 'assistant'"
        class="message-content"
        v-html="highlightKeywords(linkifyUrls(richText(message.content)), message.keywords || [])"
      ></div>

      <div v-if="message.follow_ups?.length" class="followup-section">
        <button
          class="followup-toggle"
          :class="{ open: followupsOpen }"
          type="button"
          @click="followupsOpen = !followupsOpen"
        >
          💡 你可能还想问
          <span class="followup-chevron">▼</span>
        </button>
        <Transition name="followup">
          <div v-if="followupsOpen" class="followup-list">
            <button
              v-for="(item, index) in message.follow_ups"
              :key="index"
              class="followup-button"
              type="button"
              @click="$emit('follow-up', item)"
            >
              {{ item }}
            </button>
          </div>
        </Transition>
      </div>

      <div v-if="message.recommendations?.length" class="recommendation-section">
        <div class="section-label">
          <span>相关规范推荐</span>
          <span class="recommendation-note">未收录，可自行查找</span>
        </div>
        <div
          v-for="(group, groupIndex) in message.recommendations"
          :key="groupIndex"
          class="recommendation-group"
        >
          <div class="recommendation-category">{{ group.category }}</div>
          <ul class="recommendation-list">
            <li v-for="(item, itemIndex) in group.items" :key="itemIndex">
              <span class="recommendation-code">{{ item.code }}</span>
              {{ item.title }}
            </li>
          </ul>
        </div>
      </div>

      <div v-if="message.web_results?.length || message.web_note" class="web-section">
        <div class="section-label">
          <span>网络检索结果</span>
          <span class="recommendation-note">来源于网络搜索，请核实</span>
        </div>
        <a
          v-for="(item, index) in message.web_results"
          :key="index"
          class="web-result-item"
          :href="item.url"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ item.title }}
        </a>
        <div v-if="!message.web_results?.length && message.web_note" class="web-unavailable">
          {{ message.web_note }}
        </div>
      </div>

    </div>
  </article>
</template>
