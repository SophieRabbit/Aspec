<script setup>
import { Bot, Database } from 'lucide-vue-next'
import { ref } from 'vue'
import { highlightKeywords, linkifyUrls, richText } from '../lib/format'
import ReasoningTrace from './ReasoningTrace.vue'
import SourceCard from './SourceCard.vue'

defineProps({
  message: { type: Object, required: true },
})

defineEmits(['follow-up', 'view-source'])

const expanded = ref(false)
const feedbackSent = ref(false)
</script>

<template>
  <article class="message-row" :class="message.role">
    <div v-if="message.role === 'assistant'" class="message-avatar">
      <Bot :size="17" />
    </div>
    <div class="message-body">
      <div v-if="message.role === 'assistant' && message.region_path?.length" class="region-path">
        <template v-for="(item, index) in message.region_path" :key="index">
          <span class="region-path-item" :class="{ missing: !item.available }">
            <span>{{ item.level }}</span>
            <span class="region-path-state">{{ item.available ? `${item.count} 部` : '未收录' }}</span>
          </span>
          <span v-if="index < message.region_path.length - 1" class="region-path-arrow">→</span>
        </template>
      </div>
      <div
        v-if="message.role === 'assistant'"
        class="message-content"
        v-html="highlightKeywords(linkifyUrls(richText(message.content)), message.keywords || [])"
      ></div>
      <div v-else class="user-bubble">{{ message.content }}</div>

      <ReasoningTrace v-if="message.reasoning?.length" :steps="message.reasoning" />

      <div v-if="message.sources?.length" class="source-section">
        <div class="section-label">规范出处</div>
        <div class="source-grid">
          <SourceCard
            v-for="(source, index) in expanded ? message.sources : message.sources.slice(0, 3)"
            :key="index"
            :source="source"
            @open="$emit('view-source', source)"
          />
        </div>
        <button
          v-if="message.sources.length > 3"
          class="source-more-button"
          type="button"
          @click="expanded = !expanded"
        >
          {{ expanded ? '收起' : `查看更多（${message.sources.length - 3}）` }}
        </button>
      </div>

      <div v-if="message.follow_ups?.length" class="followup-section">
        <div class="section-label">延伸问题</div>
        <div class="followup-list">
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

      <div v-if="message.memory" class="memory-note">
        <Database :size="13" />
        <span>记忆上下文 {{ message.memory.token_estimate }}/{{ message.memory.budget }} tokens · {{ message.memory.recent_messages }} 条近期消息</span>
      </div>
      <button
        v-if="message.role === 'assistant'"
        class="feedback-button"
        type="button"
        :disabled="feedbackSent"
        @click="feedbackSent = true; $emit('feedback', { trace_id: message.trace_id, actual_reply: message.content })"
      >
        {{ feedbackSent ? '已反馈' : '标记不准确' }}
      </button>
    </div>
  </article>
</template>
