<script setup>
import {
  ArrowLeft,
  BarChart3,
  Clock3,
  Eye,
  LockKeyhole,
  LogOut,
  MessageSquareText,
  MousePointerClick,
  RefreshCw,
  Route,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
  Users,
} from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const AUTH_STORAGE_KEY = 'guibao_feedback_dashboard_auth'

const username = ref('')
const password = ref('')
const authHeader = ref('')
const dashboard = ref(null)
const loading = ref(false)
const error = ref('')

const reasonLabels = {
  answer_inaccurate: '答案不准确',
  source_mismatch: '来源不匹配',
  wrong_clause: '引用条款错误',
  incomplete: '答案不完整',
  missing_content: '未收录相关内容',
  misclassified: '问题被误分类',
  hard_to_read: '格式不易阅读',
  other: '其他',
}

const intentLabels = {
  standard_number: '按编号查',
  standard_name: '按名称查',
  term: '术语查询',
  numeric: '数值查询',
  scenario: '场景查询',
  comparison: '对比查询',
  material: '材料查询',
  version: '版本查询',
  colloquial: '模糊口语',
  chitchat: '闲聊问候',
  fallback: '未覆盖问题',
  outside_region: '中国大陆以外',
}

const trendMax = computed(() => {
  if (!dashboard.value) return 1
  return Math.max(1, ...dashboard.value.trend.map((item) => item.total))
})

const reasonMax = computed(() => {
  if (!dashboard.value) return 1
  return Math.max(1, ...dashboard.value.reasons.map((item) => item.count))
})

const intentMax = computed(() => {
  if (!dashboard.value) return 1
  return Math.max(1, ...dashboard.value.intents.map((item) => item.count))
})

const analytics = computed(() => dashboard.value?.analytics || null)

const trafficMax = computed(() => {
  if (!analytics.value) return 1
  return Math.max(
    1,
    ...analytics.value.trend.map((item) =>
      Math.max(item.pv, item.questions, item.answers),
    ),
  )
})

const funnelSteps = computed(() => {
  if (!analytics.value) return []
  const summary = analytics.value.summary
  const pvBase = Math.max(1, summary.pv)
  return [
    { label: '页面访问 PV', value: summary.pv, rate: 100 },
    {
      label: '发起提问',
      value: summary.questions,
      rate: Math.round(summary.questions / pvBase * 1000) / 10,
    },
    {
      label: '回答完成',
      value: summary.answers,
      rate: Math.round(summary.answers / pvBase * 1000) / 10,
    },
    {
      label: '提交反馈',
      value: summary.feedback_submits,
      rate: Math.round(summary.feedback_submits / pvBase * 1000) / 10,
    },
  ]
})

function encodeBasicAuth(user, pass) {
  const bytes = new TextEncoder().encode(`${user}:${pass}`)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return `Basic ${window.btoa(binary)}`
}

function clearAuthentication() {
  authHeader.value = ''
  dashboard.value = null
  sessionStorage.removeItem(AUTH_STORAGE_KEY)
}

async function loadDashboard(auth, quiet = false) {
  if (!auth || loading.value) return
  loading.value = true
  if (!quiet) error.value = ''
  try {
    dashboard.value = await api.feedbackDashboard(auth)
    authHeader.value = auth
    sessionStorage.setItem(AUTH_STORAGE_KEY, auth)
  } catch (loadError) {
    const message = loadError.message || ''
    if (message.includes('401') || message.includes('用户名或密码错误')) {
      clearAuthentication()
      error.value = '用户名或密码错误'
    } else {
      error.value = '看板数据加载失败，请稍后重试'
    }
  } finally {
    loading.value = false
  }
}

async function login() {
  const user = username.value.trim()
  if (!user || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  const auth = encodeBasicAuth(user, password.value)
  await loadDashboard(auth)
  if (dashboard.value) {
    username.value = ''
    password.value = ''
  }
}

function logout() {
  clearAuthentication()
  error.value = ''
}

function refresh() {
  if (authHeader.value) loadDashboard(authHeader.value)
}

function barHeight(value) {
  if (!value) return '3px'
  return `${Math.max(8, Math.round(value / trendMax.value * 100))}%`
}

function trafficBarHeight(value) {
  if (!value) return '3px'
  return `${Math.max(8, Math.round(value / trafficMax.value * 100))}%`
}

function funnelWidth(value) {
  return `${Math.max(4, Math.round(value))}%`
}

function relativeWidth(value, maximum) {
  return `${Math.max(4, Math.round(value / maximum.value * 100))}%`
}

function formatTime(value) {
  if (!value) return '时间未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

onMounted(() => {
  const saved = sessionStorage.getItem(AUTH_STORAGE_KEY)
  if (saved) loadDashboard(saved, true)
})
</script>

<template>
  <div class="feedback-dashboard">
    <header class="dashboard-header">
      <div class="dashboard-brand">
        <span class="dashboard-brand-mark"><BarChart3 :size="19" /></span>
        <div>
          <strong>规宝</strong>
          <span>反馈数据看板</span>
        </div>
      </div>
      <div class="dashboard-header-actions">
        <a class="dashboard-nav-link" href="/">
          <ArrowLeft :size="15" />
          返回问答
        </a>
        <button
          v-if="dashboard"
          class="dashboard-ghost-button"
          type="button"
          @click="logout"
        >
          <LogOut :size="15" />
          退出
        </button>
      </div>
    </header>

    <main class="dashboard-content">
      <section v-if="!dashboard" class="dashboard-login-card">
        <span class="dashboard-lock"><LockKeyhole :size="24" /></span>
        <h1>反馈数据看板</h1>
        <p>请输入管理员账号，查看用户反馈和使用质量。</p>
        <form class="dashboard-login-form" @submit.prevent="login">
          <label>
            <span>用户名</span>
            <input
              v-model="username"
              type="text"
              name="username"
              autocomplete="username"
              placeholder="请输入用户名"
              :disabled="loading"
            />
          </label>
          <label>
            <span>密码</span>
            <input
              v-model="password"
              type="password"
              name="password"
              autocomplete="current-password"
              placeholder="请输入密码"
              :disabled="loading"
            />
          </label>
          <button class="dashboard-login-button" type="submit" :disabled="loading">
            {{ loading ? '验证中…' : '进入看板' }}
          </button>
          <p v-if="error" class="dashboard-error">{{ error }}</p>
        </form>
      </section>

      <template v-else>
        <section class="dashboard-title-row">
          <div>
            <p class="dashboard-eyebrow">FEEDBACK INSIGHTS</p>
            <h1>问答反馈概览</h1>
            <p class="dashboard-subtitle">
              数据更新于 {{ formatTime(dashboard.generated_at) }}
            </p>
          </div>
          <button
            class="dashboard-refresh-button"
            type="button"
            :disabled="loading"
            @click="refresh"
          >
            <RefreshCw :size="16" :class="{ spinning: loading }" />
            {{ loading ? '刷新中' : '刷新数据' }}
          </button>
        </section>

        <p v-if="error" class="dashboard-error">{{ error }}</p>

        <div class="dashboard-group-heading">
          <div>
            <h2>流量与问答</h2>
            <p>统计最近 14 天内的匿名访问和问答转化</p>
          </div>
          <span>PV / UV / Session</span>
        </div>

        <section class="dashboard-stat-grid">
          <article class="dashboard-stat-card">
            <span class="stat-icon accent"><Eye :size="20" /></span>
            <p>页面浏览量 PV</p>
            <strong>{{ analytics.summary.pv }}</strong>
            <small>每次问答页加载计一次</small>
          </article>
          <article class="dashboard-stat-card">
            <span class="stat-icon neutral"><Users :size="20" /></span>
            <p>独立访客 UV</p>
            <strong>{{ analytics.summary.uv }}</strong>
            <small>按匿名访客 ID 去重</small>
          </article>
          <article class="dashboard-stat-card">
            <span class="stat-icon positive"><MousePointerClick :size="20" /></span>
            <p>访问会话数</p>
            <strong>{{ analytics.summary.sessions }}</strong>
            <small>{{ analytics.summary.questions }} 次问题提交</small>
          </article>
          <article class="dashboard-stat-card">
            <span class="stat-icon neutral"><TrendingUp :size="20" /></span>
            <p>回答完成率</p>
            <strong>{{ analytics.summary.answer_rate }}%</strong>
            <small>
              {{ analytics.summary.answers }} 次完成 ·
              {{ analytics.summary.answer_errors }} 次失败
            </small>
          </article>
        </section>

        <section class="dashboard-traffic-grid">
          <article class="dashboard-panel">
            <div class="dashboard-panel-heading">
              <div>
                <h2>流量与提问趋势</h2>
                <p>每天 PV、UV 与问题提交量</p>
              </div>
              <div class="dashboard-legend">
                <span><i class="legend-dot pv"></i>PV</span>
                <span><i class="legend-dot questions"></i>提问</span>
                <span><i class="legend-dot uv"></i>UV</span>
              </div>
            </div>
            <div class="traffic-chart">
              <div
                v-for="point in analytics.trend"
                :key="point.date"
                class="traffic-column"
                :title="`${point.date}：PV ${point.pv}，UV ${point.uv}，提问 ${point.questions}`"
              >
                <span class="traffic-total">{{ point.pv || '' }}</span>
                <div class="traffic-track">
                  <span
                    class="traffic-bar pv"
                    :style="{ height: trafficBarHeight(point.pv) }"
                  ></span>
                  <span
                    class="traffic-bar questions"
                    :style="{ height: trafficBarHeight(point.questions) }"
                  ></span>
                </div>
                <span class="traffic-uv">{{ point.uv ? `UV ${point.uv}` : '' }}</span>
                <span class="trend-date">{{ point.date }}</span>
              </div>
            </div>
          </article>

          <article class="dashboard-panel">
            <div class="dashboard-panel-heading">
              <div>
                <h2>问答转化漏斗</h2>
                <p>从页面访问到反馈提交的转化情况</p>
              </div>
              <span class="funnel-icon"><Route :size="18" /></span>
            </div>
            <div class="funnel-list">
              <div v-for="step in funnelSteps" :key="step.label" class="funnel-row">
                <div class="funnel-label">
                  <span>{{ step.label }}</span>
                  <strong>{{ step.value }}</strong>
                </div>
                <div class="funnel-track">
                  <span
                    class="funnel-fill"
                    :style="{ width: funnelWidth(step.rate) }"
                  ></span>
                </div>
                <small>{{ step.rate }}%</small>
              </div>
            </div>
            <div class="dashboard-inline-metrics">
              <span>打开原文 {{ analytics.summary.source_opens }}</span>
              <span>反馈转化 {{ analytics.summary.feedback_rate }}%</span>
            </div>
          </article>
        </section>

        <div class="dashboard-group-heading">
          <div>
            <h2>反馈质量</h2>
            <p>回答满意度与需要复核的负反馈</p>
          </div>
        </div>

        <section class="dashboard-stat-grid">
          <article class="dashboard-stat-card">
            <span class="stat-icon neutral"><MessageSquareText :size="20" /></span>
            <p>反馈总数</p>
            <strong>{{ dashboard.summary.total }}</strong>
            <small>{{ dashboard.summary.users }} 位用户参与</small>
          </article>
          <article class="dashboard-stat-card">
            <span class="stat-icon positive"><ThumbsUp :size="20" /></span>
            <p>有帮助</p>
            <strong>{{ dashboard.summary.helpful }}</strong>
            <small>{{ dashboard.summary.helpful_rate }}% 好评率</small>
          </article>
          <article class="dashboard-stat-card">
            <span class="stat-icon negative"><ThumbsDown :size="20" /></span>
            <p>没帮助</p>
            <strong>{{ dashboard.summary.not_helpful }}</strong>
            <small>需要优先复核的反馈</small>
          </article>
          <article class="dashboard-stat-card">
            <span class="stat-icon accent"><Users :size="20" /></span>
            <p>近 14 天反馈</p>
            <strong>
              {{ dashboard.trend.reduce((sum, item) => sum + item.total, 0) }}
            </strong>
            <small>按反馈创建日期统计</small>
          </article>
        </section>

        <section class="dashboard-panel dashboard-trend-panel">
          <div class="dashboard-panel-heading">
            <div>
              <h2>反馈趋势</h2>
              <p>最近 14 天的有帮助与没帮助变化</p>
            </div>
            <div class="dashboard-legend">
              <span><i class="legend-dot helpful"></i>有帮助</span>
              <span><i class="legend-dot negative"></i>没帮助</span>
            </div>
          </div>
          <div class="trend-chart">
            <div
              v-for="point in dashboard.trend"
              :key="point.date"
              class="trend-column"
              :title="`${point.date}：有帮助 ${point.helpful}，没帮助 ${point.not_helpful}`"
            >
              <span class="trend-count">{{ point.total || '' }}</span>
              <div class="trend-track">
                <div
                  class="trend-bar"
                  :class="{ empty: !point.total }"
                  :style="{ height: barHeight(point.total) }"
                >
                  <span
                    v-if="point.helpful"
                    class="trend-segment helpful"
                    :style="{ flex: point.helpful }"
                  ></span>
                  <span
                    v-if="point.not_helpful"
                    class="trend-segment negative"
                    :style="{ flex: point.not_helpful }"
                  ></span>
                </div>
              </div>
              <span class="trend-date">{{ point.date }}</span>
            </div>
          </div>
        </section>

        <section class="dashboard-analysis-grid">
          <article class="dashboard-panel">
            <div class="dashboard-panel-heading">
              <div>
                <h2>负反馈原因</h2>
                <p>按用户选择的问题标签统计</p>
              </div>
            </div>
            <div v-if="dashboard.reasons.length" class="breakdown-list">
              <div v-for="item in dashboard.reasons" :key="item.name" class="breakdown-row">
                <div class="breakdown-label">
                  <span>{{ reasonLabels[item.name] || item.name }}</span>
                  <strong>{{ item.count }}</strong>
                </div>
                <div class="breakdown-track">
                  <span
                    class="breakdown-fill reason"
                    :style="{ width: relativeWidth(item.count, reasonMax) }"
                  ></span>
                </div>
              </div>
            </div>
            <p v-else class="dashboard-empty">暂无负反馈原因</p>
          </article>

          <article class="dashboard-panel">
            <div class="dashboard-panel-heading">
              <div>
                <h2>问题类型</h2>
                <p>反馈回答对应的意图分布</p>
              </div>
            </div>
            <div v-if="dashboard.intents.length" class="breakdown-list">
              <div v-for="item in dashboard.intents" :key="item.name" class="breakdown-row">
                <div class="breakdown-label">
                  <span>{{ intentLabels[item.name] || item.name }}</span>
                  <strong>{{ item.count }}</strong>
                </div>
                <div class="breakdown-track">
                  <span
                    class="breakdown-fill intent"
                    :style="{ width: relativeWidth(item.count, intentMax) }"
                  ></span>
                </div>
              </div>
            </div>
            <p v-else class="dashboard-empty">暂无意图分布数据</p>
          </article>
        </section>

        <section class="dashboard-panel dashboard-question-panel">
          <div class="dashboard-panel-heading">
            <div>
              <h2>最近提问</h2>
              <p>最近 20 次用户问题及回答状态</p>
            </div>
          </div>
          <div v-if="analytics.recent_questions.length" class="recent-question-list">
            <article
              v-for="(item, index) in analytics.recent_questions"
              :key="`${item.created_at}-${index}`"
              class="recent-question-item"
            >
              <div class="recent-question-copy">
                <strong>{{ item.question || '未记录问题文本' }}</strong>
                <span>
                  {{ intentLabels[item.intent] || item.intent || '意图未记录' }}
                  · {{ item.source_count }} 条来源
                  <template v-if="item.latency_ms">
                    · {{ item.latency_ms }} ms
                  </template>
                </span>
              </div>
              <div class="recent-question-meta">
                <span
                  class="question-status"
                  :class="{ answered: item.status === 'answered' }"
                >
                  {{ item.status === 'answered' ? '已回答' : '已提交' }}
                </span>
                <time>{{ formatTime(item.created_at) }}</time>
              </div>
            </article>
          </div>
          <p v-else class="dashboard-empty">暂无提问埋点数据</p>
        </section>

        <section class="dashboard-panel">
          <div class="dashboard-panel-heading">
            <div>
              <h2>最近反馈</h2>
              <p>最多展示最近 30 条，问题与回答用于复核检索质量</p>
            </div>
          </div>
          <div v-if="dashboard.recent.length" class="feedback-feed">
            <article
              v-for="item in dashboard.recent"
              :key="item.id"
              class="feedback-feed-item"
            >
              <div class="feedback-feed-head">
                <span
                  class="feedback-rating"
                  :class="item.rating === 'helpful' ? 'positive' : 'negative'"
                >
                  <ThumbsUp v-if="item.rating === 'helpful'" :size="14" />
                  <ThumbsDown v-else :size="14" />
                  {{ item.rating === 'helpful' ? '有帮助' : '没帮助' }}
                </span>
                <span class="feedback-intent">
                  {{ intentLabels[item.intent] || item.intent || '意图未记录' }}
                </span>
                <span class="feedback-time">
                  <Clock3 :size="13" />
                  {{ formatTime(item.updated_at || item.created_at) }}
                </span>
              </div>
              <h3>{{ item.question || '未记录问题' }}</h3>
              <div v-if="item.reason_codes.length" class="feedback-tags">
                <span v-for="code in item.reason_codes" :key="code">
                  {{ reasonLabels[code] || code }}
                </span>
              </div>
              <p v-if="item.comment" class="feedback-comment">{{ item.comment }}</p>
              <details>
                <summary>查看回答快照</summary>
                <p>{{ item.answer || '未记录回答内容' }}</p>
              </details>
              <div class="feedback-feed-meta">
                <span>用户 {{ item.user_id || '未知' }}</span>
                <span>Trace {{ item.trace_id || '未记录' }}</span>
                <span>{{ item.kb_version || '知识库版本未记录' }}</span>
              </div>
            </article>
          </div>
          <p v-else class="dashboard-empty">还没有用户反馈</p>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.feedback-dashboard {
  height: 100%;
  overflow-y: auto;
  background:
    radial-gradient(circle at 8% 0%, rgba(15, 118, 110, 0.1), transparent 24rem),
    #f3f6f8;
  color: #17212b;
}

.dashboard-header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
  padding: 0 28px;
  border-bottom: 1px solid #dde4e9;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(14px);
}

.dashboard-brand,
.dashboard-brand > div,
.dashboard-header-actions,
.dashboard-nav-link,
.dashboard-ghost-button,
.dashboard-refresh-button,
.feedback-time,
.feedback-rating {
  display: flex;
  align-items: center;
}

.dashboard-brand {
  gap: 11px;
}

.dashboard-brand > div {
  align-items: baseline;
  gap: 9px;
}

.dashboard-brand strong {
  font-size: 17px;
}

.dashboard-brand span:last-child {
  color: #6b7785;
  font-size: 13px;
}

.dashboard-brand-mark {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 10px;
  background: #0f766e;
  color: #fff;
}

.dashboard-header-actions {
  gap: 9px;
}

.dashboard-nav-link,
.dashboard-ghost-button,
.dashboard-refresh-button {
  gap: 7px;
  height: 36px;
  padding: 0 13px;
  border: 1px solid #d8e0e6;
  border-radius: 9px;
  background: #fff;
  color: #465361;
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;
}

.dashboard-nav-link:hover,
.dashboard-ghost-button:hover {
  border-color: #0f766e;
  color: #0f766e;
}

.dashboard-content {
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto;
  padding: 38px 0 72px;
}

.dashboard-login-card {
  width: min(420px, 100%);
  margin: 9vh auto 0;
  padding: 34px;
  border: 1px solid #dde4e9;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 24px 70px rgba(24, 43, 55, 0.12);
}

.dashboard-lock {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 14px;
  background: #e6f4f2;
  color: #0f766e;
}

.dashboard-login-card h1 {
  margin: 20px 0 7px;
  font-size: 27px;
}

.dashboard-login-card > p {
  margin: 0;
  color: #6b7785;
  font-size: 14px;
}

.dashboard-login-form {
  display: grid;
  gap: 16px;
  margin-top: 28px;
}

.dashboard-login-form label {
  display: grid;
  gap: 7px;
  color: #394652;
  font-size: 13px;
  font-weight: 600;
}

.dashboard-login-form input {
  width: 100%;
  height: 44px;
  padding: 0 13px;
  border: 1px solid #d4dde4;
  border-radius: 9px;
  outline: none;
  background: #fbfcfd;
  color: #17212b;
  font: inherit;
}

.dashboard-login-form input:focus {
  border-color: #0f766e;
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12);
}

.dashboard-login-button {
  height: 44px;
  margin-top: 4px;
  border: 0;
  border-radius: 9px;
  background: #0f766e;
  color: #fff;
  font-weight: 650;
  cursor: pointer;
}

.dashboard-login-button:disabled,
.dashboard-refresh-button:disabled {
  cursor: wait;
  opacity: 0.65;
}

.dashboard-title-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
}

.dashboard-eyebrow {
  margin: 0 0 7px;
  color: #0f766e;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.16em;
}

.dashboard-title-row h1 {
  margin: 0;
  font-size: 31px;
  letter-spacing: -0.03em;
}

.dashboard-subtitle {
  margin: 8px 0 0;
  color: #6b7785;
  font-size: 13px;
}

.dashboard-refresh-button {
  height: 40px;
  border-color: #0f766e;
  color: #0f766e;
}

.spinning {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.dashboard-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.dashboard-stat-card,
.dashboard-panel {
  border: 1px solid #dde4e9;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 8px 26px rgba(29, 48, 61, 0.05);
}

.dashboard-stat-card {
  position: relative;
  min-height: 160px;
  padding: 20px;
  border-radius: 15px;
}

.stat-icon {
  position: absolute;
  top: 18px;
  right: 18px;
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 11px;
}

.stat-icon.neutral {
  background: #eef2f5;
  color: #53616e;
}

.stat-icon.positive {
  background: #e8f5ed;
  color: #18794e;
}

.stat-icon.negative {
  background: #fef0ef;
  color: #b42318;
}

.stat-icon.accent {
  background: #e6f4f2;
  color: #0f766e;
}

.dashboard-stat-card p {
  margin: 0;
  color: #6b7785;
  font-size: 13px;
}

.dashboard-stat-card strong {
  display: block;
  margin-top: 16px;
  font-size: 34px;
  line-height: 1;
}

.dashboard-stat-card small {
  display: block;
  margin-top: 12px;
  color: #8994a0;
  font-size: 12px;
}

.dashboard-panel {
  padding: 22px;
  border-radius: 16px;
}

.dashboard-trend-panel {
  margin-bottom: 16px;
}

.dashboard-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
}

.dashboard-panel-heading h2 {
  margin: 0;
  font-size: 17px;
}

.dashboard-panel-heading p {
  margin: 6px 0 0;
  color: #7a8692;
  font-size: 12px;
}

.dashboard-legend {
  display: flex;
  align-items: center;
  gap: 14px;
  color: #697582;
  font-size: 12px;
}

.dashboard-legend span {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-dot.helpful,
.trend-segment.helpful {
  background: #2a9d68;
}

.legend-dot.negative,
.trend-segment.negative {
  background: #dc5a4e;
}

.trend-chart {
  display: grid;
  grid-template-columns: repeat(14, minmax(24px, 1fr));
  gap: 9px;
  height: 210px;
  padding-top: 12px;
}

.trend-column {
  display: grid;
  grid-template-rows: 18px 1fr 22px;
  min-width: 0;
  text-align: center;
}

.trend-count {
  color: #6b7785;
  font-size: 10px;
}

.trend-track {
  display: flex;
  align-items: flex-end;
  height: 100%;
  border-radius: 5px;
  background: linear-gradient(to top, #f2f5f7 1px, transparent 1px) 0 0 / 100% 25%;
}

.trend-bar {
  display: flex;
  width: 100%;
  max-width: 34px;
  min-height: 3px;
  margin: 0 auto;
  overflow: hidden;
  border-radius: 5px 5px 2px 2px;
  background: #e7ecef;
}

.trend-bar.empty {
  opacity: 0.75;
}

.trend-segment {
  min-width: 2px;
}

.trend-date {
  padding-top: 7px;
  color: #8b96a1;
  font-size: 10px;
  white-space: nowrap;
}

.dashboard-analysis-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.breakdown-list {
  display: grid;
  gap: 15px;
}

.breakdown-label {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 7px;
  color: #4c5965;
  font-size: 12px;
}

.breakdown-label strong {
  color: #26323d;
}

.breakdown-track {
  height: 7px;
  overflow: hidden;
  border-radius: 99px;
  background: #edf1f3;
}

.breakdown-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.breakdown-fill.reason {
  background: #dc5a4e;
}

.breakdown-fill.intent {
  background: #23857c;
}

.feedback-feed {
  display: grid;
  gap: 12px;
}

.feedback-feed-item {
  padding: 18px;
  border: 1px solid #e4e9ed;
  border-radius: 13px;
  background: #fbfcfd;
}

.feedback-feed-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.feedback-rating,
.feedback-intent,
.feedback-tags span {
  border-radius: 999px;
  font-size: 11px;
  font-weight: 650;
}

.feedback-rating {
  gap: 5px;
  padding: 5px 9px;
}

.feedback-rating.positive {
  background: #e8f5ed;
  color: #18794e;
}

.feedback-rating.negative {
  background: #fef0ef;
  color: #b42318;
}

.feedback-intent {
  padding: 5px 9px;
  background: #edf2f5;
  color: #52606c;
}

.feedback-time {
  gap: 5px;
  margin-left: auto;
  color: #8994a0;
  font-size: 11px;
}

.feedback-feed-item h3 {
  margin: 14px 0 9px;
  font-size: 15px;
  line-height: 1.55;
}

.feedback-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.feedback-tags span {
  padding: 4px 8px;
  background: #fff2ed;
  color: #a9432f;
}

.feedback-comment {
  margin: 9px 0;
  padding: 10px 12px;
  border-left: 3px solid #dc5a4e;
  background: #fff7f5;
  color: #5c4a45;
  font-size: 13px;
  line-height: 1.6;
}

.feedback-feed-item details {
  color: #52606c;
  font-size: 12px;
}

.feedback-feed-item summary {
  cursor: pointer;
}

.feedback-feed-item details p {
  margin: 10px 0 0;
  white-space: pre-wrap;
  line-height: 1.7;
}

.feedback-feed-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 13px;
  color: #96a0aa;
  font-size: 10px;
}

.dashboard-empty {
  margin: 8px 0;
  padding: 28px 0;
  color: #8994a0;
  text-align: center;
  font-size: 13px;
}

.dashboard-error {
  margin: 10px 0 0;
  padding: 9px 11px;
  border-radius: 8px;
  background: #fef0ef;
  color: #b42318;
  font-size: 12px;
}

.dashboard-group-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin: 28px 2px 13px;
}

.dashboard-group-heading h2 {
  margin: 0;
  font-size: 18px;
}

.dashboard-group-heading p {
  margin: 5px 0 0;
  color: #7a8692;
  font-size: 12px;
}

.dashboard-group-heading > span {
  color: #9aa4ae;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
}

.dashboard-traffic-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.75fr) minmax(280px, 0.85fr);
  gap: 16px;
  margin-bottom: 16px;
}

.legend-dot.pv,
.traffic-bar.pv {
  background: #0f766e;
}

.legend-dot.questions,
.traffic-bar.questions {
  background: #d58a2c;
}

.legend-dot.uv {
  background: #4f6d8c;
}

.traffic-chart {
  display: grid;
  grid-template-columns: repeat(14, minmax(22px, 1fr));
  gap: 6px;
  height: 230px;
  padding-top: 4px;
}

.traffic-column {
  display: grid;
  grid-template-rows: 17px 1fr 15px 20px;
  min-width: 0;
  text-align: center;
}

.traffic-total,
.traffic-uv {
  color: #7d8995;
  font-size: 9px;
}

.traffic-track {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 3px;
  height: 100%;
  border-bottom: 1px solid #e4e9ed;
  background: linear-gradient(to top, #f2f5f7 1px, transparent 1px) 0 0 / 100% 25%;
}

.traffic-bar {
  display: block;
  width: 9px;
  min-height: 3px;
  border-radius: 3px 3px 0 0;
  opacity: 0.92;
}

.traffic-bar.questions {
  width: 6px;
}

.funnel-icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 10px;
  background: #e6f4f2;
  color: #0f766e;
}

.funnel-list {
  display: grid;
  gap: 16px;
}

.funnel-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 50px;
  gap: 5px 10px;
}

.funnel-label {
  grid-column: 1 / -1;
  display: flex;
  justify-content: space-between;
  color: #4e5b67;
  font-size: 12px;
}

.funnel-label strong {
  color: #17212b;
}

.funnel-track {
  height: 9px;
  overflow: hidden;
  border-radius: 99px;
  background: #edf1f3;
}

.funnel-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0f766e, #42a39b);
}

.funnel-row small {
  color: #7e8a96;
  font-size: 10px;
  text-align: right;
}

.dashboard-inline-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
}

.dashboard-inline-metrics span {
  padding: 5px 8px;
  border-radius: 999px;
  background: #f1f5f7;
  color: #667380;
  font-size: 10px;
}

.dashboard-question-panel {
  margin-bottom: 16px;
}

.recent-question-list {
  display: grid;
  gap: 9px;
}

.recent-question-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 14px;
  border: 1px solid #e6ebef;
  border-radius: 11px;
  background: #fbfcfd;
}

.recent-question-copy {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.recent-question-copy strong {
  overflow: hidden;
  color: #27333e;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-question-copy span,
.recent-question-meta time {
  color: #8994a0;
  font-size: 10px;
}

.recent-question-meta {
  display: flex;
  align-items: center;
  flex: none;
  gap: 9px;
}

.question-status {
  padding: 4px 7px;
  border-radius: 99px;
  background: #fff2df;
  color: #a45d12;
  font-size: 10px;
  font-weight: 650;
}

.question-status.answered {
  background: #e8f5ed;
  color: #18794e;
}

@media (max-width: 900px) {
  .dashboard-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .dashboard-analysis-grid {
    grid-template-columns: 1fr;
  }

  .dashboard-traffic-grid {
    grid-template-columns: 1fr;
  }

  .trend-chart {
    gap: 4px;
  }
}

@media (max-width: 620px) {
  .dashboard-header {
    padding: 0 16px;
  }

  .dashboard-brand span:last-child {
    display: none;
  }

  .dashboard-content {
    width: calc(100% - 24px);
    padding-top: 24px;
  }

  .dashboard-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .dashboard-title-row h1 {
    font-size: 26px;
  }

  .dashboard-stat-grid {
    grid-template-columns: 1fr;
  }

  .dashboard-stat-card {
    min-height: 140px;
  }

  .dashboard-panel {
    padding: 17px;
  }

  .dashboard-legend {
    display: none;
  }

  .trend-chart {
    grid-template-columns: repeat(14, 34px);
    overflow-x: auto;
  }

  .feedback-time {
    width: 100%;
    margin-left: 0;
  }

  .recent-question-item {
    align-items: flex-start;
    flex-direction: column;
    gap: 9px;
  }

  .recent-question-meta {
    justify-content: space-between;
    width: 100%;
  }

  .traffic-chart {
    grid-template-columns: repeat(14, 34px);
    overflow-x: auto;
  }
}
</style>
