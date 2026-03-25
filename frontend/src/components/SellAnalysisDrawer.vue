<template>
  <el-drawer
    :model-value="modelValue"
    size="56%"
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

          <section class="analysis-section">
            <div class="section-header">4）挂单价格</div>
            <div class="price-grid">
              <div class="metric-card"><span>主动兑现价</span><strong>{{ orderPlan?.proactive_take_profit_price || '-' }}</strong></div>
              <div class="metric-card"><span>反抽卖出价</span><strong>{{ orderPlan?.rebound_sell_price || '-' }}</strong></div>
              <div class="metric-card"><span>失守止损价</span><strong>{{ orderPlan?.break_stop_price || '-' }}</strong></div>
              <div class="metric-card"><span>条件观察位</span><strong>{{ orderPlan?.observe_level || '-' }}</strong></div>
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
  tradeDate: { type: String, default: '' }
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
    data.value = res.data.data || null
  } catch (error) {
    ElMessage.error('加载卖点 SOP 失败')
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
  grid-template-columns: repeat(4, minmax(0, 1fr));
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

.section-header {
  font-size: 15px;
  font-weight: 700;
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
  .price-grid {
    grid-template-columns: 1fr;
  }

  .data-item {
    flex-direction: column;
  }
}
</style>
