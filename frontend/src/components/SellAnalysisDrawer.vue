<template>
  <el-drawer
    :model-value="modelValue"
    size="72%"
    :destroy-on-close="false"
    class="sell-analysis-drawer"
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
        </div>
        <div class="header-actions">
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </div>
    </template>

    <div class="drawer-body">
      <el-empty v-if="!tsCode" description="请选择一只持仓后再查看卖点 SOP" />
      <template v-else>
        <div v-if="loadError" class="drawer-error">
          {{ loadError }}
        </div>
        <el-skeleton v-if="loading && !data" :rows="14" animated />
        <el-empty
          v-else-if="!data"
          :description="loadError ? '卖点 SOP 加载失败' : '暂无卖点分析结果'"
        />
        <template v-else>
        <div class="overview-card">
          <div class="overview-top">
            <div class="overview-badge" :class="actionBadgeClass">
              {{ execution?.action || '拿' }}
            </div>
            <div class="overview-copy">
              <div class="overview-title">{{ actionHeadline }}</div>
              <div class="overview-desc">{{ execution?.reason || '-' }}</div>
              <div class="overview-conclusion">
                {{ execution?.partial_plan || '-' }}
              </div>
            </div>
          </div>

          <div class="overview-tags">
            <span class="overview-tag">{{ basic?.sell_signal_tag || '-' }}</span>
            <span class="overview-tag">{{ basic?.sell_point_type || '-' }}</span>
            <span class="overview-tag">日线 {{ daily?.sell_point_level || '-' }}</span>
            <span class="overview-tag">分时 {{ sanitizePendingText(intraday?.conclusion) }}</span>
          </div>

          <div class="mode-banner" :class="{ 'mode-banner-live': isRealtimeQuote, 'mode-banner-fallback': !isRealtimeQuote }">
            <strong>{{ quoteModeTitle }}</strong>
            <span>{{ quoteModeCopy }}</span>
          </div>

          <div class="overview-main-grid">
            <div class="hero-card hero-card-primary" :class="heroCardToneClass">
              <span class="hero-label">{{ primaryExecutionLabel }}</span>
              <strong class="hero-value">{{ execution?.key_level || '-' }}</strong>
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
            <span>{{ quoteMeta }}</span>
            <span>{{ accountContext?.context_summary || '-' }}</span>
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
          <div v-if="backupOrderPlanCards.length" class="order-plan-backup">
            <div class="order-flow-title">备用退出方案</div>
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
              <span class="execution-details-icon">查看顺序与条件</span>
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
              <div class="plan-notes-grid">
                <div class="section-note">{{ takeProfitNoteLabel }}：{{ orderPlan?.take_profit_condition || '-' }}</div>
                <div class="section-note">{{ reboundNoteLabel }}：{{ orderPlan?.rebound_condition || '-' }}</div>
                <div class="section-note">{{ stopNoteLabel }}：{{ orderPlan?.stop_condition || '-' }}</div>
                <div class="section-note">{{ holdNoteLabel }}：{{ orderPlan?.hold_condition || '-' }}</div>
              </div>
            </div>
          </details>
        </section>

        <details class="analysis-disclosure">
          <summary class="analysis-disclosure-summary">
            <div class="analysis-disclosure-copy">
              <strong>查看更多分析</strong>
              <span>{{ analysisSummary }}</span>
            </div>
            <span class="analysis-disclosure-icon">查看账户 / 日线 / 分时</span>
          </summary>

          <div class="section-grid">
            <section class="analysis-section">
              <div class="section-header">账户语境</div>
              <div class="data-list">
                <div class="data-item"><span>仓位</span><strong>{{ accountContext?.position_status || '-' }}</strong></div>
                <div class="data-item"><span>浮盈亏</span><strong>{{ accountContext?.pnl_status || '-' }}</strong></div>
                <div class="data-item"><span>角色</span><strong>{{ accountContext?.role || '-' }}</strong></div>
                <div class="data-item"><span>优先级</span><strong>{{ accountContext?.priority || '-' }}</strong></div>
              </div>
              <div class="section-emphasis">{{ accountContext?.context_summary || '-' }}</div>
              <div class="section-note">稳定环境：{{ basic?.stable_market_env_tag || '-' }}；实时环境：{{ basic?.realtime_market_env_tag || basic?.market_env_tag || '-' }}</div>
            </section>

            <section class="analysis-section">
              <div class="section-header">日线卖点级别</div>
              <div class="data-list">
                <div class="data-item"><span>当前阶段</span><strong>{{ daily?.current_stage || '-' }}</strong></div>
                <div class="data-item"><span>卖点信号</span><strong>{{ daily?.sell_signal || '-' }}</strong></div>
                <div class="data-item"><span>卖点级别</span><strong>{{ daily?.sell_point_level || '-' }}</strong></div>
              </div>
              <div class="section-note">{{ daily?.reason || '-' }}</div>
            </section>

            <section class="analysis-section analysis-section-wide analysis-section-intraday">
              <div class="section-header">分时执行判断</div>
              <div class="intraday-headline">
                <strong>{{ intradayHeadline }}</strong>
                <span>{{ sanitizePendingText(intraday?.note, '当前不是实时分时口径，具体卖法要结合盘中承接再确认。') }}</span>
              </div>
              <div class="data-list">
                <div class="data-item"><span>均价线关系</span><strong>{{ sanitizePendingText(intraday?.price_vs_avg_line, '当前待盘中确认') }}</strong></div>
                <div class="data-item"><span>分时结构</span><strong>{{ sanitizePendingText(intraday?.intraday_structure, '当前待盘中确认') }}</strong></div>
                <div class="data-item"><span>量能性质</span><strong>{{ sanitizePendingText(intraday?.volume_quality) }}</strong></div>
                <div class="data-item"><span>当前结论</span><strong>{{ sanitizePendingText(intraday?.conclusion) }}</strong></div>
              </div>
            </section>
          </div>
        </details>
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
  currentPrice: { type: Number, default: null },
  currentPnlPct: { type: Number, default: null },
})

const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const data = ref(null)
const loadError = ref('')

const basic = computed(() => data.value?.basic_info || null)
const accountContext = computed(() => data.value?.account_context || null)
const daily = computed(() => data.value?.daily_judgement || null)
const intraday = computed(() => data.value?.intraday_judgement || null)
const orderPlan = computed(() => data.value?.order_plan || null)
const execution = computed(() => data.value?.execution || null)
const displayTradeDate = computed(() => props.tradeDate || getLocalDate())
const headerTitle = computed(() => `${props.stockName || '持仓'}卖点 SOP`)
const displayCurrentPrice = computed(() => {
  if (props.currentPrice === null || props.currentPrice === undefined) return '-'
  return Number(props.currentPrice).toFixed(2)
})
const displayCurrentPnlPct = computed(() => {
  if (props.currentPnlPct === null || props.currentPnlPct === undefined) return '-'
  const num = Number(props.currentPnlPct)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
})
const currentPnlClass = computed(() => {
  if (props.currentPnlPct === null || props.currentPnlPct === undefined) return ''
  if (Number(props.currentPnlPct) > 0) return 'text-red'
  if (Number(props.currentPnlPct) < 0) return 'text-green'
  return 'text-neutral'
})
const quoteMeta = computed(() => {
  const source = basic.value?.data_source
  const quoteTime = basic.value?.quote_time
  const sourceLabel = source && String(source).startsWith('realtime_') ? '实时/收盘快照' : '日线回退'
  if (quoteTime) return `${sourceLabel} ${formatLocalDateTime(quoteTime)}`
  return `${sourceLabel} ${displayTradeDate.value}`
})
const currentAction = computed(() => execution.value?.action || '拿')
const isRealtimeQuote = computed(() => String(basic.value?.data_source || '').startsWith('realtime_'))
const heroCardToneClass = computed(() => {
  if (currentAction.value === '清') return 'hero-card-clear'
  if (currentAction.value === '减') return 'hero-card-reduce'
  return 'hero-card-hold'
})
const actionHeadline = computed(() => {
  if (currentAction.value === '清') return '优先退出，先看前面的处理区，不要等到底线'
  if (currentAction.value === '减') return '先减仓防守，给结构修复留余地'
  return '先守关键位，承接没坏前不急着动'
})
const quoteModeTitle = computed(() => (
  isRealtimeQuote.value ? '当前为实时/收盘快照口径' : '当前为日线回退口径'
))
const quoteModeCopy = computed(() => (
  isRealtimeQuote.value
    ? '现价按实时行情或收盘后快照更新；守位、失守位和反抽区默认锚定上一交易日结构。'
    : '下面的价位更适合作为计划参考，盘中仍要结合承接和回流确认。'
))
const primaryExecutionLabel = computed(() => {
  if (currentAction.value === '清') return '现在先卖哪'
  if (currentAction.value === '减') return '现在先减哪'
  return '继续拿先守哪'
})
const primaryExecutionCopy = computed(() => {
  if (currentAction.value === '清') return '能在更前面的处理区走，就不要把最后失效线当成第一卖点。'
  if (currentAction.value === '减') return '先把最舒服的减仓位看清，再决定后面要不要继续收缩。'
  return '守住这个位才值得继续拿；一旦失守，就切到退出线处理。'
})
const planSectionTitle = computed(() => {
  if (currentAction.value === '清') return '退出计划'
  if (currentAction.value === '减') return '减仓计划'
  return '继续持有计划'
})
const executionDetailsSummary = computed(() => {
  if (currentAction.value === '清') {
    return `顺序看先卖区、反抽区和最后底线，避免把底线当第一卖点。`
  }
  if (currentAction.value === '减') {
    return `顺序看主动减仓位、反抽位和保护位，不用一开始就把所有方案都摊开。`
  }
  return `顺序看守位、失守位和备用处理区，先确认还能不能继续拿。`
})
const summaryCards = computed(() => ([
  {
    label: '现价 / 浮盈',
    value: displayCurrentPrice.value,
    valueClass: currentPnlClass.value,
    tip: displayCurrentPnlPct.value === '-'
      ? '浮盈亏待确认'
      : `${Number(props.currentPnlPct ?? 0) >= 0 ? '当前浮盈' : '当前浮亏'} ${displayCurrentPnlPct.value}`,
  },
  {
    label: '环境 / 日线',
    value: `${basic.value?.market_env_tag || '-'} / ${daily.value?.sell_point_level || '-'}`,
    tip: `${daily.value?.current_stage || '-'} · ${basic.value?.stable_market_env_tag || basic.value?.market_env_tag || '-'}`,
  },
  {
    label: '分时 / 优先级',
    value: `${sanitizePendingText(intraday.value?.conclusion)} / ${accountContext.value?.priority || '-'}`,
    tip: sanitizePendingText(intraday.value?.intraday_structure, '当前待盘中确认'),
  },
]))
const intradayHeadline = computed(() => {
  const structure = sanitizePendingText(intraday.value?.intraday_structure, '当前待盘中确认')
  const conclusion = sanitizePendingText(intraday.value?.conclusion, '拿')
  const volume = sanitizePendingText(intraday.value?.volume_quality, '量能待确认')
  return `${conclusion}，当前分时看 ${structure}，量能侧重点是 ${volume}。`
})
const analysisSummary = computed(() => (
  `账户语境 ${accountContext.value?.context_summary || '-'} · 日线 ${daily.value?.sell_point_level || '-'} · 分时 ${sanitizePendingText(intraday.value?.conclusion)}`
))
const isActionableLevel = (value) => {
  const text = String(value || '').trim()
  if (!text || text === '-') return false
  return !text.includes('不适用')
}
const normalizeLevelValue = (value) => (isActionableLevel(value) ? String(value).trim() : '当前不设')
const sanitizePendingText = (value, fallback = '-') => {
  const text = String(value || '').trim()
  if (!text || text === '-') return fallback
  if (text.includes('需确认')) return fallback
  return text
}
const parseZone = (value) => {
  const text = String(value || '').trim()
  const match = text.match(/(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)/)
  if (!match) return null
  return { low: Number(match[1]), high: Number(match[2]) }
}
const reboundZoneMeta = computed(() => parseZone(orderPlan.value?.rebound_sell_price))
const currentPriceAboveReboundZone = computed(() => {
  if (props.currentPrice === null || props.currentPrice === undefined) return false
  if (!reboundZoneMeta.value) return false
  return Number(props.currentPrice) > reboundZoneMeta.value.high
})
const primaryOrderCardKey = computed(() => {
  const action = currentAction.value
  if (action === '清' && isActionableLevel(orderPlan.value?.priority_exit_price)) return 'priority_exit'
  if (action === '清' && isActionableLevel(orderPlan.value?.rebound_sell_price)) return 'rebound'
  if (action === '清' && isActionableLevel(orderPlan.value?.break_stop_price)) return 'stop'
  if (action === '减' && isActionableLevel(orderPlan.value?.proactive_take_profit_price)) return 'take_profit'
  if (action === '减' && isActionableLevel(orderPlan.value?.rebound_sell_price)) return 'rebound'
  if (action === '拿' && isActionableLevel(orderPlan.value?.observe_level)) return 'observe'
  if (isActionableLevel(orderPlan.value?.proactive_take_profit_price)) return 'take_profit'
  if (isActionableLevel(orderPlan.value?.rebound_sell_price)) return 'rebound'
  if (isActionableLevel(orderPlan.value?.break_stop_price)) return 'stop'
  if (isActionableLevel(orderPlan.value?.observe_level)) return 'observe'
  return 'take_profit'
})
const orderPlanSummary = computed(() => {
  const action = currentAction.value
  if (action === '清' && isActionableLevel(orderPlan.value?.priority_exit_price)) {
    return `最好先卖在 ${normalizeLevelValue(orderPlan.value?.priority_exit_price)}`
  }
  if (action === '清' && isActionableLevel(orderPlan.value?.rebound_sell_price)) {
    return `卖不到优先区，就看反抽区 ${normalizeLevelValue(orderPlan.value?.rebound_sell_price)}`
  }
  if (action === '清' && isActionableLevel(orderPlan.value?.break_stop_price)) {
    return `最晚别拖破 ${normalizeLevelValue(orderPlan.value?.break_stop_price)}`
  }
  if (action === '减' && isActionableLevel(orderPlan.value?.proactive_take_profit_price)) {
    return `最好先减在 ${normalizeLevelValue(orderPlan.value?.proactive_take_profit_price)}`
  }
  if (action === '减' && isActionableLevel(orderPlan.value?.rebound_sell_price)) return '先看反抽减仓位，再看失守保护位'
  if (action === '拿' && isActionableLevel(orderPlan.value?.observe_level)) {
    return `先盯守位 ${normalizeLevelValue(orderPlan.value?.observe_level)}`
  }
  return '先看启用中的价格位，再按顺序执行'
})
const orderPlanLeadTitle = computed(() => {
  if (currentAction.value === '清') return '最好卖在前面，不要拖到破位'
  if (currentAction.value === '减') return '先减在舒服的位置，不用死等最高点'
  return '先盯守位，守不住再动手'
})
const orderPlanLeadCopy = computed(() => {
  if (currentAction.value === '清') {
    if (isActionableLevel(orderPlan.value?.priority_exit_price)) {
      return `能卖在优先区就先卖，不要一路等到最后失效线；如果盘中只给一次弱反抽，再看反抽区借机走。`
    }
    if (isActionableLevel(orderPlan.value?.rebound_sell_price)) {
      return `如果没有更好的主动卖点，就盯反抽区先走；${normalizeLevelValue(orderPlan.value?.break_stop_price)} 只是最晚不能再拖的底线。`
    }
    return `${normalizeLevelValue(orderPlan.value?.break_stop_price)} 只是最晚不能再拖的位置，核心是早点退出，不是等它来提醒你。`
  }
  if (currentAction.value === '减') {
    if (isActionableLevel(orderPlan.value?.proactive_take_profit_price)) {
      if (currentPriceAboveReboundZone.value) {
        return `先看主动减仓区。当前价已经高于旧的反抽区，后面反抽区只当回落后的备选处理位。`
      }
      return `先看主动减仓区；如果冲高不成，再回到反抽区和底线位继续执行。`
    }
    if (currentPriceAboveReboundZone.value) {
      return `当前价已经高于反抽区，这一带更像回落后的补处理区，不是让你等股价掉回去才第一次减。`
    }
    return `优先看反抽减仓位，底线位只负责防止进一步恶化，不是第一减仓点。`
  }
  return `只要继续守住观察位，才值得继续拿；一旦失守，就按退出线处理。`
})
const orderPlanLeadTone = computed(() => {
  if (currentAction.value === '清') return 'danger'
  if (currentAction.value === '减') return 'warning'
  return 'info'
})
const orderPlanCards = computed(() => {
  const primaryKey = primaryOrderCardKey.value
  return [
    {
      key: 'priority_exit',
      label: '最好先卖区',
      scene: '能直接卖在这里就先走',
      value: normalizeLevelValue(orderPlan.value?.priority_exit_price),
      note: orderPlan.value?.priority_exit_condition || '当前没有明确的优先清仓区。',
      tone: 'danger',
      badge: isActionableLevel(orderPlan.value?.priority_exit_price)
        ? (primaryKey === 'priority_exit' ? '先处理' : '优先位')
        : '当前不设',
      active: isActionableLevel(orderPlan.value?.priority_exit_price),
      primary: primaryKey === 'priority_exit',
    },
    {
      key: 'take_profit',
      label: '最好先减区',
      scene: '冲高到这里更适合先减',
      value: normalizeLevelValue(orderPlan.value?.proactive_take_profit_price),
      note: orderPlan.value?.take_profit_condition || '当前没有明确的主动兑现触发条件。',
      tone: 'warm',
      badge: isActionableLevel(orderPlan.value?.proactive_take_profit_price) ? (primaryKey === 'take_profit' ? '先处理' : '备选') : '当前不设',
      active: isActionableLevel(orderPlan.value?.proactive_take_profit_price),
      primary: primaryKey === 'take_profit',
    },
    {
      key: 'rebound',
      label: currentAction.value === '清' ? '卖不到时看反抽区' : '减不到时看反抽区',
      scene: currentAction.value === '清' ? '只给弱反抽时借机走' : '只给弱反抽时借机减',
      value: normalizeLevelValue(orderPlan.value?.rebound_sell_price),
      note: currentAction.value === '减' && currentPriceAboveReboundZone.value
        ? '这段区间已经落在当前价下方，更适合后续回落到该带但站不稳时再参考，不是让你现在等回去才第一次减。'
        : (orderPlan.value?.rebound_condition || '没有反抽确认前，先不按这条执行。'),
      tone: 'reduce',
      badge: isActionableLevel(orderPlan.value?.rebound_sell_price)
        ? (primaryKey === 'rebound' ? '先处理' : currentAction.value === '清' ? '优先通道' : '备选')
        : '当前不设',
      active: isActionableLevel(orderPlan.value?.rebound_sell_price),
      primary: primaryKey === 'rebound',
    },
    {
      key: 'stop',
      label: currentAction.value === '清' ? '最晚不能拖到这' : '失守就得保护退',
      scene: currentAction.value === '清' ? '真到这里就别再拖' : '跌破后按保护动作走',
      value: normalizeLevelValue(orderPlan.value?.break_stop_price),
      note: orderPlan.value?.stop_condition || '当前没有明确的止损失效位。',
      tone: 'danger',
      badge: isActionableLevel(orderPlan.value?.break_stop_price)
        ? (primaryKey === 'stop' ? '先处理' : currentAction.value === '清' ? '最后底线' : '硬规则')
        : '当前不设',
      active: isActionableLevel(orderPlan.value?.break_stop_price),
      primary: primaryKey === 'stop',
    },
    {
      key: 'observe',
      label: '继续拿先看守位',
      scene: '守住这里才值得继续看',
      value: normalizeLevelValue(orderPlan.value?.observe_level),
      note: orderPlan.value?.hold_condition || '当前不建议继续以观察为主。',
      tone: 'observe',
      badge: isActionableLevel(orderPlan.value?.observe_level) ? (primaryKey === 'observe' ? '优先看' : '观察线') : '当前不设',
      active: isActionableLevel(orderPlan.value?.observe_level),
      primary: primaryKey === 'observe',
    },
  ]
})
const primaryOrderPlanCards = computed(() => {
  if (currentAction.value === '清') {
    return orderPlanCards.value.filter((card) => ['priority_exit', 'rebound', 'stop'].includes(card.key))
  }
  if (currentAction.value !== '拿') return orderPlanCards.value.filter((card) => card.key !== 'priority_exit')
  return orderPlanCards.value.filter((card) => ['observe', 'stop'].includes(card.key))
})
const backupOrderPlanCards = computed(() => {
  if (currentAction.value !== '拿') return []
  return orderPlanCards.value.filter((card) => card.active && ['rebound', 'take_profit'].includes(card.key))
})
const orderExecutionSteps = computed(() => (
  [
    primaryOrderCardKey.value,
    ...(['priority_exit', 'rebound', 'take_profit', 'stop', 'observe'].filter((key) => key !== primaryOrderCardKey.value)),
  ]
    .map((key) => primaryOrderPlanCards.value.find((card) => card.key === key))
    .filter(Boolean)
    .map((card) => ({
    key: card.key,
    title: `${card.label}：${card.value}`,
    note: card.note,
  }))
))
const takeProfitNoteLabel = computed(() => {
  if (currentAction.value === '清') return '如果盘中冲高，哪里能先处理'
  if (currentAction.value === '减') return '最好先减在哪'
  return '如果盘中转强，哪里可以先兑现'
})
const reboundNoteLabel = computed(() => {
  if (currentAction.value === '清') return '卖不到优先区时，退而求其次看哪'
  if (currentAction.value === '减') return '如果只给弱反抽，优先看哪减'
  return '如果只给弱反抽，哪里需要重新评估'
})
const stopNoteLabel = computed(() => (
  currentAction.value === '清' ? '最晚不能拖到哪' : '跌破哪就不能再硬扛'
))
const holdNoteLabel = computed(() => (
  currentAction.value === '清' ? '只有重新站回哪才值得再看' : '守住哪还能继续看'
))
const actionBadgeClass = computed(() => {
  if (execution.value?.action === '清') return 'badge-pass'
  if (execution.value?.action === '减') return 'badge-reduce'
  return 'badge-hold'
})

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

const loadData = async () => {
  if (!props.tsCode) return
  loading.value = true
  loadError.value = ''
  try {
    const res = await stockApi.sellAnalysis(props.tsCode, displayTradeDate.value, { timeout: 90000 })
    const payload = res.data || {}
    if (payload.code !== 200) {
      loadError.value = payload.message || '加载卖点 SOP 失败'
      data.value = null
      ElMessage.error(loadError.value)
      return
    }
    data.value = payload.data || null
  } catch (error) {
    const message = error?.response?.data?.message || error?.message || '加载卖点 SOP 失败'
    loadError.value = message
    data.value = null
    ElMessage.error(message)
  } finally {
    loading.value = false
  }
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

.drawer-body {
  display: grid;
  gap: 18px;
}

.overview-card {
  display: grid;
  gap: 16px;
  padding: 18px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(255, 122, 127, 0.14), transparent 36%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.04));
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.overview-top {
  display: flex;
  gap: 16px;
  align-items: center;
}

.overview-badge {
  min-width: 110px;
  padding: 16px 18px;
  border-radius: 18px;
  color: #fff;
  text-align: center;
  font-weight: 800;
  letter-spacing: 0.06em;
}

.badge-hold {
  background: linear-gradient(135deg, #1d8b6f, #2fcf9a);
}

.badge-reduce {
  background: linear-gradient(135deg, #d39b24, #f3c24d);
}

.badge-pass {
  background: linear-gradient(135deg, #d84d58, #ff7a7f);
}

.overview-copy {
  display: grid;
  gap: 8px;
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

.overview-title {
  font-size: 1.05rem;
  font-weight: 700;
}

.overview-desc,
.overview-conclusion,
.section-note {
  line-height: 1.7;
}

.overview-conclusion {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
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

.hero-card-hold .hero-value {
  color: #7ad7ff;
}

.hero-card-reduce .hero-value {
  color: #ffb454;
}

.hero-card-clear .hero-value {
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

.text-red {
  color: #ff7a7f;
}

.text-green {
  color: #46d0b6;
}

.text-neutral {
  color: var(--color-text-sec);
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
  gap: 16px;
}

.analysis-section {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.analysis-section-wide {
  grid-column: 1 / -1;
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

.order-plan-lead-danger {
  background: rgba(255, 122, 127, 0.08);
  border-color: rgba(255, 122, 127, 0.24);
}

.order-plan-lead-warning {
  background: rgba(255, 196, 64, 0.08);
  border-color: rgba(255, 196, 64, 0.22);
}

.order-plan-lead-info {
  background: rgba(122, 215, 255, 0.08);
  border-color: rgba(122, 215, 255, 0.2);
}

.data-list {
  display: grid;
  gap: 8px;
}

.intraday-headline {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.intraday-headline strong {
  font-size: 14px;
}

.intraday-headline span {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.data-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.data-item span {
  color: var(--color-text-sec);
  flex-shrink: 0;
}

.data-item strong {
  text-align: right;
}

.price-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.order-plan-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.order-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.order-card-primary {
  border-color: rgba(255, 196, 64, 0.4);
  box-shadow: 0 0 0 1px rgba(255, 196, 64, 0.16) inset;
}

.order-card-inactive {
  opacity: 0.72;
}

.order-card-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.order-card-label {
  font-size: 13px;
  color: var(--color-text-sec);
}

.order-card-scene {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-sec);
}

.order-card-badge {
  flex-shrink: 0;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1;
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-text-main);
}

.order-card-price {
  font-size: 1.65rem;
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: 0.01em;
  font-variant-numeric: tabular-nums;
}

.order-card-price-empty {
  font-size: 1.2rem;
  color: var(--color-text-sec);
}

.order-card-note {
  line-height: 1.7;
}

.order-card-warm .order-card-price {
  color: #ffd166;
}

.order-card-reduce .order-card-price {
  color: #ffb454;
}

.order-card-danger .order-card-price {
  color: #ff7a7f;
}

.order-card-observe .order-card-price {
  color: #7ad7ff;
}

.order-plan-flow {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.order-plan-backup {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px dashed rgba(255, 255, 255, 0.1);
}

.backup-card-list {
  display: grid;
  gap: 10px;
}

.backup-card {
  display: grid;
  gap: 4px;
}

.backup-card strong {
  font-size: 13px;
}

.backup-card span {
  color: var(--color-text-sec);
  line-height: 1.6;
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

.order-flow-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-sec);
}

.order-flow-list {
  display: grid;
  gap: 10px;
}

.order-flow-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.order-flow-index {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.08);
  font-size: 12px;
  font-weight: 700;
}

.order-flow-copy {
  display: grid;
  gap: 3px;
}

.order-flow-copy strong {
  font-size: 13px;
}

.order-flow-copy span {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.plan-notes-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px;
}

.section-emphasis {
  font-weight: 700;
  line-height: 1.7;
}

@media (max-width: 1200px) {
  .drawer-header,
  .overview-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .overview-main-grid,
  .overview-grid,
  .section-grid,
  .price-grid,
  .order-plan-grid,
  .plan-notes-grid {
    grid-template-columns: 1fr;
  }

  .data-item {
    flex-direction: column;
  }
}
</style>
