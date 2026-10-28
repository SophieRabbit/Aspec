<script setup>
import { Check, MessageSquareWarning, Send, ThumbsDown, ThumbsUp } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { track } from '../lib/analytics'

const props = defineProps({
  message: { type: Object, required: true },
})

const reasonOptions = [
  { code: 'answer_inaccurate', label: '答案不准确' },
  { code: 'source_mismatch', label: '来源不匹配' },
  { code: 'wrong_clause', label: '引用条款错误' },
  { code: 'incomplete', label: '答案不完整' },
  { code: 'missing_content', label: '未收录相关内容' },
  { code: 'misclassified', label: '问题被误分类' },
  { code: 'hard_to_read', label: '格式不易阅读' },
  { code: 'other', label: '其他' },
]

const submitted = ref(props.message.feedback || null)
const editing = ref(false)
const formOpen = ref(false)
const selectedReasons = ref([...(props.message.feedback?.reason_codes || [])])
const comment = ref(props.message.feedback?.comment || '')
const submitting = ref(false)
const error = ref('')

const submittedText = computed(() => {
  if (!submitted.value) return ''
  return submitted.value.rating === 'helpful' ? '已反馈：有帮助' : '已反馈：没帮助'
})

watch(
  () => props.message.feedback,
  (value) => {
    submitted.value = value || null
  },
)

function toggleReason(code) {
  if (selectedReasons.value.includes(code)) {
    selectedReasons.value = selectedReasons.value.filter((item) => item !== code)
  } else {
    selectedReasons.value = [...selectedReasons.value, code]
  }
}

function openNegativeFeedback() {
  error.value = ''
  formOpen.value = true
}

function editFeedback() {
  selectedReasons.value = [...(submitted.value?.reason_codes || [])]
  comment.value = submitted.value?.comment || ''
  editing.value = true
  formOpen.value = false
  error.value = ''
}

function cancelFeedback() {
  formOpen.value = false
  editing.value = false
  error.value = ''
}

async function submitFeedback(rating) {
  if (submitting.value) return
  if (
    rating === 'not_helpful' &&
    !selectedReasons.value.length &&
    !comment.value.trim()
  ) {
    error.value = '请选择至少一个问题标签，或填写补充说明'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const result = await api.submitFeedback({
      conversation_id: props.message.conversation_id,
      message_id: String(props.message.message_id || props.message.id || ''),
      trace_id: props.message.trace_id || '',
      rating,
      reason_codes: rating === 'helpful' ? [] : selectedReasons.value,
      comment: rating === 'helpful' ? '' : comment.value.trim(),
    })
    submitted.value = result
    formOpen.value = false
    editing.value = false
    track(
      'feedback_submit',
      {
        rating,
        reason_codes: rating === 'helpful' ? [] : selectedReasons.value,
        has_comment: rating === 'not_helpful' && Boolean(comment.value.trim()),
      },
      {
        conversationId: props.message.conversation_id,
        messageId: props.message.message_id || props.message.id,
        traceId: props.message.trace_id,
      },
    )
  } catch (submitError) {
    error.value = submitError.message || '反馈提交失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="feedback-controls">
    <div v-if="(!submitted || editing) && !formOpen" class="feedback-prompt">
      <span>{{ submitted ? '修改反馈：' : '这个回答有帮助吗？' }}</span>
      <button
        class="feedback-rating-button"
        :class="{ selected: submitted?.rating === 'helpful' }"
        type="button"
        aria-label="这个回答有帮助"
        :disabled="submitting"
        @click="submitFeedback('helpful')"
      >
        <ThumbsUp :size="15" />
        有帮助
      </button>
      <button
        class="feedback-rating-button negative"
        :class="{ selected: submitted?.rating === 'not_helpful' }"
        type="button"
        aria-label="这个回答没有帮助"
        :disabled="submitting"
        @click="openNegativeFeedback"
      >
        <ThumbsDown :size="15" />
        没帮助
      </button>
      <button
        v-if="submitted"
        class="feedback-edit-button"
        type="button"
        :disabled="submitting"
        @click="cancelFeedback"
      >
        取消
      </button>
    </div>

    <div v-else-if="submitted && !editing && !formOpen" class="feedback-result">
      <span class="feedback-result-text">
        <Check :size="15" />
        {{ submittedText }}
      </span>
      <button class="feedback-edit-button" type="button" @click="editFeedback">
        修改反馈
      </button>
    </div>

    <div v-if="formOpen" class="feedback-form">
      <div class="feedback-form-title">
        <MessageSquareWarning :size="16" />
        <span>哪里需要改进？</span>
      </div>
      <div class="feedback-reasons">
        <button
          v-for="reason in reasonOptions"
          :key="reason.code"
          class="feedback-reason-button"
          :class="{ selected: selectedReasons.includes(reason.code) }"
          type="button"
          :aria-pressed="selectedReasons.includes(reason.code)"
          @click="toggleReason(reason.code)"
        >
          {{ reason.label }}
        </button>
      </div>
      <textarea
        v-model="comment"
        class="feedback-comment"
        maxlength="1000"
        rows="3"
        placeholder="可以补充具体问题，例如希望增加的地方标准或正确条款（选填）"
      ></textarea>
      <div class="feedback-form-footer">
        <span class="feedback-privacy-note">反馈仅用于改进规范检索</span>
        <div class="feedback-form-actions">
          <button
            class="feedback-cancel-button"
            type="button"
            :disabled="submitting"
            @click="cancelFeedback"
          >
            取消
          </button>
          <button
            class="feedback-submit-button"
            type="button"
            :disabled="submitting"
            @click="submitFeedback('not_helpful')"
          >
            <Send :size="14" />
            {{ submitting ? '提交中…' : '提交反馈' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="error" class="feedback-error">{{ error }}</div>
  </div>
</template>
