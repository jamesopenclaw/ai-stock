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
      <el-skeleton v-else-if="loading" :rows="14" animated />
      <el-empty v-else-if="!data" description="暂无卖点分析结果" />
      <template v-else>
        <div class="overview-card">
          <div class="overview-top">
            <div class="overview-badge" :class="actionBadgeClass">
              {{ execution?.action || '拿' }}
            </div>
            <div class="overview-copy">
              <div class="overview-title">
                {{ basic?.sell_signal_tag || '-' }} / {{ basic?.sell_point_type || '-' }}
              </div>
              <div class="overview-desc">{{ execution?.reason || '-' }}</div>
              <div class="overview-conclusion">
                {{ execution?.partial_plan || '-' }}
              </div>
            </div>
          </div>

          <div class="overview-grid">
            <div class="summary-card">
              <span class="summary-label">最新价</span>
              <strong class="summary-value">{{ displayCurrentPrice }}</strong>
              <span class="summary-tip" :class="currentPnlClass">当前浮盈 {{ displayCurrentPnlPct }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">环境</span>
              <strong class="summary-value">{{ basic?.market_env_tag || '-' }}</strong>
              <span class="summary-tip">{{ marketEnvSummary }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">日线级别</span>
              <strong class="summary-value">{{ daily?.sell_point_level || '-' }}</strong>
              <span class="summary-tip">{{ daily?.current_stage || '-' }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">分时结论</span>
              <strong class="summary-value">{{ intraday?.conclusion || '-' }}</strong>
              <span class="summary-tip">{{ intraday?.intraday_structure || '-' }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">重点位</span>
              <strong class="summary-value">{{ execution?.key_level || '-' }}</strong>
              <span class="summary-tip">{{ accountContext?.priority || '-' }}</span>
            </div>
          </div>

          <div class="quote-strip">
            <span>{{ quoteMeta }}</span>
          </div>
        </div>

        <div class="section-grid">
          <section class="analysis-section">
            <div class="section-header">1）账户语境</div>
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
            <div class="section-header">2）日线卖点级别</div>
            <div class="data-list">
              <div class="data-item"><span>当前阶段</span><strong>{{ daily?.current_stage || '-' }}</strong></div>
              <div class="data-item"><span>卖点信号</span><strong>{{ daily?.sell_signal || '-' }}</strong></div>
              <div class="data-item"><span>卖点级别</span><strong>{{ daily?.sell_point_level || '-' }}</strong></div>
            </div>
            <div class="section-note">{{ daily?.reason || '-' }}</div>
          </section>

          <section class="analysis-section">
            <div class="section-header">3）分时执行判断</div>
            <div class="data-list">
              <div class="data-item"><span>均价线关系</span><strong>{{ intraday?.price_vs_avg_line || '-' }}</strong></div>
              <div class="data-item"><span>分时结构</span><strong>{{ intraday?.intraday_structure || '-' }}</strong></div>
              <div class="data-item"><span>量能性质</span><strong>{{ intraday?.volume_quality || '-' }}</strong></div>
              <div class="data-item"><span>当前结论</span><strong>{{ intraday?.conclusion || '-' }}</strong></div>
            </div>
            <div class="section-note">{{ intraday?.note || '-' }}</div>
          </section>

          <section class="analysis-section order-plan-section">
            <div class="section-header-row">
              <div class="section-header">4）挂单价格</div>
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
            <div class="section-note">冲到哪里先兑现：{{ orderPlan?.take_profit_condition || '-' }}</div>
            <div class="section-note">弱反抽到哪里减：{{ orderPlan?.rebound_condition || '-' }}</div>
            <div class="section-note">跌破哪里不再幻想：{{ orderPlan?.stop_condition || '-' }}</div>
            <div class="section-note">守住哪里还能继续看：{{ orderPlan?.hold_condition || '-' }}</div>
          </section>

          <section class="analysis-section analysis-section-full">
            <div class="section-header">5）一句话执行</div>
            <div class="final-line">{{ execution?.action || '-' }}</div>
            <div class="section-note">是否分批：{{ execution?.partial_plan || '-' }}</div>
            <div class="section-note">重点盯哪个位：{{ execution?.key_level || '-' }}</div>
            <div class="section-emphasis">{{ execution?.reason || '-' }}</div>
          </section>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { stockApi } from '../api'

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
const marketEnvSummary = computed(() => {
  const realtimeTag = basic.value?.realtime_market_env_tag || basic.value?.market_env_tag || '-'
  const stableTag = basic.value?.stable_market_env_tag || '-'
  const contextSummary = accountContext.value?.context_summary || '-'
  return `实时${realtimeTag} / 稳定${stableTag} · ${contextSummary}`
})
const quoteMeta = computed(() => {
  const source = basic.value?.data_source
  const quoteTime = basic.value?.quote_time
  const sourceLabel = source && String(source).startsWith('realtime_') ? '盘中实时' : '日线回退'
  if (quoteTime) return `${sourceLabel} ${quoteTime}`
  return `${sourceLabel} ${displayTradeDate.value}`
})
const currentAction = computed(() => execution.value?.action || '拿')
const isActionableLevel = (value) => {
  const text = String(value || '').trim()
  if (!text || text === '-') return false
  return !text.includes('不适用')
}
const normalizeLevelValue = (value) => (isActionableLevel(value) ? String(value).trim() : '当前不设')
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
  if (action === '清' && isActionableLevel(orderPlan.value?.rebound_sell_price)) {
    return `先看反抽区 ${normalizeLevelValue(orderPlan.value?.rebound_sell_price)}`
  }
  if (action === '清' && isActionableLevel(orderPlan.value?.break_stop_price)) {
    return `${normalizeLevelValue(orderPlan.value?.break_stop_price)} 是最后失效线`
  }
  if (action === '减' && isActionableLevel(orderPlan.value?.proactive_take_profit_price)) {
    return `先看兑现区 ${normalizeLevelValue(orderPlan.value?.proactive_take_profit_price)}`
  }
  if (action === '减' && isActionableLevel(orderPlan.value?.rebound_sell_price)) return '当前以反抽减仓和失守保护为主'
  if (action === '拿' && isActionableLevel(orderPlan.value?.observe_level)) {
    return `先看观察位 ${normalizeLevelValue(orderPlan.value?.observe_level)}`
  }
  return '先看启用中的价格位，再按顺序执行'
})
const orderPlanLeadTitle = computed(() => {
  if (currentAction.value === '清') return '这不是“再等等”的票'
  if (currentAction.value === '减') return '这票优先降风险，不必纠结最高点'
  return '这票当前先看守位，再决定要不要动'
})
const orderPlanLeadCopy = computed(() => {
  if (currentAction.value === '清') {
    if (isActionableLevel(orderPlan.value?.rebound_sell_price)) {
      return `优先按反抽卖出区处理；${normalizeLevelValue(orderPlan.value?.break_stop_price)} 只是最后底线，不是建议继续死等到那个位置。`
    }
    return `${normalizeLevelValue(orderPlan.value?.break_stop_price)} 是最后失效线，核心是提升退出效率，不是继续拖。`
  }
  if (currentAction.value === '减') {
    if (isActionableLevel(orderPlan.value?.proactive_take_profit_price)) {
      if (currentPriceAboveReboundZone.value) {
        return `先看主动兑现区。当前价已经高于旧的反抽区，反抽区只作为后续回落时的次级减仓参考。`
      }
      return `先看主动兑现区；如果冲高不成，再回到反抽区和底线位继续执行。`
    }
    if (currentPriceAboveReboundZone.value) {
      return `当前价已经高于反抽区，这一带更像“回落后的参考区”，不是让你等股价掉回去才第一次减。`
    }
    return `优先看反抽减仓位，底线位只负责防止进一步恶化。`
  }
  return `只要继续守住观察位，才有继续拿的理由；一旦失守，就按退出线处理。`
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
      key: 'take_profit',
      label: '主动兑现价',
      scene: '强势冲高时先兑现',
      value: normalizeLevelValue(orderPlan.value?.proactive_take_profit_price),
      note: orderPlan.value?.take_profit_condition || '当前没有明确的主动兑现触发条件。',
      tone: 'warm',
      badge: isActionableLevel(orderPlan.value?.proactive_take_profit_price) ? (primaryKey === 'take_profit' ? '先处理' : '备选') : '当前不设',
      active: isActionableLevel(orderPlan.value?.proactive_take_profit_price),
      primary: primaryKey === 'take_profit',
    },
    {
      key: 'rebound',
      label: currentAction.value === '清' ? '反抽退出价' : '反抽卖出价',
      scene: currentAction.value === '清' ? '弱反抽时借机退出' : '弱反抽时借机减仓',
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
      label: currentAction.value === '清' ? '最后失效线' : '失守止损价',
      scene: currentAction.value === '清' ? '如果还没处理，再破就不能拖' : '跌破后保护退出',
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
      label: '条件观察位',
      scene: '守住才继续看',
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
  if (currentAction.value !== '拿') return orderPlanCards.value
  return orderPlanCards.value.filter((card) => ['observe', 'stop'].includes(card.key))
})
const backupOrderPlanCards = computed(() => {
  if (currentAction.value !== '拿') return []
  return orderPlanCards.value.filter((card) => card.active && ['rebound', 'take_profit'].includes(card.key))
})
const orderExecutionSteps = computed(() => (
  [
    primaryOrderCardKey.value,
    ...(['rebound', 'take_profit', 'stop', 'observe'].filter((key) => key !== primaryOrderCardKey.value)),
  ]
    .map((key) => primaryOrderPlanCards.value.find((card) => card.key === key))
    .filter(Boolean)
    .map((card) => ({
    key: card.key,
    title: `${card.label}：${card.value}`,
    note: card.note,
  }))
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
  try {
    const res = await stockApi.sellAnalysis(props.tsCode, displayTradeDate.value)
    const payload = res.data || {}
    if (payload.code !== 200) {
      ElMessage.error(payload.message || '加载卖点 SOP 失败')
      return
    }
    data.value = payload.data || null
  } catch (error) {
    const message = error?.response?.data?.message || error?.message || '加载卖点 SOP 失败'
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

.overview-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.summary-card,
.metric-card {
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

.analysis-section-full {
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
  grid-template-columns: repeat(2, minmax(0, 1fr));
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

.section-emphasis,
.final-line {
  font-weight: 700;
  line-height: 1.7;
}

@media (max-width: 1200px) {
  .drawer-header,
  .overview-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .overview-grid,
  .section-grid,
  .price-grid,
  .order-plan-grid {
    grid-template-columns: 1fr;
  }

  .data-item {
    flex-direction: column;
  }
}
</style>
