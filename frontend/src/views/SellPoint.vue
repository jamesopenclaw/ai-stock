<template>
  <div class="sell-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>卖点分析</span>
            <span v-if="displayDate" class="header-date">{{ displayDate }}</span>
          </div>
          <div class="header-actions">
            <el-button @click="loadData({ refresh: true })" :loading="loading">刷新</el-button>
            <el-button @click="refreshLlm()" :loading="llmRefreshing" type="primary" plain>刷新解读</el-button>
          </div>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="8" animated />
      <template v-else>
        <el-alert
          v-if="loadError"
          :title="loadError"
          type="error"
          show-icon
          :closable="false"
          class="load-error-alert"
        />
        <div class="decision-overview">
          <div class="overview-copy">
            <div class="overview-title">{{ sellHeadline }}</div>
            <div class="overview-desc">{{ sellGuidance }}</div>
            <div v-if="sellData.llm_summary?.page_summary" class="overview-llm">
              {{ sellData.llm_summary.page_summary }}
            </div>
          </div>
          <div class="overview-stats">
            <div class="stat-card stat-sell">
              <span class="stat-label">建议卖出</span>
              <strong class="stat-value">{{ sellData.sell_positions?.length || 0 }}</strong>
              <span class="stat-tip">优先处理</span>
            </div>
            <div class="stat-card stat-reduce">
              <span class="stat-label">建议减仓</span>
              <strong class="stat-value">{{ sellData.reduce_positions?.length || 0 }}</strong>
              <span class="stat-tip">先降风险</span>
            </div>
            <div class="stat-card stat-hold">
              <span class="stat-label">持有观察</span>
              <strong class="stat-value">{{ sellData.hold_positions?.length || 0 }}</strong>
              <span class="stat-tip">继续跟踪</span>
            </div>
          </div>
          <div class="overview-rules">
            <div v-for="rule in sellChecklist" :key="rule" class="rule-chip">{{ rule }}</div>
          </div>
          <div v-if="addSignalCount" class="overview-add-signals">
            <span class="add-signal-pill add-signal-pill-strong">建议加仓 {{ addSuggestionCount }}</span>
            <span v-if="addSmallAddCount" class="add-signal-pill add-signal-pill-watch">仅可小加 {{ addSmallAddCount }}</span>
            <span v-if="addWatchCount" class="add-signal-pill add-signal-pill-watch">可关注加仓 {{ addWatchCount }}</span>
          </div>
          <div v-if="llmStatusVisible" class="llm-status" :class="llmStatusClass">
            <span class="llm-status-label">LLM 状态</span>
            <span class="llm-status-text">{{ llmStatusText }}</span>
          </div>
          <div v-if="sellData.llm_summary?.action_summary" class="overview-action-summary">
            <span class="summary-kicker">LLM 摘要</span>
            <span>{{ sellData.llm_summary.action_summary }}</span>
          </div>
          <div v-if="topActions.length" class="top-actions">
            <div class="top-actions-title">今天先处理</div>
            <div class="top-actions-list">
              <div v-for="item in topActions" :key="item.ts_code" class="top-action-item">
                <span class="top-action-rank">{{ item.rank }}</span>
                <div class="top-action-main">
                  <strong>{{ item.orderLabel }}{{ item.stock_name }}</strong>
                  <span class="top-action-meta">{{ item.sell_signal_tag }} / {{ item.sell_priority }}优先 / {{ formatSignedPct(item.pnl_pct) }}</span>
                </div>
                <div class="top-action-trigger">
                  <span class="top-action-trigger-label">动手条件</span>
                  <span class="top-action-reason">{{ topActionReason(item) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <el-tabs v-model="activeTab">
          <el-tab-pane name="sell">
            <template #label>
              <span>建议卖出 <em class="tab-count">{{ sellData.sell_positions?.length || 0 }}</em></span>
            </template>
            <el-empty v-if="!sellData.sell_positions?.length" description="暂无卖出建议" />
            <div v-else class="signal-grid">
              <article v-for="point in sellData.sell_positions" :key="point.ts_code" class="signal-card signal-card-sell">
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ point.stock_name }}</div>
                    <div class="signal-code">{{ point.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" type="danger">{{ point.sell_signal_tag }}</el-tag>
                    <el-tag size="small" type="danger">{{ point.sell_point_type }}</el-tag>
                    <el-tag size="small" :type="priorityTagType(point.sell_priority)">{{ point.sell_priority }}优先</el-tag>
                    <el-tag v-if="hasLlmCopy(point)" size="small" type="info">LLM解读</el-tag>
                  </div>
                </div>

                <div class="signal-intent signal-intent-sell">
                  {{ sellActionLine(point) }}
                </div>

                <div class="quote-strip">
                  <div class="metric-card">
                    <span class="metric-label">现价 / 成本</span>
                    <strong class="metric-value">{{ formatPrice(point.market_price) }} / {{ formatPrice(point.cost_price) }}</strong>
                    <span class="metric-meta" :class="{ 'metric-meta-live': isRealtimeSource(point.data_source) }">
                      {{ quoteMetaLine(point.data_source, point.quote_time, displayDate) }}
                    </span>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">浮盈亏</span>
                    <strong :class="['metric-value', pnlClass(point.pnl_pct)]">{{ formatSignedPct(point.pnl_pct) }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">持仓 / 天数</span>
                    <strong class="metric-value">{{ formatQty(point.holding_qty) }} / {{ formatDays(point.holding_days) }}</strong>
                  </div>
                </div>

                <div v-if="hasLlmCopy(point)" class="llm-copy-panel">
                  <div class="llm-copy-head">LLM 解读</div>
                  <div class="llm-copy-paragraph">{{ point.llm_plain_note || point.llm_action_sentence || point.sell_reason }}</div>
                </div>

                <div class="condition-section">
                  <div class="section-kicker">执行清单</div>
                  <div class="condition-panel-grid condition-panel-grid-watch">
                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">动作</div>
                          <div class="panel-subtitle">这是系统建议你优先做的事</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ point.llm_action_sentence || point.sell_reason }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-invalid">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">执行条件</div>
                          <div class="panel-subtitle">满足这个条件时就动手</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ point.llm_trigger_sentence || point.sell_trigger_cond }}</div>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ point.llm_risk_sentence || point.sell_comment || '-' }}</span>
                  <div class="footer-actions">
                    <span class="footer-flag">{{ point.can_sell_today ? '今日可卖' : 'T+1锁定' }}</span>
                    <el-button
                      type="primary"
                      link
                      size="small"
                      :loading="Boolean(priceRefreshingMap[point.ts_code])"
                      @click="refreshPointPrice(point)"
                    >
                      刷新价格
                    </el-button>
                    <el-button type="primary" link size="small" @click="openSellAnalysis(point)">卖点详解</el-button>
                    <el-button type="primary" link size="small" @click="openCheckup(point)">全面体检</el-button>
                  </div>
                </div>
              </article>
            </div>
          </el-tab-pane>

          <el-tab-pane name="reduce">
            <template #label>
              <span>建议减仓 <em class="tab-count">{{ sellData.reduce_positions?.length || 0 }}</em></span>
            </template>
            <el-empty v-if="!sellData.reduce_positions?.length" description="暂无减仓建议" />
            <div v-else class="signal-grid">
              <article v-for="point in sellData.reduce_positions" :key="point.ts_code" class="signal-card signal-card-reduce">
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ point.stock_name }}</div>
                    <div class="signal-code">{{ point.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" type="warning">{{ point.sell_signal_tag }}</el-tag>
                    <el-tag size="small" type="warning">{{ point.sell_point_type }}</el-tag>
                    <el-tag size="small" :type="priorityTagType(point.sell_priority)">{{ point.sell_priority }}优先</el-tag>
                    <el-tag v-if="hasLlmCopy(point)" size="small" type="info">LLM解读</el-tag>
                  </div>
                </div>

                <div class="signal-intent signal-intent-reduce">
                  {{ reduceActionLine(point) }}
                </div>

                <div class="quote-strip">
                  <div class="metric-card">
                    <span class="metric-label">现价 / 成本</span>
                    <strong class="metric-value">{{ formatPrice(point.market_price) }} / {{ formatPrice(point.cost_price) }}</strong>
                    <span class="metric-meta" :class="{ 'metric-meta-live': isRealtimeSource(point.data_source) }">
                      {{ quoteMetaLine(point.data_source, point.quote_time, displayDate) }}
                    </span>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">浮盈亏</span>
                    <strong :class="['metric-value', pnlClass(point.pnl_pct)]">{{ formatSignedPct(point.pnl_pct) }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">持仓 / 天数</span>
                    <strong class="metric-value">{{ formatQty(point.holding_qty) }} / {{ formatDays(point.holding_days) }}</strong>
                  </div>
                </div>

                <div v-if="hasLlmCopy(point)" class="llm-copy-panel">
                  <div class="llm-copy-head">LLM 解读</div>
                  <div class="llm-copy-paragraph">{{ point.llm_plain_note || point.llm_action_sentence || point.sell_reason }}</div>
                </div>

                <div class="condition-section">
                  <div class="section-kicker">观察重点</div>
                  <div class="condition-panel-grid condition-panel-grid-watch">
                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">先做</div>
                          <div class="panel-subtitle">先把风险收下来</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ point.llm_action_sentence || point.sell_reason }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-confirm">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">执行条件</div>
                          <div class="panel-subtitle">这个条件到了就减仓</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ point.llm_trigger_sentence || point.sell_trigger_cond }}</div>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ point.llm_risk_sentence || point.sell_comment || '-' }}</span>
                  <div class="footer-actions">
                    <span class="footer-flag">{{ point.can_sell_today ? '今日可卖' : 'T+1锁定' }}</span>
                    <el-button
                      type="primary"
                      link
                      size="small"
                      :loading="Boolean(priceRefreshingMap[point.ts_code])"
                      @click="refreshPointPrice(point)"
                    >
                      刷新价格
                    </el-button>
                    <el-button type="primary" link size="small" @click="openSellAnalysis(point)">卖点详解</el-button>
                    <el-button type="primary" link size="small" @click="openCheckup(point)">全面体检</el-button>
                  </div>
                </div>
              </article>
            </div>
          </el-tab-pane>

          <el-tab-pane name="hold">
            <template #label>
              <span>持有观察 <em class="tab-count">{{ sellData.hold_positions?.length || 0 }}</em></span>
            </template>
            <el-empty v-if="!sellData.hold_positions?.length" description="暂无持有观察项" />
            <div v-else class="signal-grid">
              <article v-for="point in sellData.hold_positions" :key="point.ts_code" class="signal-card signal-card-hold">
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ point.stock_name }}</div>
                    <div class="signal-code">{{ point.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" type="success">{{ point.sell_signal_tag }}</el-tag>
                    <el-tag size="small" :type="priorityTagType(point.sell_priority)">{{ point.sell_priority }}优先</el-tag>
                    <el-tag
                      v-if="point.add_signal_tag"
                      size="small"
                      :type="point.add_signal_tag === '建议加仓' ? 'danger' : 'warning'"
                    >
                      {{ point.add_signal_tag }}
                    </el-tag>
                    <el-tag v-if="hasLlmCopy(point)" size="small" type="info">LLM解读</el-tag>
                  </div>
                </div>

                <div class="signal-intent signal-intent-hold">
                  {{ holdActionLine(point) }}
                </div>

                <div v-if="point.add_signal_tag" class="add-signal-banner" :class="point.add_signal_tag === '建议加仓' ? 'add-signal-banner-strong' : 'add-signal-banner-watch'">
                  <strong>{{ point.add_signal_tag }}</strong>
                  <span>{{ point.add_signal_reason || '这只票可以转到加仓语境继续看。' }}</span>
                </div>

                <div class="quote-strip">
                  <div class="metric-card">
                    <span class="metric-label">现价 / 成本</span>
                    <strong class="metric-value">{{ formatPrice(point.market_price) }} / {{ formatPrice(point.cost_price) }}</strong>
                    <span class="metric-meta" :class="{ 'metric-meta-live': isRealtimeSource(point.data_source) }">
                      {{ quoteMetaLine(point.data_source, point.quote_time, displayDate) }}
                    </span>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">浮盈亏</span>
                    <strong :class="['metric-value', pnlClass(point.pnl_pct)]">{{ formatSignedPct(point.pnl_pct) }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">持仓 / 天数</span>
                    <strong class="metric-value">{{ formatQty(point.holding_qty) }} / {{ formatDays(point.holding_days) }}</strong>
                  </div>
                </div>

                <div v-if="hasLlmCopy(point)" class="llm-copy-panel">
                  <div class="llm-copy-head">LLM 解读</div>
                  <div class="llm-copy-paragraph">{{ point.llm_plain_note || point.llm_action_sentence || point.sell_comment || point.sell_reason }}</div>
                </div>

                <div class="condition-section">
                  <div class="section-kicker">观察重点</div>
                  <div class="condition-panel-grid condition-panel-grid-watch">
                    <section class="condition-panel condition-panel-confirm">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">说明</div>
                          <div class="panel-subtitle">当前先不用急着处理</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ point.llm_action_sentence || point.sell_comment || point.sell_reason }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">后续处理</div>
                          <div class="panel-subtitle">继续跟踪这个条件</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ point.llm_trigger_sentence || point.sell_trigger_cond }}</div>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ point.llm_risk_sentence || point.sell_reason || '-' }}</span>
                  <div class="footer-actions">
                    <span class="footer-flag">{{ point.can_sell_today ? '今日可卖' : 'T+1锁定' }}</span>
                    <el-button
                      type="primary"
                      link
                      size="small"
                      :loading="Boolean(priceRefreshingMap[point.ts_code])"
                      @click="refreshPointPrice(point)"
                    >
                      刷新价格
                    </el-button>
                    <el-button v-if="point.add_signal_tag" type="primary" link size="small" @click="openBuyAnalysis(point)">查看加仓分析</el-button>
                    <el-button type="primary" link size="small" @click="openSellAnalysis(point)">卖点详解</el-button>
                    <el-button type="primary" link size="small" @click="openCheckup(point)">全面体检</el-button>
                  </div>
                </div>
              </article>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-card>
    <SellAnalysisDrawer
      v-model="sellAnalysisVisible"
      :ts-code="sellAnalysisStock.tsCode"
      :stock-name="sellAnalysisStock.stockName"
      :trade-date="sellAnalysisTradeDate"
      :current-price="sellAnalysisStock.currentPrice"
      :current-pnl-pct="sellAnalysisStock.currentPnlPct"
    />
    <StockCheckupDrawer
      v-model="checkupVisible"
      :ts-code="checkupStock.tsCode"
      :stock-name="checkupStock.stockName"
      :default-target="checkupStock.defaultTarget"
      :trade-date="displayDate"
    />
    <BuyAnalysisDrawer
      v-model="buyAnalysisVisible"
      :ts-code="buyAnalysisStock.tsCode"
      :stock-name="buyAnalysisStock.stockName"
      :trade-date="displayDate"
      :current-price="buyAnalysisStock.currentPrice"
      :current-change-pct="buyAnalysisStock.currentChangePct"
    />
  </div>
</template>

<script setup>
import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { decisionApi, stockApi } from '../api'
import { authState } from '../auth'
import { ElMessage } from 'element-plus'
import StockCheckupDrawer from '../components/StockCheckupDrawer.vue'
import BuyAnalysisDrawer from '../components/BuyAnalysisDrawer.vue'
import SellAnalysisDrawer from '../components/SellAnalysisDrawer.vue'
import { formatLocalTime } from '../utils/datetime'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const llmRefreshing = ref(false)
const activeTab = ref('sell')
const displayDate = ref('')
const loadError = ref('')
const sellData = ref({ sell_positions: [], reduce_positions: [], hold_positions: [], llm_status: null })
const sellAnalysisVisible = ref(false)
const sellAnalysisStock = ref({ tsCode: '', stockName: '', currentPrice: null, currentPnlPct: null })
const buyAnalysisVisible = ref(false)
const buyAnalysisStock = ref({ tsCode: '', stockName: '', currentPrice: null, currentChangePct: null })
const checkupVisible = ref(false)
const checkupStock = ref({ tsCode: '', stockName: '', defaultTarget: '持仓型' })
const priceRefreshingMap = ref({})
const SELL_POINT_CACHE_PREFIX = 'sell_point_snapshot_v2'
const DASHBOARD_CACHE_PREFIX = 'dashboard_snapshot_v2'
const notificationAction = computed(() => String(route.query.notification_action || '').trim())
const notificationTsCode = computed(() => String(route.query.ts_code || '').trim())
const notificationStockName = computed(() => String(route.query.stock_name || '').trim())

const sellHeadline = computed(() => {
  if (sellData.value.sell_positions?.length) return '先处理 SOP 明确要求退出的持仓，再看减仓和继续观察的部分'
  if (sellData.value.reduce_positions?.length) return '当前以防守和收缩风险为主，先把该减的仓位处理掉'
  return '当前没有必须退出的持仓，按 SOP 以持有观察为主'
})
const sellAnalysisTradeDate = computed(() => sellData.value?.resolved_trade_date || displayDate.value)

const sellGuidance = computed(() => {
  if (sellData.value.sell_positions?.length) return '本页已按卖点 SOP 的最终执行动作归类。卖出区代表优先退出，不要和减仓票混在一起处理。'
  if (sellData.value.reduce_positions?.length) return '本页已按卖点 SOP 的最终执行动作归类。减仓区代表先做防守，不等于整笔持仓已经结束。'
  return '本页已按卖点 SOP 的最终执行动作归类。持有观察区代表暂时不急着动，但仍要盯住后续处理条件。'
})

const sellChecklist = computed(() => {
  if (sellData.value.sell_positions?.length) {
    return ['先清高优先级', '退出票优先执行', '别把减仓票当卖出票处理']
  }
  if (sellData.value.reduce_positions?.length) {
    return ['先把风险降下来', '强度下降先防守', '减仓后再看结构是否修复']
  }
  return ['当前先观察', '留意后续处理条件', '承接没坏前不急着机械处理']
})

const llmStatus = computed(() => sellData.value.llm_status || null)
const llmStatusVisible = computed(() => Boolean(llmStatus.value))
const llmStatusClass = computed(() => {
  if (llmStatus.value?.success) return 'llm-status-success'
  if (llmStatus.value?.enabled) return 'llm-status-warning'
  return 'llm-status-muted'
})
const llmStatusText = computed(() => {
  if (!llmStatus.value) return ''
  return llmStatus.value.message || (llmStatus.value.success ? 'LLM 解释增强已生效' : 'LLM 当前未生效')
})
const addSuggestionCount = computed(() => (sellData.value.hold_positions || []).filter((point) => point.add_signal_tag === '建议加仓').length)
const addSmallAddCount = computed(() => (sellData.value.hold_positions || []).filter((point) => point.add_signal_tag === '仅可小加').length)
const addWatchCount = computed(() => (sellData.value.hold_positions || []).filter((point) => point.add_signal_tag === '可关注加仓').length)
const addSignalCount = computed(() => addSuggestionCount.value + addSmallAddCount.value + addWatchCount.value)

const topActions = computed(() => {
  const ordered = [
    ...(sellData.value.sell_positions || []),
    ...(sellData.value.reduce_positions || []),
    ...(sellData.value.hold_positions || []),
  ]
  return ordered.slice(0, 3).map((item, index) => ({
    ...item,
    rank: index + 1,
    orderLabel: orderLabel(index, item.sell_signal_tag),
  }))
})

const resolveCacheKey = (tradeDate) => {
  const accountId = authState.account?.id || 'guest'
  return `${SELL_POINT_CACHE_PREFIX}:${accountId}:${tradeDate}`
}

const resolveDashboardCacheKey = () => {
  const accountId = authState.account?.id || 'guest'
  return `${DASHBOARD_CACHE_PREFIX}:${accountId}`
}

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const priorityTagType = (p) => {
  if (p === '高') return 'danger'
  if (p === '中') return 'warning'
  return 'info'
}

const pnlClass = (value) => {
  if (value === null || value === undefined) return ''
  if (Number(value) > 0) return 'text-red'
  if (Number(value) < 0) return 'text-green'
  return 'text-neutral'
}

const formatPrice = (value) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(2)
}

const formatSignedPct = (value) => {
  if (value === null || value === undefined) return '-'
  const num = Number(value)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const formatQty = (value) => {
  if (value === null || value === undefined) return '-'
  return `${value}股`
}

const formatDays = (value) => {
  if (value === null || value === undefined) return '-'
  return `${value}天`
}

const isRealtimeSource = (source) => String(source || '').startsWith('realtime_')

const quoteSourceLabel = (source) => {
  if (!source) return '日线回退'
  if (String(source).startsWith('realtime_')) return '盘中实时'
  if (source === 'mock') return '模拟数据'
  return '日线回退'
}

const quoteMetaLine = (source, quoteTime, fallbackDate) => {
  const label = quoteSourceLabel(source)
  if (quoteTime) return `${label} ${formatLocalTime(quoteTime)}`
  if (fallbackDate) return `${label} ${fallbackDate}`
  return label
}

const hasLlmCopy = (point) => Boolean(
  point?.llm_plain_note || point?.llm_action_sentence || point?.llm_trigger_sentence || point?.llm_risk_sentence
)

const hasAnyLlmContent = (data) => {
  if (data?.llm_summary?.page_summary || data?.llm_summary?.action_summary) return true
  const groups = [
    ...(data?.sell_positions || []),
    ...(data?.reduce_positions || []),
    ...(data?.hold_positions || []),
  ]
  return groups.some((point) => hasLlmCopy(point))
}

const shouldPreserveCurrentLlm = (nextData) => hasAnyLlmContent(sellData.value) && !hasAnyLlmContent(nextData)

const sellActionLine = (point) => {
  if (point?.can_sell_today === false) return '系统动作：今天先记录退出计划，下个可卖时点优先执行。'
  return '系统动作：优先退出，按触发条件执行，不再拖延。'
}

const reduceActionLine = (point) => {
  if (point?.can_sell_today === false) return '系统动作：今天先记减仓计划，下个可卖时点优先防守。'
  if (point?.reduce_reason_code === 'protect_profit') return '系统动作：先锁一部分利润，再看后续强弱。'
  if (point?.reduce_reason_code === 'structure_loose') return '系统动作：先减仓防守，观察结构是否继续松动。'
  if (point?.reduce_reason_code === 'env_weak') return '系统动作：环境转弱，先把仓位收下来。'
  if (point?.reduce_reason_code === 'rebound_exit') return '系统动作：借反抽处理，不宜恋战。'
  return '系统动作：先减仓防守，不急着一把清。'
}

const holdActionLine = (point) => {
  if (point.add_signal_tag) {
    return `${point.add_signal_tag}：${point.add_signal_reason || point.sell_comment || point.sell_reason}。`
  }
  return '系统动作：暂不处理，先盯承接和关键位。'
}
const topActionReason = (point) => point.llm_trigger_sentence || shortTriggerText(point.sell_trigger_cond || point.sell_reason || '-')

const shortTriggerText = (text) => {
  if (!text) return '-'
  return String(text)
    .replace(/^次日/, '下个交易时段')
    .replace(/^日内/, '盘中')
    .replace(/^收盘前/, '尾盘')
}

const orderLabel = (index, signal) => {
  const prefix = index === 0 ? '先' : index === 1 ? '再' : '最后'
  if (signal === '卖出') return `${prefix}卖出 `
  if (signal === '减仓') return `${prefix}减仓 `
  return `${prefix}观察 `
}

const openCheckup = (point, defaultTarget = '持仓型') => {
  checkupStock.value = {
    tsCode: point.ts_code,
    stockName: point.stock_name || point.ts_code,
    defaultTarget
  }
  checkupVisible.value = true
}

const openSellAnalysis = (point) => {
  sellAnalysisStock.value = {
    tsCode: point.ts_code,
    stockName: point.stock_name || point.ts_code,
    currentPrice: point.market_price ?? null,
    currentPnlPct: point.pnl_pct ?? null,
  }
  sellAnalysisVisible.value = true
}

const openBuyAnalysis = (point) => {
  buyAnalysisStock.value = {
    tsCode: point.ts_code,
    stockName: point.stock_name || point.ts_code,
    currentPrice: point.market_price ?? null,
    currentChangePct: null,
  }
  buyAnalysisVisible.value = true
}

const clearNotificationQuery = () => {
  const query = { ...route.query }
  delete query.notification_action
  delete query.ts_code
  delete query.stock_name
  router.replace({ query })
}

const matchesTsCode = (point, tsCode) => String(point?.ts_code || '').toUpperCase() === String(tsCode || '').toUpperCase()

const handleNotificationQuery = () => {
  if (!notificationAction.value || !notificationTsCode.value) return
  const allPoints = [
    ...(sellData.value.sell_positions || []),
    ...(sellData.value.reduce_positions || []),
    ...(sellData.value.hold_positions || []),
  ]
  const targetPoint = allPoints.find((point) => matchesTsCode(point, notificationTsCode.value))
  if (notificationAction.value === 'sell_analysis') {
    openSellAnalysis(targetPoint || {
      ts_code: notificationTsCode.value,
      stock_name: notificationStockName.value || notificationTsCode.value,
      market_price: null,
      pnl_pct: null,
    })
    clearNotificationQuery()
    return
  }
  if (notificationAction.value === 'buy_analysis') {
    openBuyAnalysis(targetPoint || {
      ts_code: notificationTsCode.value,
      stock_name: notificationStockName.value || notificationTsCode.value,
      market_price: null,
    })
    clearNotificationQuery()
    return
  }
  if (notificationAction.value === 'checkup') {
    openCheckup({
      ts_code: notificationTsCode.value,
      stock_name: notificationStockName.value || notificationTsCode.value,
    })
    clearNotificationQuery()
  }
}

const setPointRefreshing = (tsCode, refreshing) => {
  priceRefreshingMap.value = {
    ...priceRefreshingMap.value,
    [tsCode]: refreshing,
  }
}

const refreshPointPrice = async (point) => {
  if (!point?.ts_code) return
  setPointRefreshing(point.ts_code, true)
  try {
    const res = await stockApi.detail(point.ts_code, displayDate.value || getLocalDate())
    const stock = res?.data?.data?.stock
    const latestPrice = Number(stock?.close)
    if (!Number.isFinite(latestPrice) || latestPrice <= 0) {
      ElMessage.warning('未获取到有效最新价')
      return
    }

    point.market_price = latestPrice
    point.quote_time = stock?.quote_time || null
    point.data_source = stock?.data_source || point.data_source
    if (Number(point.cost_price) > 0) {
      point.pnl_pct = Number((((latestPrice - Number(point.cost_price)) / Number(point.cost_price)) * 100).toFixed(2))
    }

    if (sellAnalysisVisible.value && sellAnalysisStock.value.tsCode === point.ts_code) {
      sellAnalysisStock.value = {
        ...sellAnalysisStock.value,
        currentPrice: point.market_price ?? null,
        currentPnlPct: point.pnl_pct ?? null,
      }
    }
    if (buyAnalysisVisible.value && buyAnalysisStock.value.tsCode === point.ts_code) {
      buyAnalysisStock.value = {
        ...buyAnalysisStock.value,
        currentPrice: point.market_price ?? null,
      }
    }

    persistSellPointCache()
    ElMessage.success(`${point.stock_name || point.ts_code} 最新价已更新`)
  } catch (error) {
    const message = error?.response?.data?.message || error?.message || '刷新价格失败'
    ElMessage.error(message)
  } finally {
    setPointRefreshing(point.ts_code, false)
  }
}

const persistSellPointCache = () => {
  if (typeof window === 'undefined' || !displayDate.value) return
  const payload = {
    displayDate: displayDate.value,
    sellData: sellData.value,
    activeTab: activeTab.value,
    updatedAt: Date.now(),
  }
  window.sessionStorage.setItem(resolveCacheKey(displayDate.value), JSON.stringify(payload))
}

const hydrateSellPointCache = (tradeDate) => {
  if (typeof window === 'undefined') return false
  const raw = window.sessionStorage.getItem(resolveCacheKey(tradeDate))
  if (!raw) return false
  try {
    const payload = JSON.parse(raw)
    displayDate.value = payload.displayDate || tradeDate
    sellData.value = payload.sellData || { sell_positions: [], reduce_positions: [], hold_positions: [], llm_status: null }
    activeTab.value = payload.activeTab || 'sell'
    return true
  } catch (error) {
    window.sessionStorage.removeItem(resolveCacheKey(tradeDate))
    return false
  }
}

const hydrateDashboardSellPointCache = (tradeDate) => {
  if (typeof window === 'undefined') return false
  const raw = window.sessionStorage.getItem(resolveDashboardCacheKey())
  if (!raw) return false
  try {
    const payload = JSON.parse(raw)
    const dashboardSellData = payload.sellPoints || null
    if (!dashboardSellData || !hasAnyLlmContent(dashboardSellData)) return false
    displayDate.value = tradeDate
    sellData.value = dashboardSellData
    if (dashboardSellData.sell_positions?.length) activeTab.value = 'sell'
    else if (dashboardSellData.reduce_positions?.length) activeTab.value = 'reduce'
    else activeTab.value = 'hold'
    persistSellPointCache()
    return true
  } catch (error) {
    return false
  }
}

const loadData = async (options = {}) => {
  const refresh = Boolean(options.refresh)
  const forceLlmRefresh = Boolean(options.forceLlmRefresh)
  const includeLlm = true
  const silent = Boolean(options.silent)
  const hasRenderableData = Boolean(
    sellData.value?.sell_positions?.length
    || sellData.value?.reduce_positions?.length
    || sellData.value?.hold_positions?.length
  )
  if (forceLlmRefresh) llmRefreshing.value = true
  else loading.value = refresh || (!hasRenderableData && !silent)
  if (!forceLlmRefresh) loadError.value = ''
  try {
    const tradeDate = getLocalDate()
    displayDate.value = tradeDate
    const res = await decisionApi.sellPoint(tradeDate, {
      refresh,
      forceLlmRefresh,
      includeLlm,
      timeout: 90000
    })
    const nextData = res.data.data
    if (shouldPreserveCurrentLlm(nextData)) {
      sellData.value = {
        ...nextData,
        llm_summary: sellData.value?.llm_summary || nextData?.llm_summary || null,
        llm_status: sellData.value?.llm_status || nextData?.llm_status || null,
        sell_positions: (nextData?.sell_positions || []).map((point) => {
          const current = (sellData.value?.sell_positions || []).find((item) => item.ts_code === point.ts_code)
          return current && hasLlmCopy(current)
            ? {
                ...point,
                llm_plain_note: current.llm_plain_note ?? point.llm_plain_note,
                llm_action_sentence: current.llm_action_sentence ?? point.llm_action_sentence,
                llm_trigger_sentence: current.llm_trigger_sentence ?? point.llm_trigger_sentence,
                llm_risk_sentence: current.llm_risk_sentence ?? point.llm_risk_sentence,
              }
            : point
        }),
        reduce_positions: (nextData?.reduce_positions || []).map((point) => {
          const current = (sellData.value?.reduce_positions || []).find((item) => item.ts_code === point.ts_code)
          return current && hasLlmCopy(current)
            ? {
                ...point,
                llm_plain_note: current.llm_plain_note ?? point.llm_plain_note,
                llm_action_sentence: current.llm_action_sentence ?? point.llm_action_sentence,
                llm_trigger_sentence: current.llm_trigger_sentence ?? point.llm_trigger_sentence,
                llm_risk_sentence: current.llm_risk_sentence ?? point.llm_risk_sentence,
              }
            : point
        }),
        hold_positions: (nextData?.hold_positions || []).map((point) => {
          const current = (sellData.value?.hold_positions || []).find((item) => item.ts_code === point.ts_code)
          return current && hasLlmCopy(current)
            ? {
                ...point,
                llm_plain_note: current.llm_plain_note ?? point.llm_plain_note,
                llm_action_sentence: current.llm_action_sentence ?? point.llm_action_sentence,
                llm_trigger_sentence: current.llm_trigger_sentence ?? point.llm_trigger_sentence,
                llm_risk_sentence: current.llm_risk_sentence ?? point.llm_risk_sentence,
              }
            : point
        }),
      }
    } else {
      sellData.value = nextData
    }
    if (sellData.value.sell_positions?.length) activeTab.value = 'sell'
    else if (sellData.value.reduce_positions?.length) activeTab.value = 'reduce'
    else activeTab.value = 'hold'
    persistSellPointCache()
    handleNotificationQuery()
  } catch (error) {
    const message = error?.response?.data?.message || error?.message || '加载失败'
    if (forceLlmRefresh) {
      ElMessage.error(`刷新解读失败: ${message}`)
    } else {
      loadError.value = `卖点分析加载失败：${message}`
      ElMessage.error('卖点分析加载失败')
    }
  } finally {
    loading.value = false
    llmRefreshing.value = false
  }
}

const refreshLlm = async () => {
  await loadData({ forceLlmRefresh: true })
}

onMounted(() => {
  const tradeDate = getLocalDate()
  displayDate.value = tradeDate
  const hydrated = hydrateSellPointCache(tradeDate) || hydrateDashboardSellPointCache(tradeDate)
  loadData({ silent: hydrated })
})

watch(
  () => [notificationAction.value, notificationTsCode.value, loading.value],
  () => {
    if (loading.value) return
    handleNotificationQuery()
  }
)
</script>

<style scoped>
.sell-view {
  min-height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.header-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.card-header-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.header-date {
  font-size: 13px;
  color: var(--color-text-sec);
  letter-spacing: 0.02em;
  font-weight: 400;
}

.decision-overview {
  display: grid;
  gap: 18px;
  margin-bottom: 24px;
  padding: 20px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(255, 122, 127, 0.1), transparent 34%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.04));
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.overview-copy {
  display: grid;
  gap: 8px;
}

.overview-title {
  font-size: 1.05rem;
  font-weight: 700;
}

.overview-desc {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.overview-llm,
.overview-action-summary {
  padding: 10px 12px;
  border-radius: 12px;
  line-height: 1.6;
  color: var(--color-text-main);
  background: rgba(255, 255, 255, 0.04);
}

.overview-action-summary {
  display: grid;
  gap: 6px;
}

.summary-kicker {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.overview-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.overview-rules {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.overview-add-signals {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.add-signal-pill {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  border: 1px solid transparent;
}

.add-signal-pill-strong {
  color: #ff8c69;
  background: rgba(255, 140, 105, 0.1);
  border-color: rgba(255, 140, 105, 0.2);
}

.add-signal-pill-watch {
  color: #f3c24d;
  background: rgba(243, 194, 77, 0.1);
  border-color: rgba(243, 194, 77, 0.2);
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
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.llm-status-text {
  line-height: 1.5;
  color: var(--color-text-main);
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

.top-actions {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.top-actions-title {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.top-actions-list {
  display: grid;
  gap: 8px;
}

.top-action-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) minmax(240px, 1fr);
  gap: 12px;
  align-items: stretch;
}

.top-action-rank {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #ff7a7f, #d84d58);
}

.top-action-main {
  display: grid;
  gap: 2px;
  align-content: center;
}

.top-action-meta {
  color: var(--color-text-sec);
  font-size: 12px;
}

.top-action-trigger {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  align-content: center;
}

.top-action-trigger-label {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.top-action-reason {
  color: var(--color-text-pri);
  font-size: 14px;
  line-height: 1.6;
  font-weight: 500;
}

.rule-chip {
  padding: 8px 12px;
  border-radius: 999px;
  color: var(--color-text-sec);
  font-size: 13px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.stat-card {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.stat-value {
  font-size: 1.6rem;
  line-height: 1;
}

.stat-tip {
  color: var(--color-text-sec);
  font-size: 13px;
}

.stat-sell .stat-value {
  color: #ff7a7f;
}

.stat-reduce .stat-value {
  color: #f3c24d;
}

.stat-hold .stat-value {
  color: #44d19f;
}

.tab-count {
  font-style: normal;
  color: var(--color-text-sec);
  margin-left: 4px;
}

.signal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.signal-card {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
}

.signal-card-sell {
  box-shadow: inset 0 1px 0 rgba(255, 122, 127, 0.16);
}

.signal-card-reduce {
  box-shadow: inset 0 1px 0 rgba(243, 194, 77, 0.16);
}

.signal-card-hold {
  box-shadow: inset 0 1px 0 rgba(68, 209, 159, 0.16);
}

.signal-card-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.signal-stock {
  font-size: 1.05rem;
  font-weight: 700;
}

.signal-code {
  font-size: 13px;
  color: var(--color-text-sec);
}

.signal-badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.signal-intent {
  padding: 12px 14px;
  border-radius: 14px;
  line-height: 1.6;
}

.signal-intent-sell {
  background: rgba(255, 122, 127, 0.08);
  border: 1px solid rgba(255, 122, 127, 0.14);
}

.signal-intent-reduce {
  background: rgba(243, 194, 77, 0.08);
  border: 1px solid rgba(243, 194, 77, 0.16);
}

.signal-intent-hold {
  background: rgba(68, 209, 159, 0.08);
  border: 1px solid rgba(68, 209, 159, 0.14);
}

.add-signal-banner {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  line-height: 1.6;
}

.add-signal-banner-strong {
  background: rgba(255, 140, 105, 0.08);
  border: 1px solid rgba(255, 140, 105, 0.18);
}

.add-signal-banner-watch {
  background: rgba(243, 194, 77, 0.08);
  border: 1px solid rgba(243, 194, 77, 0.18);
}

.llm-copy-panel {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(88, 176, 255, 0.18);
  background: linear-gradient(135deg, rgba(88, 176, 255, 0.09), rgba(88, 176, 255, 0.04));
}

.llm-copy-head {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #9dc2ff;
}

.llm-copy-paragraph {
  color: var(--color-text-main);
  line-height: 1.8;
  font-size: 15px;
  font-weight: 500;
}

.quote-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  display: grid;
  gap: 6px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(9, 14, 23, 0.35);
}

.metric-label {
  color: var(--color-text-sec);
  font-size: 12px;
}

.metric-value {
  font-size: 1.15rem;
}

.metric-meta {
  font-size: 12px;
  color: var(--color-text-sec);
}

.metric-meta-live {
  color: #54d2a4;
}

.condition-section {
  display: grid;
  gap: 10px;
}

.section-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.condition-panel-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.condition-panel-grid-watch {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.condition-panel {
  display: grid;
  gap: 12px;
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
  min-width: 0;
}

.condition-panel-trigger {
  background: linear-gradient(180deg, rgba(92, 122, 255, 0.06), rgba(255, 255, 255, 0.02));
}

.condition-panel-confirm {
  background: linear-gradient(180deg, rgba(68, 209, 159, 0.06), rgba(255, 255, 255, 0.02));
}

.condition-panel-invalid {
  background: linear-gradient(180deg, rgba(255, 122, 127, 0.08), rgba(255, 255, 255, 0.02));
}

.panel-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.panel-step {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: rgba(255, 255, 255, 0.14);
  flex-shrink: 0;
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
}

.panel-subtitle {
  font-size: 12px;
  color: var(--color-text-sec);
  line-height: 1.5;
  margin-top: 2px;
}

.panel-body {
  min-width: 0;
}

.condition-title {
  line-height: 1.6;
  font-size: 15px;
}

.signal-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  color: var(--color-text-sec);
  font-size: 13px;
}

.footer-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.footer-flag {
  white-space: nowrap;
  color: #8ab4ff;
}

@media (max-width: 900px) {
  .overview-stats,
  .quote-strip,
  .condition-panel-grid,
  .condition-panel-grid-watch {
    grid-template-columns: 1fr;
  }

  .overview-rules {
    flex-direction: column;
  }

  .top-action-item {
    grid-template-columns: 28px minmax(0, 1fr);
  }

  .signal-footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .footer-actions {
    justify-content: flex-start;
  }
}
</style>
