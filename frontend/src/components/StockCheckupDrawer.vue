<template>
  <el-drawer
    :model-value="modelValue"
    size="62%"
    :destroy-on-close="false"
    class="stock-checkup-drawer"
    @close="handleClose"
  >
    <template #header>
      <div class="drawer-header">
        <div class="header-main">
          <div class="header-title">{{ headerTitle }}</div>
          <div class="header-meta">
            <span>{{ tsCode || '-' }}</span>
            <span v-if="displayTradeDate">体检日 {{ displayTradeDate }}</span>
            <span v-if="data?.resolved_trade_date && data.resolved_trade_date !== displayTradeDate">
              实际行情日 {{ data.resolved_trade_date }}
            </span>
          </div>
        </div>
        <div class="header-actions">
          <el-radio-group v-model="activeTarget" size="small">
            <el-radio-button label="观察型" />
            <el-radio-button label="持仓型" />
            <el-radio-button label="交易型" />
          </el-radio-group>
          <el-button @click="loadData()" :loading="loading">刷新</el-button>
          <el-button @click="refreshLlm()" :loading="llmRefreshing" type="primary" plain>刷新解读</el-button>
        </div>
      </div>
    </template>

    <div class="drawer-body">
      <el-empty v-if="!tsCode" description="请选择一只股票后再查看体检" />
      <el-skeleton v-else-if="loading" :rows="16" animated />
      <el-empty v-else-if="!data" description="暂无体检结果" />
      <template v-else>
        <div class="overview-card">
          <div class="overview-top">
            <div class="overview-badge" :class="strategyBadgeClass">
              {{ rule?.strategy?.current_strategy || '观察' }}
            </div>
            <div class="overview-copy">
              <div class="overview-title">
                {{ rule?.strategy?.current_characterization || '-' }} / {{ rule?.strategy?.current_role || '-' }}
              </div>
              <div class="overview-desc">
                {{ llm?.overall_summary || rule?.strategy?.strategy_reason || '-' }}
              </div>
              <div class="overview-conclusion">
                {{ llm?.one_line_conclusion || rule?.final_conclusion?.one_line_conclusion || '-' }}
              </div>
            </div>
          </div>

          <div class="overview-grid">
            <div class="summary-card">
              <span class="summary-label">市场</span>
              <strong class="summary-value">{{ rule?.market_context?.market_env_tag || '-' }}</strong>
              <span class="summary-tip">{{ rule?.market_context?.stock_market_alignment || '-' }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">地位</span>
              <strong class="summary-value">{{ rule?.direction_position?.stock_role || '-' }}</strong>
              <span class="summary-tip">{{ rule?.direction_position?.sector_level || '-' }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">结构</span>
              <strong class="summary-value">{{ rule?.daily_structure?.stage_position || '-' }}</strong>
              <span class="summary-tip">{{ rule?.daily_structure?.structure_conclusion || '-' }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">风险</span>
              <strong class="summary-value">{{ (llm?.key_risks?.length || rule?.strategy?.risk_points?.length || 0) }}</strong>
              <span class="summary-tip">{{ riskPreview }}</span>
            </div>
          </div>

          <div v-if="llmStatusVisible" class="llm-status" :class="llmStatusClass">
            <span class="llm-status-label">LLM 状态</span>
            <span class="llm-status-text">{{ llmStatusText }}</span>
          </div>
        </div>

        <div class="section-grid">
          <section class="checkup-section">
            <div class="section-header">1）基本信息</div>
            <div class="data-list">
              <div class="data-item"><span>名称 / 代码</span><strong>{{ rule?.basic_info?.stock_name || '-' }} / {{ rule?.basic_info?.ts_code || '-' }}</strong></div>
              <div class="data-item"><span>行业 / 板块</span><strong>{{ rule?.basic_info?.sector_name || '-' }}</strong></div>
              <div class="data-item"><span>板块属性</span><strong>{{ rule?.basic_info?.board || '-' }}</strong></div>
              <div class="data-item"><span>特殊属性</span><strong>{{ joinList(rule?.basic_info?.special_tags) }}</strong></div>
            </div>
            <div class="llm-copy">{{ reportContent('basic_info') }}</div>
          </section>

          <section class="checkup-section">
            <div class="section-header">2）市场环境</div>
            <div class="data-list">
              <div class="data-item"><span>当前市场状态</span><strong>{{ rule?.market_context?.market_phase || '-' }}</strong></div>
              <div class="data-item"><span>顺势 / 逆势</span><strong>{{ rule?.market_context?.stock_market_alignment || '-' }}</strong></div>
              <div class="data-item"><span>容错率</span><strong>{{ rule?.market_context?.tolerance_comment || '-' }}</strong></div>
            </div>
            <div class="section-note">{{ rule?.market_context?.market_comment || '-' }}</div>
            <div class="llm-copy">{{ reportContent('market_context') }}</div>
          </section>

          <section class="checkup-section">
            <div class="section-header">3）方向地位</div>
            <div class="data-list">
              <div class="data-item"><span>所属方向</span><strong>{{ rule?.direction_position?.direction_name || '-' }}</strong></div>
              <div class="data-item"><span>板块级别</span><strong>{{ rule?.direction_position?.sector_level || '-' }}</strong></div>
              <div class="data-item"><span>板块状态</span><strong>{{ rule?.direction_position?.sector_trend || '-' }}</strong></div>
              <div class="data-item"><span>个股地位</span><strong>{{ rule?.direction_position?.stock_role || '-' }}</strong></div>
            </div>
            <div class="section-note">{{ rule?.direction_position?.relative_strength || '-' }}</div>
            <div class="llm-copy">{{ reportContent('direction_position') }}</div>
          </section>

          <section class="checkup-section">
            <div class="section-header">4）日线结构</div>
            <div class="data-list">
              <div class="data-item"><span>均线位置</span><strong>{{ rule?.daily_structure?.ma_position_summary || '-' }}</strong></div>
              <div class="data-item"><span>阶段位置</span><strong>{{ rule?.daily_structure?.stage_position || '-' }}</strong></div>
              <div class="data-item"><span>20日区间</span><strong>{{ rule?.daily_structure?.range_position_20d || '-' }}</strong></div>
              <div class="data-item"><span>60日区间</span><strong>{{ rule?.daily_structure?.range_position_60d || '-' }}</strong></div>
            </div>
            <div class="section-note">{{ rule?.daily_structure?.pattern_integrity || '-' }}</div>
            <div class="section-emphasis">{{ rule?.daily_structure?.structure_conclusion || '-' }}</div>
            <div class="llm-copy">{{ reportContent('daily_structure') }}</div>
          </section>

          <section class="checkup-section">
            <div class="section-header">5）短线强度</div>
            <div class="metric-grid">
              <div class="metric-card"><span>涨跌幅</span><strong :class="pctClass(rule?.intraday_strength?.change_pct)">{{ formatSignedPct(rule?.intraday_strength?.change_pct) }}</strong></div>
              <div class="metric-card"><span>换手率</span><strong>{{ formatPct(rule?.intraday_strength?.turnover_rate) }}</strong></div>
              <div class="metric-card"><span>量比</span><strong>{{ formatNumber(rule?.intraday_strength?.vol_ratio) }}</strong></div>
              <div class="metric-card"><span>强度结论</span><strong>{{ rule?.intraday_strength?.strength_level || '-' }}</strong></div>
            </div>
            <div class="section-note">{{ rule?.intraday_strength?.candle_label || '-' }} / {{ rule?.intraday_strength?.close_position || '-' }} / {{ rule?.intraday_strength?.volume_state || '-' }}</div>
            <div class="llm-copy">{{ reportContent('intraday_strength') }}</div>
          </section>

          <section class="checkup-section">
            <div class="section-header">6）资金质量</div>
            <div class="data-list">
              <div class="data-item"><span>最近资金变化</span><strong>{{ rule?.fund_quality?.recent_fund_flow || '-' }}</strong></div>
              <div class="data-item"><span>今日资金性质</span><strong>{{ rule?.fund_quality?.cash_flow_quality || '-' }}</strong></div>
              <div class="data-item"><span>大单参与</span><strong>{{ rule?.fund_quality?.big_order_status || '-' }}</strong></div>
              <div class="data-item"><span>放量特征</span><strong>{{ rule?.fund_quality?.volume_behavior || '-' }}</strong></div>
            </div>
            <div class="llm-copy">{{ reportContent('fund_quality') }}</div>
          </section>

          <section class="checkup-section">
            <div class="section-header">7）同类对比</div>
            <div class="peer-summary">
              {{ rule?.peer_comparison?.relative_strength || '-' }} / {{ rule?.peer_comparison?.recognizability || '-' }}
            </div>
            <div v-if="rule?.peer_comparison?.peers?.length" class="peer-list">
              <div v-for="peer in rule.peer_comparison.peers" :key="peer.ts_code" class="peer-row">
                <div class="peer-main">
                  <strong>{{ peer.stock_name }}</strong>
                  <span>{{ peer.ts_code }}</span>
                </div>
                <div class="peer-side">
                  <span :class="pctClass(peer.change_pct)">{{ formatSignedPct(peer.change_pct) }}</span>
                  <span>{{ peer.role_hint || '-' }}</span>
                </div>
              </div>
            </div>
            <div v-else class="section-note">暂无足够同类样本。</div>
            <div class="section-note">{{ rule?.peer_comparison?.note || '-' }}</div>
            <div class="llm-copy">{{ reportContent('peer_comparison') }}</div>
          </section>

          <section class="checkup-section">
            <div class="section-header">8）估值与属性</div>
            <div class="metric-grid">
              <div class="metric-card"><span>PE</span><strong>{{ formatNumber(rule?.valuation_profile?.pe) }}</strong></div>
              <div class="metric-card"><span>PB</span><strong>{{ formatNumber(rule?.valuation_profile?.pb) }}</strong></div>
              <div class="metric-card"><span>PS</span><strong>{{ formatNumber(rule?.valuation_profile?.ps) }}</strong></div>
              <div class="metric-card"><span>市值(亿)</span><strong>{{ formatNumber(rule?.valuation_profile?.market_value) }}</strong></div>
            </div>
            <div class="section-note">{{ rule?.valuation_profile?.valuation_level || '-' }} / {{ rule?.valuation_profile?.drive_type || '-' }}</div>
            <div class="llm-copy">{{ reportContent('valuation_profile') }}</div>
          </section>

          <section class="checkup-section">
            <div class="section-header">9）关键位</div>
            <div class="data-list">
              <div class="data-item"><span>压力位</span><strong>{{ joinPrices(rule?.key_levels?.pressure_levels) }}</strong></div>
              <div class="data-item"><span>支撑位</span><strong>{{ joinPrices(rule?.key_levels?.support_levels) }}</strong></div>
              <div class="data-item"><span>防守位</span><strong>{{ formatPrice(rule?.key_levels?.defense_level) }}</strong></div>
            </div>
            <div class="section-note">{{ rule?.key_levels?.note || '-' }}</div>
            <div class="llm-copy">{{ reportContent('key_levels') }}</div>
          </section>

          <section class="checkup-section">
            <div class="section-header">10）策略结论</div>
            <div class="strategy-pill" :class="strategyBadgeClass">{{ rule?.strategy?.current_strategy || '-' }}</div>
            <div class="section-emphasis">{{ rule?.strategy?.strategy_reason || '-' }}</div>
            <div v-if="rule?.buy_view" class="sub-panel">
              <div class="sub-title">交易视角</div>
              <div class="sub-copy">{{ rule.buy_view.buy_signal_tag || '-' }} / {{ rule.buy_view.buy_point_type || '-' }}</div>
              <div class="sub-copy">{{ rule.buy_view.buy_trigger_cond || '-' }}</div>
            </div>
            <div v-if="rule?.sell_view" class="sub-panel">
              <div class="sub-title">持仓视角</div>
              <div class="sub-copy">{{ rule.sell_view.sell_signal_tag || '-' }} / {{ rule.sell_view.sell_point_type || '-' }}</div>
              <div class="sub-copy">{{ rule.sell_view.sell_reason || '-' }}</div>
            </div>
            <div class="risk-list">
              <span v-for="risk in rule?.strategy?.risk_points || []" :key="risk" class="risk-chip">{{ risk }}</span>
            </div>
            <div class="llm-copy">{{ reportContent('strategy') }}</div>
          </section>

          <section class="checkup-section checkup-section-full">
            <div class="section-header">11）一句话结论</div>
            <div class="final-line">{{ llm?.one_line_conclusion || rule?.final_conclusion?.one_line_conclusion || '-' }}</div>
            <div class="llm-copy">{{ reportContent('final_conclusion') }}</div>
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
  defaultTarget: { type: String, default: '观察型' }
})

const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const llmRefreshing = ref(false)
const activeTarget = ref('观察型')
const data = ref(null)
const CHECKUP_TIMEOUT = 120000

const rule = computed(() => data.value?.rule_snapshot || null)
const llm = computed(() => data.value?.llm_report || null)
const displayTradeDate = computed(() => props.tradeDate || getLocalDate())
const headerTitle = computed(() => `${props.stockName || '个股'}全面体检`)
const llmStatus = computed(() => data.value?.llm_status || null)
const llmStatusVisible = computed(() => Boolean(llmStatus.value))
const llmStatusClass = computed(() => {
  if (llmStatus.value?.success) return 'llm-status-success'
  if (llmStatus.value?.enabled) return 'llm-status-warning'
  return 'llm-status-muted'
})
const llmStatusText = computed(() => {
  if (!llmStatus.value) return ''
  return llmStatus.value.message || (llmStatus.value.success ? 'LLM 体检已生效' : 'LLM 当前未生效')
})
const strategyBadgeClass = computed(() => {
  const strategy = rule.value?.strategy?.current_strategy
  if (strategy === '低吸') return 'badge-buy'
  if (strategy === '突破确认') return 'badge-break'
  if (strategy === '放弃') return 'badge-pass'
  return 'badge-watch'
})
const riskPreview = computed(() => {
  const risks = llm.value?.key_risks?.length ? llm.value.key_risks : (rule.value?.strategy?.risk_points || [])
  return risks.slice(0, 2).join(' / ') || '-'
})

watch(
  () => [props.modelValue, props.tsCode, props.defaultTarget],
  ([visible, tsCode, defaultTarget]) => {
    if (!visible) return
    activeTarget.value = defaultTarget || '观察型'
    if (tsCode) loadData()
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
  const forceLlmRefresh = Boolean(options.forceLlmRefresh)
  if (forceLlmRefresh) llmRefreshing.value = true
  else loading.value = true
  try {
    const res = await stockApi.checkup(
      props.tsCode,
      displayTradeDate.value,
      activeTarget.value,
      { forceLlmRefresh, timeout: CHECKUP_TIMEOUT }
    )
    const payload = res.data || {}
    if (payload.code && payload.code !== 200) {
      throw new Error(payload.message || '加载个股体检失败')
    }
    data.value = payload.data || null
  } catch (error) {
    data.value = null
    const isTimeout = error?.code === 'ECONNABORTED' || String(error?.message || '').toLowerCase().includes('timeout')
    ElMessage.error(isTimeout ? '个股体检超时，请稍后重试' : (error?.message || '加载个股体检失败'))
  } finally {
    loading.value = false
    llmRefreshing.value = false
  }
}

const refreshLlm = async () => {
  await loadData({ forceLlmRefresh: true })
}

const reportContent = (key) => {
  const section = llm.value?.llm_report_sections?.find((item) => item.key === key)
  return section?.content || '-'
}

const joinList = (items) => (items?.length ? items.join(' / ') : '-')
const joinPrices = (items) => (items?.length ? items.map((item) => formatPrice(item)).join(' / ') : '-')

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(2)
}

const formatPrice = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(2)
}

const formatPct = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toFixed(2)}%`
}

const formatSignedPct = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const num = Number(value)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const pctClass = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return ''
  if (Number(value) > 0) return 'text-red'
  if (Number(value) < 0) return 'text-green'
  return 'text-neutral'
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

.header-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
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
    radial-gradient(circle at top right, rgba(88, 176, 255, 0.14), transparent 36%),
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

.badge-buy {
  background: linear-gradient(135deg, #1d8b6f, #2fcf9a);
}

.badge-break {
  background: linear-gradient(135deg, #4f76d9, #67a5ff);
}

.badge-watch {
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
.overview-conclusion {
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
.metric-card,
.sub-panel {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.summary-label,
.sub-title {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.summary-value {
  font-size: 1.5rem;
  line-height: 1;
}

.summary-tip,
.section-note,
.sub-copy {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.llm-status {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.llm-status-label {
  font-size: 11px;
  color: var(--color-text-sec);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.llm-status-success {
  border-color: rgba(47, 207, 154, 0.25);
  background: rgba(47, 207, 154, 0.08);
}

.llm-status-warning {
  border-color: rgba(243, 194, 77, 0.25);
  background: rgba(243, 194, 77, 0.08);
}

.llm-status-muted {
  border-color: rgba(255, 255, 255, 0.08);
}

.section-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.checkup-section {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.checkup-section-full {
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

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.peer-summary,
.strategy-pill,
.section-emphasis,
.final-line {
  font-weight: 700;
  line-height: 1.7;
}

.peer-list {
  display: grid;
  gap: 8px;
}

.peer-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}

.peer-main,
.peer-side {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.strategy-pill {
  display: inline-flex;
  width: fit-content;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
}

.risk-list {
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

.llm-copy {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(88, 176, 255, 0.08);
  border: 1px solid rgba(88, 176, 255, 0.16);
  line-height: 1.7;
}

.text-red {
  color: #ff7b86;
}

.text-green {
  color: #35c48b;
}

.text-neutral {
  color: var(--color-text-pri);
}

@media (max-width: 1200px) {
  .drawer-header,
  .overview-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .overview-grid,
  .section-grid,
  .metric-grid {
    grid-template-columns: 1fr;
  }

  .data-item,
  .peer-row {
    flex-direction: column;
  }
}
</style>
