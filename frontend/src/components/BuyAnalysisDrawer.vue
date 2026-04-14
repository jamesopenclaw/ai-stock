<template>
  <el-drawer
    :model-value="modelValue"
    size="72%"
    :destroy-on-close="false"
    class="buy-analysis-drawer"
    @close="handleClose"
  >
    <template #header>
      <div class="drawer-header">
        <div class="header-main">
          <div class="header-title">{{ headerTitle }}</div>
          <div class="header-meta">
            <span>{{ tsCode || '-' }}</span>
            <span v-if="displayTradeDate">分析日 {{ displayTradeDate }}</span>
            <span v-if="data?.resolved_trade_date && data.resolved_trade_date !== displayTradeDate">
              实际行情日 {{ data.resolved_trade_date }}
            </span>
          </div>
          <div v-if="dateContextNotice" class="drawer-date-notice">{{ dateContextNotice }}</div>
        </div>
        <div class="header-actions">
          <el-button @click="loadData" :loading="loading">刷新</el-button>
          <el-button @click="refreshLlm" :loading="llmRefreshing" type="primary" plain>
            {{ llmRefreshing ? '正在刷新解读...' : '刷新解读' }}
          </el-button>
        </div>
      </div>
    </template>

    <div class="drawer-body">
      <el-empty v-if="!tsCode" description="请选择一只股票后再查看买点 SOP" />
      <template v-else>
        <div v-if="loadError" class="drawer-error">
          {{ loadError }}
        </div>
        <el-skeleton v-if="loading && !data" :rows="14" animated />
        <el-empty
          v-else-if="!data"
          :description="loadError ? '买点 SOP 加载失败' : '暂无买点分析结果'"
        />
        <template v-else>
        <div v-if="llmRefreshing" class="llm-refresh-banner">
          <span class="llm-refresh-banner-label">LLM 解读刷新中</span>
          <strong>正在重新生成这只股票的买点说明，请等待新结果覆盖当前文案。</strong>
          <span class="llm-refresh-banner-copy">通常需要 10-20 秒，刷新期间会先保留旧解读，避免页面突然空掉。</span>
        </div>
        <div class="overview-card">
          <div class="overview-top">
            <div class="overview-badge" :class="actionBadgeClass">
              {{ execution?.action || '等' }}
            </div>
            <div class="overview-copy">
              <div class="overview-title">{{ actionHeadline }}</div>
              <div class="overview-desc">{{ execution?.reason || '-' }}</div>
              <div class="overview-conclusion">
                {{ positionAdvice?.suggestion || '-' }}：{{ positionAdvice?.reason || '-' }}
              </div>
            </div>
          </div>

          <div class="overview-tags">
            <span class="overview-tag">{{ basic?.buy_signal_tag || '-' }}</span>
            <span class="overview-tag">{{ basic?.buy_display_type || basic?.buy_point_type || '-' }}</span>
            <span class="overview-tag">日线 {{ daily?.buy_point_level || '-' }}</span>
            <span class="overview-tag">分时 {{ intraday?.conclusion || '-' }}</span>
          </div>

          <div class="mode-banner" :class="{ 'mode-banner-live': isRealtimeQuote, 'mode-banner-fallback': !isRealtimeQuote }">
            <strong>{{ quoteModeTitle }}</strong>
            <span>{{ quoteModeCopy }}</span>
          </div>

          <div class="overview-main-grid">
            <div class="hero-card hero-card-primary" :class="heroCardToneClass">
              <span class="hero-label">{{ primaryExecutionLabel }}</span>
              <strong class="hero-value">{{ primaryExecutionValue }}</strong>
              <span class="hero-note">{{ primaryExecutionCopy }}</span>
            </div>

            <div class="overview-grid">
              <div
                v-for="card in summaryCards"
                :key="card.label"
                class="summary-card"
              >
                <span class="summary-label">{{ card.label }}</span>
                <strong class="summary-value" :class="card.valueClass || ''">{{ card.value }}</strong>
                <span class="summary-tip">{{ card.tip }}</span>
              </div>
            </div>
          </div>

          <div class="quote-strip">
            <span>{{ basic?.sector_name || '-' }}</span>
            <span v-if="directionMatchLabel">{{ directionMatchLabel }}</span>
            <span>{{ basic?.candidate_bucket_tag || '未分层' }}</span>
            <span v-if="basic?.buy_execution_context">原始语境 {{ basic.buy_execution_context }}</span>
            <span>{{ quoteMeta }}</span>
          </div>
        </div>
        <section class="analysis-section order-plan-section">
          <div class="section-header-row">
            <div class="section-header">{{ planSectionTitle }}</div>
            <div class="order-plan-summary">{{ orderPlanSummary }}</div>
          </div>
          <div class="order-plan-lead" :class="`order-plan-lead-${orderPlanLeadTone}`">
            <strong>{{ orderPlanLeadTitle }}</strong>
            <span>{{ orderPlanLeadCopy }}</span>
          </div>
          <div v-if="deepRetraceNotice" class="deep-retrace-notice">
            {{ deepRetraceNotice }}
          </div>
          <div class="order-plan-grid">
            <article
              v-for="card in primaryOrderPlanCards"
              :key="card.key"
              class="order-card"
              :class="[
                `order-card-${card.tone}`,
                { 'order-card-primary': card.primary, 'order-card-inactive': !card.active }
              ]"
            >
              <div class="order-card-top">
                <div>
                  <div class="order-card-label">{{ card.label }}</div>
                  <div class="order-card-scene">{{ card.scene }}</div>
                </div>
                <span class="order-card-badge">{{ card.badge }}</span>
              </div>
              <div class="order-card-price" :class="{ 'order-card-price-empty': !card.active }">
                {{ card.value }}
              </div>
              <div class="order-card-note">{{ card.note }}</div>
            </article>
          </div>
          <div class="position-advice-strip">
            <div class="position-advice-main">
              <span class="position-advice-label">仓位建议</span>
              <div class="position-advice-head">
                <strong>{{ positionAdvice?.suggestion || '-' }}</strong>
                <span class="strategy-pill" :class="actionBadgeClass">{{ formatPlanPct(positionAdvice?.plan_position_pct) }}</span>
              </div>
              <div class="position-advice-copy">{{ positionAdvice?.reason || '-' }}</div>
            </div>
            <div class="position-advice-side">
              <div v-if="positionAdviceSizingDisplay" class="position-advice-note">{{ positionAdviceSizingDisplay }}</div>
              <div class="position-advice-note">失效位：{{ positionAdvice?.invalidation_level || '-' }}</div>
              <div class="position-advice-note">{{ positionAdvice?.invalidation_action || '-' }}</div>
            </div>
          </div>
          <div v-if="backupOrderPlanCards.length" class="order-plan-backup">
            <div class="order-flow-title">备用买入方案</div>
            <div class="backup-card-list">
              <article
                v-for="card in backupOrderPlanCards"
                :key="`backup-${card.key}`"
                class="backup-card"
              >
                <strong>{{ card.label }}：{{ card.value }}</strong>
                <span>{{ card.note }}</span>
              </article>
            </div>
          </div>

          <details class="execution-details-disclosure">
            <summary class="execution-details-summary">
              <div class="execution-details-copy">
                <strong>展开完整执行说明</strong>
                <span>{{ executionDetailsSummary }}</span>
              </div>
              <span class="execution-details-icon">查看顺序与原始条件</span>
            </summary>

            <div class="execution-details-body">
              <div class="order-plan-flow">
                <div class="order-flow-title">执行顺序</div>
                <div class="order-flow-list">
                  <div
                    v-for="(step, index) in orderExecutionSteps"
                    :key="step.key"
                    class="order-flow-item"
                  >
                    <span class="order-flow-index">{{ index + 1 }}</span>
                    <div class="order-flow-copy">
                      <strong>{{ step.title }}</strong>
                      <span>{{ step.note }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <details class="order-plan-details order-plan-raw">
                <summary>展开原始规则文本</summary>
                <div class="section-note">触发条件：{{ orderPlan?.trigger_condition || '-' }}</div>
                <div class="section-note">失效条件：{{ orderPlan?.invalid_condition || '-' }}</div>
                <div class="section-note">高于哪里不追：{{ orderPlan?.above_no_chase || '-' }}</div>
                <div class="section-note">跌破哪里不买：{{ orderPlan?.below_no_buy || '-' }}</div>
              </details>
            </div>
          </details>
        </section>

        <details class="analysis-disclosure">
          <summary class="analysis-disclosure-summary">
            <div class="analysis-disclosure-copy">
              <strong>查看更多分析</strong>
              <span>{{ analysisSummary }}</span>
            </div>
            <span class="analysis-disclosure-icon">查看账户 / 日线 / 分时 / 仓位</span>
          </summary>

          <div class="section-grid">
            <section class="analysis-section section-account">
              <div class="section-header">账户语境</div>
              <div class="data-list">
                <div class="data-item"><span>当前仓位</span><strong>{{ accountContext?.position_status || '-' }}</strong></div>
                <div class="data-item"><span>当前用途</span><strong>{{ accountContext?.current_use || '-' }}</strong></div>
                <div class="data-item"><span>方向锚点</span><strong>{{ directionMatchLabel || '未命中主线方向' }}</strong></div>
                <div class="data-item"><span>同方向暴露</span><strong>{{ accountContext?.same_direction_exposure || '-' }}</strong></div>
                <div class="data-item"><span>市场适配度</span><strong>{{ accountContext?.market_suitability || '-' }}</strong></div>
              </div>
              <div class="section-emphasis">{{ accountContext?.account_conclusion || '-' }}</div>
              <div class="section-note">稳定环境：{{ basic?.stable_market_env_tag || '-' }}；实时环境：{{ basic?.realtime_market_env_tag || basic?.market_env_tag || '-' }}</div>
            </section>

            <section v-if="showAddDecisionSection" class="analysis-section section-add-position">
              <div class="section-header-row">
                <div class="section-header">加仓决策</div>
                <div class="decision-summary">{{ addDecision?.decision || '-' }}</div>
              </div>
              <div class="decision-lead" :class="`decision-lead-${addDecisionTone}`">
                <strong>{{ addDecisionLeadTitle }}</strong>
                <span>{{ addDecision?.reason || '当前不是加仓语境。' }}</span>
              </div>
              <div class="decision-grid">
                <article v-for="item in addDecisionScoreRows" :key="item.label" class="decision-cell">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </article>
              </div>
              <div class="section-note">触发场景：{{ addDecision?.trigger_scene || '-' }}</div>
              <div class="section-note">建议推进：当前约 {{ formatPlanPct(positionAdvice?.plan_position_pct) }}，单次加 {{ formatPlanPct(positionAdvice?.increment_position_pct) }}，上限 {{ formatPlanPct(positionAdvice?.max_position_pct) }}</div>
              <div class="section-note">失败处理：{{ positionAdvice?.risk_control_action || positionAdvice?.invalidation_action || '-' }}</div>
              <div v-if="addDecisionBlockers.length" class="chip-list">
                <span v-for="item in addDecisionBlockers" :key="item" class="risk-chip">{{ item }}</span>
              </div>
            </section>

            <section class="analysis-section section-daily">
              <div class="section-header-row">
                <div class="section-header">日线买点级别</div>
                <div class="decision-summary">{{ dailyDecisionSummary }}</div>
              </div>
              <div class="daily-outcome-band" :class="`daily-outcome-band-${dailyLeadTone}`">
                <div class="daily-outcome-main">
                  <span class="daily-outcome-kicker">今天按日线怎么处理</span>
                  <strong>{{ dailyLeadTitle }}</strong>
                  <p>{{ dailyLeadCopy }}</p>
                </div>
                <div class="daily-outcome-side">
                  <article class="daily-outcome-chip">
                    <span>买点级别</span>
                    <strong>{{ daily?.buy_point_level || '-' }}</strong>
                  </article>
                  <article class="daily-outcome-chip">
                    <span>执行结论</span>
                    <strong>{{ dailyDecisionSummary }}</strong>
                  </article>
                </div>
              </div>
              <div class="daily-snapshot-grid">
                <article v-for="item in dailyHighlights" :key="item.label" class="daily-snapshot-card">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </article>
              </div>
              <div v-if="daily?.risk_items?.length" class="daily-risk-block">
                <div class="daily-subheader">当前卡住它的点</div>
                <div class="chip-list">
                  <span v-for="item in daily?.risk_items || []" :key="item" class="risk-chip">{{ item }}</span>
                </div>
              </div>
              <details class="detail-panel detail-panel-daily" v-if="dailyReferenceRows.length">
                <summary>参考结构位</summary>
                <div class="level-list level-list-compact">
                  <div v-for="item in dailyReferenceRows" :key="item.label" class="level-row">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </div>
                </div>
              </details>
            </section>

            <section class="analysis-section section-intraday">
              <div class="section-header-row">
                <div class="section-header">分时执行判断</div>
                <div class="decision-summary">{{ intradayDecisionSummary }}</div>
              </div>
              <div class="decision-lead" :class="`decision-lead-${intradayLeadTone}`">
                <strong>{{ intradayLeadTitle }}</strong>
                <span>{{ intradayLeadCopy }}</span>
              </div>
              <div class="decision-grid">
                <article v-for="item in intradayChecks" :key="item.label" class="decision-cell">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </article>
              </div>
              <div class="section-note">{{ intraday?.note || '-' }}</div>
            </section>

            <section class="analysis-section section-position">
              <div class="section-header">仓位建议</div>
              <div class="strategy-pill" :class="actionBadgeClass">{{ positionAdvice?.suggestion || '-' }}</div>
              <div class="section-emphasis">{{ positionAdvice?.reason || '-' }}</div>
              <div v-if="positionAdviceSizingDisplay" class="section-note">{{ positionAdviceSizingDisplay }}</div>
              <div class="section-note">错了看哪里失效：{{ positionAdvice?.invalidation_level || '-' }}</div>
              <div class="section-note">{{ positionAdvice?.invalidation_action || '-' }}</div>
            </section>
          </div>
        </details>

        <section v-if="llmPanelVisible" class="analysis-section analysis-section-full llm-section">
          <div class="section-header-row">
            <div class="section-header">辅助解读</div>
            <div v-if="llmStatusVisible" class="decision-summary" :class="llmStatusClass">{{ llmStatusText }}</div>
          </div>
          <div v-if="llmSummary?.plain_note" class="llm-note-main" :class="{ 'llm-note-main-refreshing': llmRefreshing }">
            <div class="llm-note-head">
              <span>卡片说明</span>
              <span v-if="llmRefreshing" class="llm-note-refresh-flag">刷新中</span>
            </div>
            <div>{{ llmSummary.plain_note }}</div>
          </div>
          <div class="llm-note-grid">
            <article v-if="llmSummary?.execution_hint" class="llm-note-card" :class="{ 'llm-note-card-refreshing': llmRefreshing }">
              <span>当前最该盯</span>
              <strong>{{ llmSummary.execution_hint }}</strong>
            </article>
            <article v-if="llmSummary?.risk_hint" class="llm-note-card" :class="{ 'llm-note-card-refreshing': llmRefreshing }">
              <span>最容易误读</span>
              <strong>{{ llmSummary.risk_hint }}</strong>
            </article>
          </div>
          <div class="section-note">仅作规则结果的人话解释，不改动买点级别、挂单价和仓位建议。</div>
        </section>
        </template>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { stockApi } from '../api'
import { formatLocalDateTime } from '../utils/datetime'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  tsCode: { type: String, default: '' },
  stockName: { type: String, default: '' },
  tradeDate: { type: String, default: '' },
  sourcePoolTag: { type: String, default: '' },
  currentPrice: { type: Number, default: null },
  currentChangePct: { type: Number, default: null }
})

const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const llmRefreshing = ref(false)
const data = ref(null)
const loadError = ref('')

const basic = computed(() => data.value?.basic_info || null)
const accountContext = computed(() => data.value?.account_context || null)
const daily = computed(() => data.value?.daily_judgement || null)
const intraday = computed(() => data.value?.intraday_judgement || null)
const orderPlan = computed(() => data.value?.order_plan || null)
const addDecision = computed(() => data.value?.add_position_decision || null)
const positionAdvice = computed(() => data.value?.position_advice || null)
const execution = computed(() => data.value?.execution || null)
const llmSummary = computed(() => data.value?.llm_summary || null)
const llmStatus = computed(() => data.value?.llm_status || null)
const displayTradeDate = computed(() => props.tradeDate || getLocalDate())
const todayDate = computed(() => getLocalDate())
const dateContextNotice = computed(() => {
  if (!displayTradeDate.value || displayTradeDate.value === todayDate.value) return ''
  return `当前是 ${displayTradeDate.value} 的历史/稳定快照口径；今日买点页会按 ${todayDate.value} 重新判断，结论可能不同。`
})
const headerTitle = computed(() => `${props.stockName || '个股'}买点 SOP`)
const displayCurrentPrice = computed(() => {
  if (props.currentPrice === null || props.currentPrice === undefined) return '-'
  return Number(props.currentPrice).toFixed(2)
})
const displayCurrentChangePct = computed(() => {
  if (props.currentChangePct === null || props.currentChangePct === undefined) return '-'
  const num = Number(props.currentChangePct)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
})
const currentChangeClass = computed(() => {
  if (props.currentChangePct === null || props.currentChangePct === undefined) return ''
  if (Number(props.currentChangePct) > 0) return 'text-red'
  if (Number(props.currentChangePct) < 0) return 'text-green'
  return 'text-neutral'
})
const quoteMeta = computed(() => {
  const source = basic.value?.data_source
  const quoteTime = basic.value?.quote_time
  const sourceLabel = source && String(source).startsWith('realtime_') ? '实时/收盘快照' : '日线回退'
  if (quoteTime) return `${sourceLabel} ${formatLocalDateTime(quoteTime)}`
  return `${sourceLabel} ${displayTradeDate.value}`
})
const llmStatusVisible = computed(() => Boolean(llmStatus.value?.message))
const llmStatusText = computed(() => {
  if (llmRefreshing.value) return '正在刷新这只股票的页面说明和执行提示，请等待新结果返回'
  if (!llmStatus.value?.message) return ''
  return llmStatus.value.message
})
const llmStatusClass = computed(() => {
  if (llmRefreshing.value) return 'text-brand'
  if (llmStatus.value?.success) return 'text-brand'
  if (llmStatus.value?.enabled) return 'text-warning'
  return 'text-neutral'
})
const llmPanelVisible = computed(() => (
  Boolean(llmSummary.value?.plain_note || llmSummary.value?.execution_hint || llmSummary.value?.risk_hint || llmStatusVisible.value)
))
const directionMatchLabel = computed(() => {
  const name = String(basic.value?.direction_match_name || '').trim()
  const sourceType = String(basic.value?.direction_match_source_type || '').trim()
  if (!name) return ''
  if (sourceType === 'concept') return `主线题材 ${name}`
  if (sourceType === 'industry' || sourceType === 'limitup_industry') return `承接行业 ${name}`
  return name
})
const actionBadgeClass = computed(() => {
  if (execution.value?.action === '买' || execution.value?.action === '加') return 'badge-buy'
  if (execution.value?.action === '放弃') return 'badge-pass'
  return 'badge-wait'
})
const showAddDecisionSection = computed(() => (
  accountContext.value?.current_use === '加仓' || Boolean(addDecision.value?.eligible)
))
const addDecisionTone = computed(() => {
  if (addDecision.value?.decision === '可加') return 'success'
  if (addDecision.value?.decision === '仅可小加') return 'info'
  return 'danger'
})
const addDecisionLeadTitle = computed(() => {
  if (addDecision.value?.decision === '可加') return '这笔底仓已经具备标准加仓条件'
  if (addDecision.value?.decision === '仅可小加') return '结构有延续，但只适合小步推进'
  return '当前不满足加仓条件，先守住已有利润垫'
})
const addDecisionScoreRows = computed(() => ([
  { label: '总分', value: addDecision.value?.score_total ?? '-' },
  { label: '趋势结构', value: addDecision.value?.trend_score ?? '-' },
  { label: '位置性价比', value: addDecision.value?.position_score ?? '-' },
  { label: '量价配合', value: addDecision.value?.volume_price_score ?? '-' },
  { label: '板块情绪', value: addDecision.value?.sector_sentiment_score ?? '-' },
  { label: '账户风险', value: addDecision.value?.account_risk_score ?? '-' },
]))
const addDecisionBlockers = computed(() => addDecision.value?.blockers || [])
const dailyDecisionSummary = computed(() => {
  const level = daily.value?.buy_point_level || '-'
  if (level === 'A') return '日线已通过，等分时确认后可以执行'
  if (level === 'B') return '日线没坏，但还不能按现价直接下单'
  if (level === 'C') return '日线还停留在观察阶段，先别急着下单'
  if (level === 'D') return '日线没通过，今天不给下单资格'
  return '先确认日线，再决定盘中有没有必要盯'
})
const dailyLeadTitle = computed(() => {
  const level = daily.value?.buy_point_level || '-'
  if (level === 'A') return '日线已经通过，可以继续等分时确认'
  if (level === 'B') return '日线没坏，但还不到直接下单的位置'
  if (level === 'C') return '日线还在观察阶段，不是今天直接出手的位置'
  return '日线没过，今天先不要给它下单资格'
})
const normalizedDailyReason = computed(() => {
  const reason = String(daily.value?.reason || '').trim()
  if (!reason) return ''
  if (reason === '日线通过，盘中可等确认后执行') return '日线已经通过，但真正下单前仍要等分时确认。'
  if (reason === '这只票的日线结构是过关的') return '日线已经通过，但真正下单前仍要等分时确认。'
  if (reason === '日线能看，但不够舒服') return '日线没坏，但位置和节奏还不够直接下单，仍要等分时确认。'
  if (reason === '日线可做，但不能跳过分时确认') return '日线具备继续跟踪的资格，但执行前仍要等分时确认。'
  if (reason === '日线更多是观察位，不宜急着下单') return '这更像日线观察位，还不到今天主动下单的阶段。'
  if (reason === '日线更偏观察，不是直接出手位') return '这更像日线观察位，还不到今天主动下单的阶段。'
  if (reason === '日线不合格，今天不做') return '日线条件没过，今天不值得给它下单资格。'
  if (reason === '日线不通过，先别给它下单资格') return '日线条件没过，今天不值得给它下单资格。'
  return reason
})
const dailyLeadCopy = computed(() => normalizedDailyReason.value || '先确认阶段、买点信号和位置，再决定是否值得盘中继续盯。')
const dailyLeadTone = computed(() => {
  const level = daily.value?.buy_point_level || '-'
  if (level === 'A') return 'success'
  if (level === 'D') return 'danger'
  return 'info'
})
const dailyHighlights = computed(() => ([
  { label: '当前阶段', value: daily.value?.current_stage || '-' },
  { label: '买点信号', value: daily.value?.buy_signal || '-' },
  { label: '买点级别', value: daily.value?.buy_point_level || '-' },
]))
const dailyReferenceRows = computed(() => (
  (daily.value?.reference_levels || []).map((item) => {
    const [label, ...rest] = String(item || '').split('：')
    return {
      label: label || '-',
      value: rest.join('：') || '-',
    }
  })
))
const intradayDecisionSummary = computed(() => {
  const conclusion = intraday.value?.conclusion || '-'
  if (conclusion === '买') return '分时确认到位，可以按主买入位执行'
  if (conclusion === '放弃' && daily.value?.buy_point_level === 'D') {
    return '分时虽有结构参考，但日线未通过，今天不执行'
  }
  if (conclusion === '放弃') return '分时承接质量不够，当前不值得执行'
  return `还没到直接下单位，先等${waitingTriggerLabel.value}`
})
const intradayLeadTitle = computed(() => {
  const conclusion = intraday.value?.conclusion || '-'
  if (conclusion === '买') return '分时已经给到相对明确的进场信号'
  if (conclusion === '放弃' && daily.value?.buy_point_level === 'D') return '分时形态可以参考，但不能覆盖日线否决'
  if (conclusion === '放弃') return '分时承接不够扎实，别把等待变成硬上'
  if (primaryOrderCardKey.value === 'retrace' && isActionableLevel(orderPlan.value?.retrace_confirm_price) && isBelowRetraceConfirmZone.value) {
    return '当前已落到确认区下方，先等重新站回，不把跌进去当成买点'
  }
  if (primaryOrderCardKey.value === 'retrace' && isActionableLevel(orderPlan.value?.retrace_confirm_price)) return '当前先等回踩确认，不是继续追高'
  if (primaryOrderCardKey.value === 'breakout' && isActionableLevel(orderPlan.value?.breakout_price)) return '当前先等突破站稳，不要提前抢跑'
  if (primaryOrderCardKey.value === 'low_absorb' && isActionableLevel(orderPlan.value?.low_absorb_price)) return '当前先等低吸区出现，不要在中间位硬接'
  return '当前最重要的是等触发，不是抢先下单'
})
const intradayLeadCopy = computed(() => {
  const structure = intraday.value?.intraday_structure || '-'
  const keyLevel = intraday.value?.key_level_status || '-'
  if (intraday.value?.conclusion === '买') return `${structure} 已经比较清楚，下一步是确认成交后别马上跌回关键位下方。`
  if (intraday.value?.conclusion === '放弃' && daily.value?.buy_point_level === 'D') {
    return `当前分时可见${structure}迹象，但日线级别未通过，今天只把这些关键位当观察边界，不当买点。${keyLevel}`
  }
  if (intraday.value?.conclusion === '放弃') return `${structure} 的承接质量还不够扎实，暂时不值得执行。${keyLevel}`
  if (primaryOrderCardKey.value === 'retrace' && isActionableLevel(orderPlan.value?.retrace_confirm_price) && isBelowRetraceConfirmZone.value) {
    return `当前价格已经落到回踩确认区 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)} 下方，这不等于确认成立；要先看能否重新站回该区间并稳住承接，若继续弱于 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 一线则计划失效。`
  }
  if (primaryOrderCardKey.value === 'retrace' && isActionableLevel(orderPlan.value?.retrace_confirm_price)) {
    return `现在更重要的是等价格回踩到 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)} 一带，并确认没有跌穿、承接能稳住；不是等它继续往上冲。`
  }
  if (primaryOrderCardKey.value === 'breakout' && isActionableLevel(orderPlan.value?.breakout_price)) {
    return `现在更重要的是等价格放量站稳 ${normalizeLevelValue(orderPlan.value?.breakout_price)} 附近，再确认不是假突破；不要提前赌它能冲过去。`
  }
  if (primaryOrderCardKey.value === 'low_absorb' && isActionableLevel(orderPlan.value?.low_absorb_price)) {
    return `现在更重要的是等价格回到低吸区 ${normalizeLevelValue(orderPlan.value?.low_absorb_price)} 附近，再看承接和量能是否配合；不是在中间位先伸手。`
  }
  return `${structure} 还不够明确，先盯关键位和均价线是否继续改善。`
})
const intradayLeadTone = computed(() => {
  const conclusion = intraday.value?.conclusion || '-'
  if (conclusion === '买') return 'success'
  if (conclusion === '放弃') return 'danger'
  return 'info'
})
const intradayChecks = computed(() => ([
  { label: '均价线关系', value: intraday.value?.price_vs_avg_line || '-' },
  { label: '分时结构', value: intraday.value?.intraday_structure || '-' },
  { label: '量能性质', value: intraday.value?.volume_quality || '-' },
  { label: '关键位状态', value: intraday.value?.key_level_status || '-' },
]))
const currentAction = computed(() => {
  const action = execution.value?.action || '等'
  return action === '加' ? '买' : action
})
const isRealtimeQuote = computed(() => String(basic.value?.data_source || '').startsWith('realtime_'))
const heroCardToneClass = computed(() => {
  if (currentAction.value === '买') return 'hero-card-buy'
  if (currentAction.value === '放弃') return 'hero-card-pass'
  return 'hero-card-wait'
})
const actionHeadline = computed(() => {
  if (currentAction.value === '买') return '条件接近完成，先盯主买入位，不要把追高当执行'
  if (currentAction.value === '放弃') return '今天先划边界，不给下单资格'
  return '先等触发确认，没到位前不抢跑'
})
const quoteModeTitle = computed(() => (
  isRealtimeQuote.value ? '当前为实时/收盘快照口径' : '当前为日线回退口径'
))
const quoteModeCopy = computed(() => (
  isRealtimeQuote.value
    ? '现价按实时行情或收盘后快照更新；低吸区、突破区、确认区和失效线默认锚定上一交易日结构。'
    : '下面的价位更适合作为计划参考，盘中仍要结合承接、量能和站稳情况确认。'
))
const primaryOrderCard = computed(() => (
  orderPlanCards.value.find((card) => card.key === primaryOrderCardKey.value) || null
))
const primaryExecutionLabel = computed(() => {
  if (currentAction.value === '买') return '现在先看哪买'
  if (currentAction.value === '放弃') return '今天先避开哪'
  return '继续观察先盯哪'
})
const primaryExecutionValue = computed(() => primaryOrderCard.value?.value || '-')
const primaryExecutionCopy = computed(() => {
  if (currentAction.value === '买') {
    return primaryOrderCard.value?.note || '主买入位出现并稳住后，再按计划下单。'
  }
  if (currentAction.value === '放弃') {
    return `今天重点看边界，不把中间价格误当成机会。跌破 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 不买。`
  }
  return `现在更重要的是等 ${waitingTriggerLabel.value}，而不是提前抢进去。`
})
const planSectionTitle = computed(() => {
  if (currentAction.value === '买') return '买入计划'
  if (currentAction.value === '放弃') return '放弃条件'
  return '观察计划'
})
const executionDetailsSummary = computed(() => {
  if (currentAction.value === '买') {
    return '顺序看主买入位、不追线和失效线，避免把观察条件误当即时买点。'
  }
  if (currentAction.value === '放弃') {
    return '顺序看不追线和失效线，今天核心是知道哪里不能做。'
  }
  return '顺序看主触发位、不追线和失效线，先等确认，再决定要不要下单。'
})
const summaryCards = computed(() => ([
  {
    label: '现价 / 涨跌',
    value: displayCurrentPrice.value,
    valueClass: currentChangeClass.value,
    tip: displayCurrentChangePct.value === '-' ? '涨跌幅待确认' : `当前涨跌 ${displayCurrentChangePct.value}`,
  },
  {
    label: '环境 / 日线',
    value: `${basic.value?.market_env_tag || '-'} / ${daily.value?.buy_point_level || '-'}`,
    tip: `${daily.value?.current_stage || '-'} · ${accountContext.value?.market_suitability || '-'}`,
  },
  {
    label: '分时 / 仓位',
    value: `${intraday.value?.conclusion || '-'} / ${positionAdvice.value?.suggestion || '-'}`,
    tip: intraday.value?.intraday_structure || '分时待确认',
  },
]))
const analysisSummary = computed(() => (
  `账户 ${accountContext.value?.current_use || '-'} · 日线 ${daily.value?.buy_point_level || '-'} · 分时 ${intraday.value?.conclusion || '-'} · 仓位 ${positionAdvice.value?.suggestion || '-'}`
))
const formatPlanPct = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${(Number(value) * 100).toFixed(0)}%`
}
const formatMoney = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}
const formatShares = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toLocaleString('zh-CN')} 股`
}
const isActionableLevel = (value) => {
  const text = String(value || '').trim()
  if (!text || text === '-') return false
  return !text.includes('需确认')
}
const normalizeLevelValue = (value) => (isActionableLevel(value) ? String(value).trim() : '当前不设')
const resolveRetraceFloorRatio = (tsCode) => {
  const code = String(tsCode || '').toUpperCase()
  if (code.endsWith('.BJ')) return 0.82
  if (code.startsWith('300') || code.startsWith('301') || code.startsWith('688')) return 0.88
  return 0.93
}
const parseZoneCenter = (value) => {
  const text = String(value || '').trim()
  if (!text || text === '-' || text.includes('需确认')) return null
  const parts = text.split('-').map((item) => Number(item))
  if (parts.length === 2 && parts.every((item) => !Number.isNaN(item))) {
    return (parts[0] + parts[1]) / 2
  }
  const single = Number(text)
  return Number.isNaN(single) ? null : single
}
const parseZoneBounds = (value) => {
  const text = String(value || '').trim()
  if (!text || text === '-' || text.includes('需确认')) return null
  const parts = text.split('-').map((item) => Number(item))
  if (parts.length === 2 && parts.every((item) => !Number.isNaN(item))) {
    return {
      low: Math.min(parts[0], parts[1]),
      high: Math.max(parts[0], parts[1]),
    }
  }
  const single = Number(text)
  if (Number.isNaN(single)) return null
  return { low: single, high: single }
}
const referenceCurrentPrice = computed(() => {
  if (props.currentPrice !== null && props.currentPrice !== undefined && !Number.isNaN(Number(props.currentPrice))) {
    return Number(props.currentPrice)
  }
  return parseZoneCenter(orderPlan.value?.breakout_price)
})
const retraceZoneBounds = computed(() => parseZoneBounds(orderPlan.value?.retrace_confirm_price))
const isBelowRetraceConfirmZone = computed(() => {
  const current = referenceCurrentPrice.value
  const bounds = retraceZoneBounds.value
  if (current === null || !bounds) return false
  return current < bounds.low
})
const isDeepRetraceReference = computed(() => {
  const current = referenceCurrentPrice.value
  const retraceCenter = parseZoneCenter(orderPlan.value?.retrace_confirm_price)
  if (current === null || retraceCenter === null) return false
  return retraceCenter < current * resolveRetraceFloorRatio(basic.value?.ts_code || props.tsCode)
})
const deepRetraceNotice = computed(() => {
  if (!isDeepRetraceReference.value || !isActionableLevel(orderPlan.value?.retrace_confirm_price)) return ''
  return `回踩确认区 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)} 离现价较远，当前先不把它当执行位，只作为深回踩后的理想二次确认参考。`
})
const waitingTriggerLabel = computed(() => {
  if (primaryOrderCardKey.value === 'retrace' && isActionableLevel(orderPlan.value?.retrace_confirm_price)) {
    if (isBelowRetraceConfirmZone.value) {
      return `重新站回 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)} 一带并稳住`
    }
    return `回踩到 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)} 一带并稳住`
  }
  if (primaryOrderCardKey.value === 'breakout' && isActionableLevel(orderPlan.value?.breakout_price)) {
    return `放量站稳 ${normalizeLevelValue(orderPlan.value?.breakout_price)} 附近`
  }
  if (primaryOrderCardKey.value === 'low_absorb' && isActionableLevel(orderPlan.value?.low_absorb_price)) {
    return `回到低吸区 ${normalizeLevelValue(orderPlan.value?.low_absorb_price)} 附近`
  }
  if (isActionableLevel(orderPlan.value?.low_absorb_price)) {
    return `回到低吸区 ${normalizeLevelValue(orderPlan.value?.low_absorb_price)} 附近`
  }
  if (isActionableLevel(orderPlan.value?.breakout_price)) {
    return `放量站稳 ${normalizeLevelValue(orderPlan.value?.breakout_price)} 附近`
  }
  if (isActionableLevel(orderPlan.value?.retrace_confirm_price)) {
    if (isBelowRetraceConfirmZone.value) {
      return `重新站回 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)} 一带并稳住`
    }
    return `回踩到 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)} 一带并稳住`
  }
  return '主触发位出现并稳住'
})
const structureCueText = computed(() => (
  [
    basic.value?.buy_point_type,
    intraday.value?.intraday_structure,
    orderPlan.value?.trigger_condition,
  ].filter(Boolean).join(' / ')
))
const prefersRetraceEntry = computed(() => /回踩|承接|低吸|中继/.test(structureCueText.value))
const prefersBreakoutEntry = computed(() => /突破|加速/.test(structureCueText.value))
const primaryOrderCardKey = computed(() => {
  if (currentAction.value === '放弃') {
    return isActionableLevel(orderPlan.value?.give_up_price) ? 'give_up' : 'invalid'
  }
  if (currentAction.value === '买') {
    if (prefersBreakoutEntry.value && isActionableLevel(orderPlan.value?.breakout_price)) return 'breakout'
    if (
      prefersRetraceEntry.value
      && isActionableLevel(orderPlan.value?.retrace_confirm_price)
      && !isDeepRetraceReference.value
    ) return 'retrace'
  }
  if (
    prefersRetraceEntry.value
    && isActionableLevel(orderPlan.value?.retrace_confirm_price)
    && !isDeepRetraceReference.value
  ) return 'retrace'
  if (isActionableLevel(orderPlan.value?.low_absorb_price)) return 'low_absorb'
  if (prefersBreakoutEntry.value && isActionableLevel(orderPlan.value?.breakout_price)) return 'breakout'
  if (isActionableLevel(orderPlan.value?.breakout_price)) return 'breakout'
  if (isActionableLevel(orderPlan.value?.retrace_confirm_price)) return 'retrace'
  if (isActionableLevel(orderPlan.value?.below_no_buy)) return 'invalid'
  if (isActionableLevel(orderPlan.value?.give_up_price)) return 'give_up'
  return 'low_absorb'
})
const orderPlanSummary = computed(() => {
  if (currentAction.value === '放弃') {
    return `高于 ${normalizeLevelValue(orderPlan.value?.above_no_chase)} 不追`
  }
  if (primaryOrderCardKey.value === 'retrace') {
    if (isBelowRetraceConfirmZone.value) {
      return `先看能否重新站回确认区 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)}`
    }
    return `先等确认区 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)}`
  }
  if (primaryOrderCardKey.value === 'breakout') {
    return `先看突破区 ${normalizeLevelValue(orderPlan.value?.breakout_price)}`
  }
  if (primaryOrderCardKey.value === 'low_absorb') {
    return `先等低吸区 ${normalizeLevelValue(orderPlan.value?.low_absorb_price)}`
  }
  return `跌破 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 不买`
})
const orderPlanLeadTitle = computed(() => {
  if (currentAction.value === '买') return '进场条件基本到位，按主买入位执行'
  if (currentAction.value === '放弃') return '今天只给边界，不给机会'
  if (isActionableLevel(orderPlan.value?.retrace_confirm_price) && isBelowRetraceConfirmZone.value) return '当前先等重新站回确认区，不把跌破确认区当成买点'
  if (isActionableLevel(orderPlan.value?.retrace_confirm_price)) return '当前先等回踩确认，不要把观察页当成下单页'
  if (isActionableLevel(orderPlan.value?.breakout_price)) return '当前先等突破站稳，不要把观察页当成下单页'
  if (isActionableLevel(orderPlan.value?.low_absorb_price)) return '当前先等低吸区出现，不要把观察页当成下单页'
  return '当前先等触发，不要把观察页当成下单页'
})
const orderPlanLeadCopy = computed(() => {
  if (currentAction.value === '买') {
    if (primaryOrderCardKey.value === 'breakout') {
      return `优先按突破挂单区执行，成交后第一件事是确认 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 不被跌破。`
    }
    if (primaryOrderCardKey.value === 'retrace') {
      return `优先看回踩确认区，只有回踩稳住才值得买；跌破 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 就别硬接。`
    }
    return `优先按低吸区试错，但本质仍是试错单，不是可以随便抬价追进去的买点。`
  }
  if (currentAction.value === '放弃') {
    return `上方 ${normalizeLevelValue(orderPlan.value?.above_no_chase)} 是放弃追价线，下方 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 是失效不买线；这些价格现在只负责告诉你哪里不能做，不代表中间就能做。`
  }
  if (primaryOrderCardKey.value === 'retrace' && isActionableLevel(orderPlan.value?.retrace_confirm_price) && isBelowRetraceConfirmZone.value) {
    return `当前价格已经低于回踩确认区 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)}，这代表承接确认还没成立；先看能否重新站回该区间并稳住，若继续弱于 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 则不买。`
  }
  if (primaryOrderCardKey.value === 'retrace' && isActionableLevel(orderPlan.value?.retrace_confirm_price)) {
    return `当前更重要的是等价格回踩到 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)} 一带并稳住承接；不是等它继续往上冲。高于 ${normalizeLevelValue(orderPlan.value?.above_no_chase)} 不追，跌破 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 不买。`
  }
  if (primaryOrderCardKey.value === 'breakout' && isActionableLevel(orderPlan.value?.breakout_price)) {
    return `当前更重要的是等价格放量站稳 ${normalizeLevelValue(orderPlan.value?.breakout_price)} 附近；不是提前赌突破。高于 ${normalizeLevelValue(orderPlan.value?.above_no_chase)} 不追，跌破 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 不买。`
  }
  if (primaryOrderCardKey.value === 'low_absorb' && isActionableLevel(orderPlan.value?.low_absorb_price)) {
    return `当前更重要的是等价格回到低吸区 ${normalizeLevelValue(orderPlan.value?.low_absorb_price)} 附近，再看是否有承接；不是在中间价位先试错。高于 ${normalizeLevelValue(orderPlan.value?.above_no_chase)} 不追，跌破 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 不买。`
  }
  return `当前更重要的是等主触发位出现并稳住。高于 ${normalizeLevelValue(orderPlan.value?.above_no_chase)} 不追，跌破 ${normalizeLevelValue(orderPlan.value?.below_no_buy)} 不买。`
})
const orderPlanLeadTone = computed(() => {
  if (currentAction.value === '买') return 'success'
  if (currentAction.value === '放弃') return 'danger'
  return 'info'
})
const orderPlanCards = computed(() => {
  const primaryKey = primaryOrderCardKey.value
  return [
    {
      key: 'low_absorb',
      label: '低吸挂单区',
      scene: '靠支撑先接，不追价',
      value: normalizeLevelValue(orderPlan.value?.low_absorb_price),
      note: primaryKey === 'low_absorb'
        ? `优先等价格回到 ${normalizeLevelValue(orderPlan.value?.low_absorb_price)} 一带，再看缩量承接是否站稳；这是靠近支撑的试错区，不是拉高后的追价区。`
        : '更适合靠近支撑时试错，不适合拉高后再追。',
      tone: 'entry',
      badge: isActionableLevel(orderPlan.value?.low_absorb_price) ? (primaryKey === 'low_absorb' ? '主路径' : '备选') : '当前不设',
      active: isActionableLevel(orderPlan.value?.low_absorb_price),
      primary: primaryKey === 'low_absorb',
    },
    {
      key: 'breakout',
      label: '突破挂单区',
      scene: '放量站稳后跟随',
      value: normalizeLevelValue(orderPlan.value?.breakout_price),
      note: primaryKey === 'breakout'
        ? `只有放量站稳 ${normalizeLevelValue(orderPlan.value?.breakout_price)} 附近，才按突破路径处理；先冲上去但站不稳，不算有效确认。`
        : '适合强势直上时跟随，不适合弱市或冲高回落时硬追。',
      tone: 'breakout',
      badge: isActionableLevel(orderPlan.value?.breakout_price) ? (primaryKey === 'breakout' ? '主路径' : '备选') : '当前不设',
      active: isActionableLevel(orderPlan.value?.breakout_price),
      primary: primaryKey === 'breakout',
    },
    {
      key: 'retrace',
      label: isDeepRetraceReference.value ? '深回踩参考位' : '回踩确认区',
      scene: isDeepRetraceReference.value ? '深回踩后二次确认' : (isBelowRetraceConfirmZone.value ? '重新站回并稳住后再进' : '确认承接后再进'),
      value: normalizeLevelValue(orderPlan.value?.retrace_confirm_price),
      note: primaryKey === 'retrace'
        ? (
          isBelowRetraceConfirmZone.value
            ? `当前价格已在确认区下方，不能把“跌进去”直接当成确认成立；要先看能否重新站回 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)} 一带并稳住。`
            : `只有回踩到 ${normalizeLevelValue(orderPlan.value?.retrace_confirm_price)} 一带后重新稳住，才按确认买点处理；没回到这里前，不把它当现价附近的执行位。`
        )
        : (
          isDeepRetraceReference.value
            ? '这条离现价较远，更像深回踩理想位，先作为二次回撤参考，不作为当前主路径。'
            : '这条更偏保守确认，用来过滤“看着强、实际站不稳”的位置。'
        ),
      tone: 'confirm',
      badge: isActionableLevel(orderPlan.value?.retrace_confirm_price)
        ? (
          primaryKey === 'retrace'
            ? '主路径'
            : (isDeepRetraceReference.value ? '深回踩' : '备选')
        )
        : '当前不设',
      active: isActionableLevel(orderPlan.value?.retrace_confirm_price),
      primary: primaryKey === 'retrace',
    },
    {
      key: 'give_up',
      label: '放弃追价线',
      scene: '高过这里不再追',
      value: normalizeLevelValue(orderPlan.value?.give_up_price),
      note: `高于 ${normalizeLevelValue(orderPlan.value?.above_no_chase)} 再追，性价比已经明显变差。`,
      tone: 'pass',
      badge: isActionableLevel(orderPlan.value?.give_up_price)
        ? (primaryKey === 'give_up' ? '先避开' : '不追线')
        : '当前不设',
      active: isActionableLevel(orderPlan.value?.give_up_price),
      primary: primaryKey === 'give_up',
    },
    {
      key: 'invalid',
      label: '失效不买线',
      scene: '跌破后计划作废',
      value: normalizeLevelValue(orderPlan.value?.below_no_buy),
      note: orderPlan.value?.invalid_condition || '跌破这条线且收不回，就不再继续挂单。',
      tone: 'danger',
      badge: isActionableLevel(orderPlan.value?.below_no_buy)
        ? (primaryKey === 'invalid' ? '先守住' : '硬规则')
        : '当前不设',
      active: isActionableLevel(orderPlan.value?.below_no_buy),
      primary: primaryKey === 'invalid',
    },
  ]
})
const primaryOrderPlanCards = computed(() => {
  if (currentAction.value === '放弃') {
    return orderPlanCards.value.filter((card) => ['give_up', 'invalid'].includes(card.key))
  }
  const keepKeys = new Set([primaryOrderCardKey.value, 'give_up', 'invalid'])
  const priority = {
    [primaryOrderCardKey.value]: 0,
    give_up: 1,
    invalid: 2,
  }
  return orderPlanCards.value
    .filter((card) => keepKeys.has(card.key))
    .sort((left, right) => (priority[left.key] ?? 3) - (priority[right.key] ?? 3))
})
const backupOrderPlanCards = computed(() => {
  if (currentAction.value === '放弃') return []
  return orderPlanCards.value.filter((card) => (
    card.active
    && ['low_absorb', 'breakout', 'retrace'].includes(card.key)
    && card.key !== primaryOrderCardKey.value
  ))
})
const orderExecutionSteps = computed(() => (
  primaryOrderPlanCards.value
    .filter((card) => card.active || ['give_up', 'invalid'].includes(card.key))
    .sort((left, right) => {
      const priority = {
        [primaryOrderCardKey.value]: 0,
        give_up: 1,
        invalid: 2,
      }
      return (priority[left.key] ?? 3) - (priority[right.key] ?? 3)
    })
    .map((card) => ({
      key: card.key,
      title: card.key === primaryOrderCardKey.value
        ? `先看主买入位：${card.value}`
        : `${card.label}：${card.value}`,
      note: card.note,
    }))
))
const positionAdviceSizingSummary = computed(() => {
  const shares = positionAdvice.value?.recommended_shares
  const amount = positionAdvice.value?.recommended_order_amount
  const referencePrice = positionAdvice.value?.sizing_reference_price
  if (!shares || !amount || !referencePrice) return ''
  const orderPct = positionAdvice.value?.recommended_order_pct
  const targetPct = positionAdvice.value?.recommended_position_pct
  const lots = positionAdvice.value?.recommended_lots
  const pctBits = []
  if (targetPct) pctBits.push(`目标单票约 ${formatPlanPct(targetPct)}`)
  if (orderPct) pctBits.push(`本次下单约 ${formatPlanPct(orderPct)}`)
  const pctText = pctBits.length ? `${pctBits.join('，')}；` : ''
  const lotText = lots ? `，约 ${lots} 手` : ''
  return `按当前价 ${Number(referencePrice).toFixed(2)} 测算：${pctText}建议先买 ${formatShares(shares)}${lotText}，预计占用 ${formatMoney(amount)} 元。`
})
const positionAdviceSizingDisplay = computed(() => (
  positionAdviceSizingSummary.value || positionAdvice.value?.sizing_note || ''
))

watch(
  () => [props.modelValue, props.tsCode, props.tradeDate],
  ([visible, tsCode]) => {
    if (!visible || !tsCode) return
    loadData()
  }
)

const handleClose = () => {
  emit('update:modelValue', false)
}

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const loadData = async (options = {}) => {
  if (!props.tsCode) return
  const refreshLlmOnly = Boolean(options.forceLlmRefresh)
  if (refreshLlmOnly) {
    llmRefreshing.value = true
  } else {
    loading.value = true
  }
  loadError.value = ''
  try {
    const res = await stockApi.buyAnalysis(props.tsCode, displayTradeDate.value, {
      timeout: 90000,
      sourcePoolTag: props.sourcePoolTag,
      forceLlmRefresh: refreshLlmOnly,
      includeLlm: true,
    })
    const payload = res.data || {}
    const responseCode = payload.code ?? 200
    if (responseCode !== 200) {
      throw new Error(payload.message || '加载买点 SOP 失败')
    }
    if (!payload.data) {
      throw new Error(payload.message || '买点 SOP 接口返回空结果')
    }
    data.value = payload.data
    if (refreshLlmOnly) {
      ElMessage.success('解读刷新完成')
    }
  } catch (error) {
    const message = error?.response?.data?.message || error?.message || '加载买点 SOP 失败'
    loadError.value = message
    ElMessage.error(message)
  } finally {
    loading.value = false
    llmRefreshing.value = false
  }
}

const refreshLlm = async () => {
  await loadData({ forceLlmRefresh: true })
}
</script>

<style scoped>
.drawer-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  width: 100%;
}

.header-main {
  display: grid;
  gap: 6px;
}

.header-title {
  font-size: 1.15rem;
  font-weight: 700;
}

.header-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--color-text-sec);
  font-size: 13px;
}

.drawer-date-notice {
  width: fit-content;
  max-width: 760px;
  padding: 6px 10px;
  border-radius: 10px;
  color: #ffd06a;
  background: rgba(243, 194, 77, 0.1);
  border: 1px solid rgba(243, 194, 77, 0.18);
  font-size: 12px;
  line-height: 1.5;
}

.drawer-body {
  display: grid;
  gap: 18px;
  padding-right: 6px;
}

.drawer-error {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 120, 120, 0.08);
  border: 1px solid rgba(255, 120, 120, 0.16);
  color: var(--color-text-main);
  font-size: 13px;
}

.llm-refresh-banner {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid rgba(83, 166, 255, 0.22);
  background: linear-gradient(135deg, rgba(83, 166, 255, 0.14), rgba(83, 166, 255, 0.05));
  position: relative;
  overflow: hidden;
  animation: llmBannerPulse 1.8s ease-in-out infinite;
}

.llm-refresh-banner::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 20%, rgba(255, 255, 255, 0.12) 45%, transparent 70%);
  transform: translateX(-120%);
  animation: llmBannerSweep 2.2s linear infinite;
}

.llm-refresh-banner-label {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #9dc2ff;
  position: relative;
  z-index: 1;
}

.llm-refresh-banner strong,
.llm-refresh-banner-copy {
  position: relative;
  z-index: 1;
}

.llm-refresh-banner strong {
  color: var(--color-text-main);
  line-height: 1.6;
  font-size: 15px;
}

.llm-refresh-banner-copy {
  color: var(--color-text-sec);
  line-height: 1.6;
  font-size: 13px;
}

.llm-section {
  gap: 14px;
}

.llm-note-main {
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(83, 166, 255, 0.16);
  background: rgba(83, 166, 255, 0.08);
  color: var(--color-text-main);
  line-height: 1.75;
}

.llm-note-main-refreshing,
.llm-note-card-refreshing {
  position: relative;
  overflow: hidden;
}

.llm-note-main-refreshing::after,
.llm-note-card-refreshing::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 25%, rgba(255, 255, 255, 0.1) 50%, transparent 75%);
  transform: translateX(-120%);
  animation: llmBannerSweep 2.4s linear infinite;
  pointer-events: none;
}

.llm-note-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  color: #9dc2ff;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.llm-note-refresh-flag {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(83, 166, 255, 0.14);
  color: #c5dbff;
  font-size: 11px;
  letter-spacing: 0.04em;
}

.llm-note-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.llm-note-card {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.llm-note-card span {
  color: var(--color-text-sec);
  font-size: 12px;
}

.llm-note-card strong {
  color: var(--color-text-main);
  line-height: 1.65;
}

@keyframes llmBannerPulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(83, 166, 255, 0.08);
  }
  50% {
    box-shadow: 0 0 0 1px rgba(83, 166, 255, 0.14);
  }
}

@keyframes llmBannerSweep {
  100% {
    transform: translateX(120%);
  }
}

.overview-card {
  display: grid;
  gap: 16px;
  padding: 22px;
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, rgba(68, 209, 159, 0.16), transparent 34%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.045));
  border: 1px solid rgba(255, 255, 255, 0.07);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.overview-top {
  display: flex;
  gap: 16px;
  align-items: stretch;
}

.overview-badge {
  min-width: 110px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 16px 18px;
  border-radius: 20px;
  color: #fff;
  text-align: center;
  font-weight: 800;
  letter-spacing: 0.06em;
}

.badge-buy {
  background: linear-gradient(135deg, #1d8b6f, #2fcf9a);
}

.badge-wait {
  background: linear-gradient(135deg, #d39b24, #f3c24d);
}

.badge-pass {
  background: linear-gradient(135deg, #d84d58, #ff7a7f);
}

.overview-copy {
  display: grid;
  gap: 8px;
  align-content: center;
}

.overview-title {
  font-size: 1.05rem;
  font-weight: 700;
}

.overview-desc,
.overview-conclusion,
.section-note,
.level-row {
  line-height: 1.7;
}

.overview-conclusion {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.overview-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.overview-tag {
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-sec);
  font-size: 12px;
}

.mode-banner {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.mode-banner strong {
  font-size: 13px;
}

.mode-banner span {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.mode-banner-live {
  background: rgba(46, 207, 154, 0.08);
  border-color: rgba(46, 207, 154, 0.2);
}

.mode-banner-fallback {
  background: rgba(122, 215, 255, 0.08);
  border-color: rgba(122, 215, 255, 0.2);
}

.overview-main-grid {
  display: grid;
  grid-template-columns: minmax(280px, 1.1fr) minmax(0, 2fr);
  gap: 14px;
  align-items: stretch;
}

.hero-card {
  display: grid;
  gap: 8px;
  padding: 18px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.06));
}

.hero-card-primary {
  border-color: rgba(255, 196, 64, 0.3);
  box-shadow: 0 0 0 1px rgba(255, 196, 64, 0.12) inset;
}

.hero-card-buy .hero-value {
  color: #58d7a2;
}

.hero-card-wait .hero-value {
  color: #7ad7ff;
}

.hero-card-pass .hero-value {
  color: #ff7a7f;
}

.hero-label {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.hero-value {
  font-size: 2.2rem;
  line-height: 1;
  font-weight: 800;
  letter-spacing: 0.01em;
  font-variant-numeric: tabular-nums;
  color: #ffd166;
}

.hero-note {
  color: var(--color-text-sec);
  line-height: 1.7;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.summary-label {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.summary-value {
  font-size: 1.5rem;
  line-height: 1;
}

.summary-tip {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.quote-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--color-text-sec);
  font-size: 13px;
}

.quote-strip span {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
}

.analysis-disclosure {
  display: grid;
  gap: 16px;
}

.analysis-disclosure-summary {
  list-style: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
  cursor: pointer;
}

.analysis-disclosure-summary::-webkit-details-marker {
  display: none;
}

.analysis-disclosure-copy {
  display: grid;
  gap: 4px;
}

.analysis-disclosure-copy strong {
  font-size: 14px;
}

.analysis-disclosure-copy span {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.analysis-disclosure-icon {
  flex-shrink: 0;
  color: var(--color-text-sec);
  font-size: 12px;
}

.analysis-disclosure[open] .analysis-disclosure-icon {
  color: var(--color-text-main);
}

.section-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  align-items: start;
}

.analysis-section {
  display: grid;
  gap: 12px;
  padding: 18px;
  border-radius: 20px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.024), rgba(255, 255, 255, 0.016));
  border: 1px solid rgba(255, 255, 255, 0.055);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
}

.analysis-section-full {
  grid-column: 1 / -1;
}

.order-plan-section {
  position: static;
}

.section-header-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.section-header {
  font-size: 15px;
  font-weight: 700;
}

.decision-summary {
  color: var(--color-text-sec);
  font-size: 13px;
}

.decision-lead {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.decision-lead strong {
  font-size: 14px;
}

.decision-lead span {
  color: var(--color-text-sec);
  line-height: 1.7;
}

.decision-lead-success {
  background: rgba(47, 207, 154, 0.08);
  border-color: rgba(47, 207, 154, 0.2);
}

.decision-lead-info {
  background: rgba(122, 215, 255, 0.08);
  border-color: rgba(122, 215, 255, 0.2);
}

.decision-lead-danger {
  background: rgba(255, 122, 127, 0.08);
  border-color: rgba(255, 122, 127, 0.24);
}

.daily-outcome-band {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) minmax(220px, 0.9fr);
  gap: 14px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.daily-outcome-band-success {
  background:
    linear-gradient(135deg, rgba(47, 207, 154, 0.12), rgba(47, 207, 154, 0.04));
  border-color: rgba(47, 207, 154, 0.22);
}

.daily-outcome-band-info {
  background:
    linear-gradient(135deg, rgba(122, 215, 255, 0.12), rgba(122, 215, 255, 0.04));
  border-color: rgba(122, 215, 255, 0.22);
}

.daily-outcome-band-danger {
  background:
    linear-gradient(135deg, rgba(255, 122, 127, 0.12), rgba(255, 122, 127, 0.04));
  border-color: rgba(255, 122, 127, 0.24);
}

.daily-outcome-main {
  display: grid;
  gap: 8px;
}

.daily-outcome-kicker {
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  letter-spacing: 0.04em;
}

.daily-outcome-main strong {
  font-size: 18px;
  line-height: 1.4;
}

.daily-outcome-main p {
  margin: 0;
  color: var(--color-text-sec);
  line-height: 1.75;
}

.daily-outcome-side {
  display: grid;
  gap: 10px;
}

.daily-outcome-chip {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.daily-outcome-chip span {
  color: var(--color-text-sec);
  font-size: 12px;
}

.daily-outcome-chip strong {
  line-height: 1.6;
}

.order-plan-summary {
  color: var(--color-text-sec);
  font-size: 13px;
}

.order-plan-lead {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.order-plan-lead strong {
  font-size: 14px;
}

.order-plan-lead span {
  color: var(--color-text-sec);
  line-height: 1.7;
}

.order-plan-lead-success {
  background: rgba(47, 207, 154, 0.08);
  border-color: rgba(47, 207, 154, 0.2);
}

.order-plan-lead-info {
  background: rgba(122, 215, 255, 0.08);
  border-color: rgba(122, 215, 255, 0.2);
}

.order-plan-lead-danger {
  background: rgba(255, 122, 127, 0.08);
  border-color: rgba(255, 122, 127, 0.24);
}

.deep-retrace-notice {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(255, 196, 107, 0.22);
  background: rgba(255, 196, 107, 0.08);
  color: #ffe3b3;
  line-height: 1.7;
  font-size: 13px;
}

.data-list {
  display: grid;
  gap: 8px;
}

.daily-snapshot-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.daily-snapshot-card {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.daily-snapshot-card span {
  color: var(--color-text-sec);
  font-size: 12px;
}

.daily-snapshot-card strong {
  line-height: 1.6;
}

.daily-risk-block {
  display: grid;
  gap: 10px;
}

.daily-subheader {
  font-size: 13px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.72);
}

.decision-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.decision-cell {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.decision-cell span {
  color: var(--color-text-sec);
  font-size: 12px;
}

.decision-cell strong {
  line-height: 1.7;
}

.compact-list {
  margin-top: 4px;
}

.data-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.data-item span {
  color: var(--color-text-sec);
  flex-shrink: 0;
}

.data-item strong {
  text-align: right;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.risk-chip {
  padding: 6px 10px;
  border-radius: 999px;
  color: #ffc0c4;
  background: rgba(255, 122, 127, 0.08);
  border: 1px solid rgba(255, 122, 127, 0.15);
  font-size: 12px;
}

.level-list {
  display: grid;
  gap: 8px;
}

.detail-panel {
  display: grid;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.detail-panel summary {
  cursor: pointer;
  color: var(--color-text-sec);
  font-size: 13px;
}

.detail-panel-daily {
  gap: 12px;
}

.level-list-compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
}

.level-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.level-row span {
  color: var(--color-text-sec);
}

.level-row strong {
  text-align: right;
}

.price-grid,
.order-plan-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.order-card {
  display: grid;
  gap: 14px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  min-height: 164px;
}

.order-card-primary {
  border-color: rgba(255, 255, 255, 0.16);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
}

.order-card-inactive {
  opacity: 0.76;
}

.order-card-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.order-card-label {
  font-size: 14px;
  font-weight: 700;
}

.order-card-scene {
  margin-top: 4px;
  color: var(--color-text-sec);
  font-size: 12px;
  line-height: 1.6;
}

.order-card-badge {
  flex-shrink: 0;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-text-sec);
  font-size: 12px;
  font-weight: 600;
}

.order-card-price {
  font-size: 1.15rem;
  font-weight: 800;
  line-height: 1.28;
  word-break: break-word;
}

.order-card-price-empty {
  color: #c7a04a;
}

.order-card-note {
  color: var(--color-text-sec);
  line-height: 1.7;
}

.order-card-entry .order-card-price {
  color: #58d7a2;
}

.order-card-breakout .order-card-price {
  color: #ffbf59;
}

.order-card-confirm .order-card-price {
  color: #7ad7ff;
}

.order-card-pass .order-card-price {
  color: #d7a85c;
}

.order-card-danger .order-card-price {
  color: #ff7a7f;
}

.order-plan-backup,
.order-plan-flow {
  display: grid;
  gap: 10px;
}

.position-advice-strip {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(280px, 1fr);
  gap: 14px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.position-advice-main,
.position-advice-side {
  display: grid;
  gap: 8px;
}

.position-advice-label {
  color: var(--color-text-sec);
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.position-advice-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.position-advice-head strong {
  font-size: 1.05rem;
  line-height: 1.4;
}

.position-advice-copy,
.position-advice-note {
  color: var(--color-text-sec);
  line-height: 1.7;
}

.execution-details-disclosure {
  display: grid;
  gap: 12px;
}

.execution-details-summary {
  list-style: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
  cursor: pointer;
}

.execution-details-summary::-webkit-details-marker {
  display: none;
}

.execution-details-copy {
  display: grid;
  gap: 4px;
}

.execution-details-copy strong {
  font-size: 14px;
}

.execution-details-copy span,
.execution-details-icon {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.execution-details-icon {
  flex-shrink: 0;
  font-size: 12px;
}

.execution-details-disclosure[open] .execution-details-icon {
  color: var(--color-text-main);
}

.execution-details-body {
  display: grid;
  gap: 12px;
}

.order-plan-details {
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
  overflow: hidden;
}

.order-plan-details summary {
  cursor: pointer;
  padding: 12px 14px;
  color: var(--color-text-sec);
  font-size: 13px;
  user-select: none;
}

.order-plan-details[open] summary {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.order-plan-details .backup-card-list,
.order-plan-details .section-note {
  margin: 12px 14px;
}

.order-plan-raw {
  margin-top: 2px;
}

.order-flow-title {
  font-size: 13px;
  color: var(--color-text-sec);
  letter-spacing: 0.04em;
}

.backup-card-list,
.order-flow-list {
  display: grid;
  gap: 10px;
}

.backup-card,
.order-flow-item {
  display: flex;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.backup-card {
  flex-direction: column;
}

.backup-card strong {
  font-size: 14px;
}

.backup-card span,
.order-flow-copy span {
  color: var(--color-text-sec);
  line-height: 1.7;
}

.order-flow-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.order-flow-copy {
  display: grid;
  gap: 4px;
}

.strategy-pill,
.section-emphasis {
  font-weight: 700;
  line-height: 1.7;
}

.strategy-pill {
  display: inline-flex;
  width: fit-content;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
}

@media (max-width: 1500px) {
  .section-grid {
    grid-template-columns: minmax(0, 1fr) minmax(320px, 0.95fr);
  }

  .decision-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .daily-outcome-band {
    grid-template-columns: 1fr;
  }

  .daily-snapshot-grid,
  .level-list-compact {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1200px) {
  .drawer-header,
  .overview-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .overview-main-grid,
  .decision-grid,
  .daily-snapshot-grid,
  .overview-grid,
  .section-grid,
  .position-advice-strip,
  .price-grid,
  .order-plan-grid,
  .level-list-compact,
  .daily-outcome-band {
    grid-template-columns: 1fr;
  }

  .data-item {
    flex-direction: column;
  }
}
</style>
