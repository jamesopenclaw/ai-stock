<template>
  <div class="pools-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>三池分类</span>
            <span v-if="displayDate" class="header-date">{{ displayDate }}</span>
            <span
              v-if="poolsData.resolved_trade_date && poolsData.resolved_trade_date !== displayDate"
              class="header-date"
            >
              实际候选日 {{ poolsData.resolved_trade_date }}
            </span>
          </div>
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="8" animated />
      <template v-else>
        <div class="decision-overview">
          <div class="overview-main">
            <div class="overview-badge" :class="overviewBadgeClass">
              {{ overviewBadge }}
            </div>
            <div class="overview-copy">
              <div class="overview-title">{{ overviewTitle }}</div>
              <div class="overview-desc">{{ overviewDesc }}</div>
              <div v-if="poolsData.llm_summary?.page_summary" class="overview-llm">
                {{ poolsData.llm_summary.page_summary }}
              </div>
            </div>
          </div>

          <div class="overview-stats">
            <div class="stat-card stat-market">
              <span class="stat-label">市场观察</span>
              <strong class="stat-value">{{ marketCount }}</strong>
              <span class="stat-tip">看方向和最强结构</span>
            </div>
            <div class="stat-card stat-account">
              <span class="stat-label">账户可参与</span>
              <strong class="stat-value">{{ accountCount }}</strong>
              <span class="stat-tip">满足账户准入才动手</span>
            </div>
            <div class="stat-card stat-holding">
              <span class="stat-label">持仓处理</span>
              <strong class="stat-value">{{ holdingCount }}</strong>
              <span class="stat-tip">优先处理已有仓位</span>
            </div>
          </div>

          <div class="overview-rules">
            <div v-for="rule in overviewRules" :key="rule" class="rule-chip">
              {{ rule }}
            </div>
          </div>

          <div v-if="llmStatusVisible" class="llm-status" :class="llmStatusClass">
            <span class="llm-status-label">LLM 状态</span>
            <span class="llm-status-text">{{ llmStatusText }}</span>
          </div>

          <div v-if="topFocusItems.length" class="top-focus">
            <div class="top-focus-title">今天先看</div>
            <div v-if="poolsData.llm_summary?.top_focus_summary" class="top-focus-summary">
              {{ poolsData.llm_summary.top_focus_summary }}
            </div>
            <div class="top-focus-list">
              <div v-for="item in topFocusItems" :key="`${item.poolKey}-${item.ts_code}`" class="top-focus-item">
                <span class="top-focus-rank">{{ item.rank }}</span>
                <div class="top-focus-main">
                  <strong>{{ item.orderLabel }}{{ item.stock_name }}</strong>
                  <span class="top-focus-meta">{{ item.meta }}</span>
                </div>
                <div class="top-focus-trigger">
                  <span class="top-focus-trigger-label">重点</span>
                  <span class="top-focus-trigger-text">{{ item.focus }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <el-tabs v-model="activeTab">
          <el-tab-pane name="market">
            <template #label>
              <span>市场最强观察池 <em class="tab-count">{{ marketCount }}</em></span>
            </template>
            <el-empty v-if="!marketCount" description="暂无需要观察的强势候选" />
            <div v-else class="signal-grid">
              <article
                v-for="stock in marketPool"
                :key="stock.ts_code"
                class="signal-card signal-card-market"
              >
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ stock.stock_name }}</div>
                    <div class="signal-code">{{ stock.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" type="primary">{{ stock.candidate_bucket_tag || '观察补充' }}</el-tag>
                    <el-tag size="small" type="info">{{ stock.stock_core_tag }}</el-tag>
                  </div>
                </div>

                <div class="signal-meta">
                  <span>{{ stock.sector_name || '无板块信息' }}</span>
                  <span>{{ stock.candidate_source_tag || '无来源标记' }}</span>
                </div>

                <div class="signal-intent signal-intent-market">
                  {{ marketActionLine(stock) }}
                </div>

                <div class="quote-strip">
                  <div class="quote-main">
                    <span class="quote-label">最新价</span>
                    <strong class="quote-price">{{ formatPrice(stock.close) }}</strong>
                    <span :class="['quote-change', pctClass(stock.change_pct)]">
                      {{ formatSignedPct(stock.change_pct) }}
                    </span>
                  </div>
                  <div class="quote-side">
                    <span class="quote-pair">
                      综合分
                      <strong>{{ formatScore(stock.stock_score) }}</strong>
                    </span>
                    <span class="quote-pair">
                      量比
                      <strong>{{ formatRatio(stock.vol_ratio) }}</strong>
                    </span>
                  </div>
                </div>

                <div class="price-strip">
                  <div class="metric-card">
                    <span class="metric-label">强弱</span>
                    <strong class="metric-value">{{ stock.stock_strength_tag }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">连续性</span>
                    <strong class="metric-value">{{ stock.stock_continuity_tag }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">交易性</span>
                    <strong class="metric-value">{{ stock.stock_tradeability_tag }}</strong>
                  </div>
                </div>

                <div class="condition-section">
                  <div class="section-kicker">观察清单</div>
                  <div class="condition-panel-grid condition-panel-grid-watch">
                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">先看</div>
                          <div class="panel-subtitle">这只票为什么值得盯</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.stock_comment || '先看板块和量能是否继续强化。' }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-invalid">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">证伪</div>
                          <div class="panel-subtitle">出现这个信号就降级观察</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.llm_risk_note || stock.stock_falsification_cond || '结构破坏或量能转弱时不再优先观察。' }}</div>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ marketFooterLine(stock) }}</span>
                  <span class="footer-flag">只观察，不直接执行</span>
                </div>
              </article>
            </div>
          </el-tab-pane>

          <el-tab-pane name="account">
            <template #label>
              <span>账户可参与池 <em class="tab-count">{{ accountCount }}</em></span>
            </template>
            <el-empty
              v-if="!accountCount"
              :description="holdingCount ? '先处理持仓风险；当前没有满足账户准入的新标的' : '当前没有满足账户准入的新标的'"
            />
            <div v-else class="signal-grid">
              <article
                v-for="stock in accountPool"
                :key="stock.ts_code"
                class="signal-card signal-card-account"
              >
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ stock.stock_name }}</div>
                    <div class="signal-code">{{ stock.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" type="success">{{ stock.candidate_bucket_tag || '可参与' }}</el-tag>
                    <el-tag size="small" :type="accountEntryTagType(stock)">{{ accountEntryTag(stock) }}</el-tag>
                  </div>
                </div>

                <div class="signal-meta">
                  <span>{{ stock.sector_name || '无板块信息' }}</span>
                  <span>{{ stock.candidate_source_tag || '无来源标记' }}</span>
                </div>

                <div class="signal-intent signal-intent-account">
                  {{ accountActionLine(stock) }}
                </div>

                <div class="quote-strip">
                  <div class="quote-main">
                    <span class="quote-label">最新价</span>
                    <strong class="quote-price">{{ formatPrice(stock.close) }}</strong>
                    <span :class="['quote-change', pctClass(stock.change_pct)]">
                      {{ formatSignedPct(stock.change_pct) }}
                    </span>
                  </div>
                  <div class="quote-side">
                    <span class="quote-pair">
                      综合分
                      <strong>{{ formatScore(stock.stock_score) }}</strong>
                    </span>
                    <span class="quote-pair">
                      换手
                      <strong>{{ formatSignedNumber(stock.turnover_rate, '%') }}</strong>
                    </span>
                  </div>
                </div>

                <div class="price-strip">
                  <div class="metric-card">
                    <span class="metric-label">强弱</span>
                    <strong class="metric-value">{{ stock.stock_strength_tag }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">连续性</span>
                    <strong class="metric-value">{{ stock.stock_continuity_tag }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">交易性</span>
                    <strong class="metric-value">{{ stock.stock_tradeability_tag }}</strong>
                  </div>
                </div>

                <div class="condition-section">
                  <div class="section-kicker">执行清单</div>
                  <div class="condition-panel-grid condition-panel-grid-watch">
                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">为什么能进池</div>
                          <div class="panel-subtitle">先看账户和结构是否匹配</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.pool_entry_reason || stock.stock_comment || '满足常规开仓条件。' }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-confirm">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">仓位提示</div>
                          <div class="panel-subtitle">执行前先按提示控制仓位</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.llm_risk_note || stock.position_hint || '按计划仓位执行，不要超配。' }}</div>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ stock.stock_comment || '可参与不代表立刻追价，仍要等买点页确认。' }}</span>
                  <span class="footer-flag">{{ accountFooterFlag(stock) }}</span>
                </div>
              </article>
            </div>
          </el-tab-pane>

          <el-tab-pane name="holding">
            <template #label>
              <span>持仓处理池 <em class="tab-count">{{ holdingCount }}</em></span>
            </template>
            <el-empty v-if="!holdingCount" description="暂无持仓或持仓未进入当日行情" />
            <div v-else class="signal-grid">
              <article
                v-for="stock in holdingPool"
                :key="stock.ts_code"
                class="signal-card signal-card-holding"
              >
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ stock.stock_name }}</div>
                    <div class="signal-code">{{ stock.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" :type="sellTagType(stock.sell_signal_tag)">{{ stock.sell_signal_tag || '观察' }}</el-tag>
                    <el-tag size="small" :type="priorityTagType(stock.sell_priority)">{{ `${stock.sell_priority || '低'}优先` }}</el-tag>
                  </div>
                </div>

                <div class="signal-meta">
                  <span>{{ stock.sector_name || '无板块信息' }}</span>
                  <span>{{ stock.holding_reason || '无买入理由记录' }}</span>
                </div>

                <div class="signal-intent signal-intent-holding">
                  {{ holdingActionLine(stock) }}
                </div>

                <div class="quote-strip">
                  <div class="quote-main">
                    <span class="quote-label">现价 / 成本</span>
                    <strong class="quote-price">{{ formatPrice(stock.close) }} / {{ formatPrice(stock.cost_price) }}</strong>
                    <span :class="['quote-change', pctClass(stock.pnl_pct)]">
                      {{ formatSignedPct(stock.pnl_pct) }}
                    </span>
                  </div>
                  <div class="quote-side">
                    <span class="quote-pair">
                      持仓
                      <strong>{{ formatQty(stock.holding_qty) }}</strong>
                    </span>
                    <span class="quote-pair">
                      市值
                      <strong>{{ formatMoney(stock.holding_market_value) }}</strong>
                    </span>
                  </div>
                </div>

                <div class="price-strip">
                  <div class="metric-card">
                    <span class="metric-label">持有天数</span>
                    <strong class="metric-value">{{ formatDays(stock.holding_days) }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">可卖状态</span>
                    <strong class="metric-value">{{ stock.can_sell_today ? '今日可卖' : 'T+1锁定' }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">交易性</span>
                    <strong class="metric-value">{{ stock.stock_tradeability_tag }}</strong>
                  </div>
                </div>

                <div class="condition-section">
                  <div class="section-kicker">处理清单</div>
                  <div class="condition-panel-grid">
                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">动作</div>
                          <div class="panel-subtitle">先明确该持有、减仓还是卖出</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.sell_reason || stock.sell_comment || '当前没有明确动作建议。' }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-confirm">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">动手条件</div>
                          <div class="panel-subtitle">到了这个条件再执行动作</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.sell_trigger_cond || '继续跟踪盘中强弱和板块共振。' }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-invalid">
                      <div class="panel-head">
                        <span class="panel-step">3</span>
                        <div>
                          <div class="panel-title">买入前提</div>
                          <div class="panel-subtitle">回头对照原来的持仓逻辑是否还成立</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.llm_risk_note || stock.stock_falsification_cond || '若买入逻辑失效，就不要继续硬扛。' }}</div>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ stock.llm_risk_note || stock.sell_comment || stock.stock_comment || '-' }}</span>
                  <span class="footer-flag">{{ holdingFooterFlag(stock) }}</span>
                </div>
              </article>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { stockApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const activeTab = ref('holding')
const displayDate = ref('')
const poolsData = ref({
  market_watch_pool: [],
  account_executable_pool: [],
  holding_process_pool: [],
  resolved_trade_date: '',
  llm_status: null,
})

const marketCount = computed(() => poolsData.value.market_watch_pool?.length || 0)
const accountCount = computed(() => poolsData.value.account_executable_pool?.length || 0)
const holdingCount = computed(() => poolsData.value.holding_process_pool?.length || 0)

const marketPool = computed(() =>
  [...(poolsData.value.market_watch_pool || [])].sort((a, b) => Number(b.stock_score || 0) - Number(a.stock_score || 0))
)
const accountPool = computed(() =>
  [...(poolsData.value.account_executable_pool || [])].sort((a, b) => Number(b.stock_score || 0) - Number(a.stock_score || 0))
)
const holdingPool = computed(() =>
  [...(poolsData.value.holding_process_pool || [])].sort(compareHoldingPriority)
)

const overviewBadge = computed(() => {
  if (holdingCount.value) return '先处理持仓'
  if (accountCount.value) return '看可参与'
  return '先看观察池'
})

const overviewBadgeClass = computed(() => {
  if (holdingCount.value) return 'badge-holding'
  if (accountCount.value) return 'badge-account'
  return 'badge-market'
})

const overviewTitle = computed(() => {
  if (holdingCount.value) return '已有仓位优先，先把该卖、该减、该持有的动作排清楚'
  if (accountCount.value) return '当前有能执行的新标的，先看账户可参与池，再回到买点页确认'
  if (marketCount.value) return '当前更适合先观察市场最强结构，不要把观察票当成执行票'
  return '今天三池都比较清淡，先等新的结构和账户信号'
})

const overviewDesc = computed(() => {
  if (holdingCount.value) return '持仓处理池是今天优先级最高的区域；先处理旧仓风险，再决定是否看新票。'
  if (accountCount.value) return '账户可参与池说明系统已经过了账户准入这一步，但真正执行仍要结合买点和盘中确认。'
  if (marketCount.value) return '观察池的任务是帮你缩小盯盘范围，先看方向、板块和量能，不要直接下单。'
  return '当前没有明显需要处理的仓位，也没有通过准入的新标的，适合保持节奏。'
})

const overviewRules = computed(() => {
  if (holdingCount.value) {
    return ['先处理旧仓，再考虑新开仓', '动作建议优先看高优先级', '证伪条件到了就不要拖']
  }
  if (accountCount.value) {
    return ['先看进池理由', '仓位提示比题材更重要', '可参与不等于立刻追价']
  }
  return ['观察池只负责缩小盯盘范围', '先看最强结构，再看账户是否允许', '没有执行确认就不要急着动']
})

const llmStatus = computed(() => poolsData.value.llm_status || null)
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

const topFocusItems = computed(() => {
  const items = []

  holdingPool.value.slice(0, 2).forEach((stock) => {
    items.push({
      poolKey: 'holding',
      ts_code: stock.ts_code,
      stock_name: stock.stock_name,
      focus: stock.sell_trigger_cond || stock.sell_reason || stock.sell_comment || '继续跟踪盘中变化',
      meta: `${stock.sell_signal_tag || '观察'} / ${stock.sell_priority || '低'}优先 / ${formatSignedPct(stock.pnl_pct)}`,
      orderLabel: holdingOrderLabel(items.length),
    })
  })

  if (accountPool.value.length) {
    const stock = accountPool.value[0]
    items.push({
      poolKey: 'account',
      ts_code: stock.ts_code,
      stock_name: stock.stock_name,
      focus: stock.pool_entry_reason || stock.position_hint || stock.stock_comment || '等待买点确认',
      meta: `可参与 / ${stock.candidate_bucket_tag || '未分层'} / ${formatSignedPct(stock.change_pct)}`,
      orderLabel: items.length ? '再看 ' : '先看 ',
    })
  } else if (marketPool.value.length) {
    const stock = marketPool.value[0]
    items.push({
      poolKey: 'market',
      ts_code: stock.ts_code,
      stock_name: stock.stock_name,
      focus: stock.stock_comment || stock.stock_falsification_cond || '先看板块和量能',
      meta: `观察池 / ${stock.candidate_bucket_tag || '未分层'} / ${formatSignedPct(stock.change_pct)}`,
      orderLabel: items.length ? '再盯 ' : '先盯 ',
    })
  }

  return items.slice(0, 3).map((item, index) => ({
    ...item,
    rank: index + 1,
    orderLabel: index === 0 ? item.orderLabel : index === 1 ? item.orderLabel.replace(/^先/, '再') : item.orderLabel.replace(/^先|^再/, '最后'),
  }))
})

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const formatPrice = (value) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(2)
}

const formatScore = (value) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(1)
}

const formatRatio = (value) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(1)
}

const formatSignedPct = (value) => {
  if (value === null || value === undefined) return '-'
  const num = Number(value)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const formatSignedNumber = (value, suffix = '') => {
  if (value === null || value === undefined) return '-'
  return `${Number(value).toFixed(1)}${suffix}`
}

const formatQty = (value) => {
  if (value === null || value === undefined) return '-'
  return `${value}股`
}

const formatMoney = (value) => {
  if (value === null || value === undefined) return '-'
  return `${Number(value).toFixed(0)}元`
}

const formatDays = (value) => {
  if (value === null || value === undefined) return '-'
  return `${value}天`
}

const pctClass = (value) => {
  if (value === null || value === undefined) return ''
  if (Number(value) > 0) return 'text-red'
  if (Number(value) < 0) return 'text-green'
  return 'text-neutral'
}

const sellTagType = (value) => {
  if (value === '卖出') return 'danger'
  if (value === '减仓') return 'warning'
  if (value === '持有') return 'success'
  return 'info'
}

const priorityTagType = (value) => {
  if (value === '高') return 'danger'
  if (value === '中') return 'warning'
  return 'info'
}

const accountEntryTag = (stock) => {
  if ((stock.pool_entry_reason || '').includes('防守')) return '防守试错'
  return '满足准入'
}

const accountEntryTagType = (stock) => {
  if ((stock.pool_entry_reason || '').includes('防守')) return 'warning'
  return 'success'
}

const marketActionLine = (stock) => stock.llm_plain_note || stock.stock_comment || '先观察这只票是否继续保持强势结构。'
const marketFooterLine = (stock) => `${stock.stock_strength_tag || '中'}强度，${stock.stock_continuity_tag || '可观察'}，继续等确认。`
const accountActionLine = (stock) => stock.llm_plain_note || stock.pool_entry_reason || stock.stock_comment || '这只票已通过账户准入，但仍要等买点确认。'
const accountFooterFlag = (stock) => ((stock.pool_entry_reason || '').includes('防守') ? '轻仓试错' : '等待买点页确认')
const holdingActionLine = (stock) => stock.llm_plain_note || `${stock.sell_signal_tag || '观察'}：${stock.sell_reason || stock.sell_comment || '继续跟踪。'}`
const holdingFooterFlag = (stock) => (stock.can_sell_today ? '今日可卖' : 'T+1锁定')

const sellSignalRank = (value) => {
  if (value === '卖出') return 0
  if (value === '减仓') return 1
  if (value === '持有') return 2
  return 3
}

const priorityRank = (value) => {
  if (value === '高') return 0
  if (value === '中') return 1
  return 2
}

const compareHoldingPriority = (a, b) => {
  const signalDiff = sellSignalRank(a.sell_signal_tag) - sellSignalRank(b.sell_signal_tag)
  if (signalDiff !== 0) return signalDiff
  const priorityDiff = priorityRank(a.sell_priority) - priorityRank(b.sell_priority)
  if (priorityDiff !== 0) return priorityDiff
  return Math.abs(Number(b.pnl_pct || 0)) - Math.abs(Number(a.pnl_pct || 0))
}

const holdingOrderLabel = (index) => {
  if (index === 0) return '先处理 '
  if (index === 1) return '再处理 '
  return '最后处理 '
}

const loadData = async () => {
  loading.value = true
  try {
    const tradeDate = getLocalDate()
    displayDate.value = tradeDate
    const res = await stockApi.pools(tradeDate, 50)
    poolsData.value = res.data.data || {
      market_watch_pool: [],
      account_executable_pool: [],
      holding_process_pool: [],
      resolved_trade_date: '',
      llm_status: null,
    }
    if (holdingCount.value) activeTab.value = 'holding'
    else if (accountCount.value) activeTab.value = 'account'
    else activeTab.value = 'market'
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  displayDate.value = getLocalDate()
  loadData()
})
</script>

<style scoped>
.pools-view {
  min-height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
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
    radial-gradient(circle at top right, rgba(88, 176, 255, 0.12), transparent 34%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.04));
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.overview-main {
  display: flex;
  align-items: center;
  gap: 18px;
}

.overview-badge {
  min-width: 124px;
  padding: 16px 18px;
  border-radius: 18px;
  font-size: 1.1rem;
  font-weight: 800;
  text-align: center;
  letter-spacing: 0.05em;
  color: #fff;
}

.badge-holding {
  background: linear-gradient(135deg, #cc6b28, #f39d56);
}

.badge-account {
  background: linear-gradient(135deg, #1d8b6f, #2fcf9a);
}

.badge-market {
  background: linear-gradient(135deg, #4f76d9, #67a5ff);
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

.overview-llm {
  padding: 10px 12px;
  border-radius: 12px;
  line-height: 1.6;
  color: var(--color-text-main);
  background: rgba(255, 255, 255, 0.04);
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

.top-focus {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.top-focus-title {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.top-focus-summary {
  color: var(--color-text-main);
  line-height: 1.6;
}

.top-focus-list {
  display: grid;
  gap: 8px;
}

.top-focus-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) minmax(240px, 1fr);
  gap: 12px;
  align-items: stretch;
}

.top-focus-rank {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #f1606c, #ff8f72);
}

.top-focus-main,
.top-focus-trigger {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.top-focus-meta,
.top-focus-trigger-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.top-focus-trigger-text {
  line-height: 1.55;
  color: var(--color-text-main);
}

.stat-card {
  display: grid;
  gap: 6px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(15, 23, 42, 0.38);
}

.stat-market {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.12);
}

.stat-account {
  box-shadow: inset 0 0 0 1px rgba(47, 207, 154, 0.12);
}

.stat-holding {
  box-shadow: inset 0 0 0 1px rgba(243, 157, 86, 0.12);
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.stat-value {
  font-size: 1.75rem;
  line-height: 1;
}

.stat-tip {
  font-size: 12px;
  color: var(--color-text-sec);
}

.rule-chip {
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--color-text-main);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.tab-count {
  font-style: normal;
  color: var(--color-text-sec);
}

.signal-grid {
  display: grid;
  gap: 16px;
  margin-top: 8px;
}

.signal-card {
  display: grid;
  gap: 16px;
  padding: 18px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.03));
}

.signal-card-market {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.08);
}

.signal-card-account {
  box-shadow: inset 0 0 0 1px rgba(47, 207, 154, 0.08);
}

.signal-card-holding {
  box-shadow: inset 0 0 0 1px rgba(243, 157, 86, 0.08);
}

.signal-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.signal-stock {
  font-size: 1.55rem;
  font-weight: 800;
  line-height: 1.1;
}

.signal-code {
  font-size: 13px;
  color: var(--color-text-sec);
  letter-spacing: 0.04em;
}

.signal-badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.signal-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--color-text-sec);
  font-size: 13px;
}

.signal-meta span {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
}

.signal-intent {
  padding: 18px 20px;
  border-radius: 20px;
  font-size: clamp(1rem, 1.4vw, 1.15rem);
  line-height: 1.65;
  font-weight: 700;
}

.signal-intent-market {
  color: #dbe9ff;
  background: rgba(76, 116, 211, 0.16);
  border: 1px solid rgba(103, 165, 255, 0.18);
}

.signal-intent-account {
  color: #dffdf1;
  background: rgba(30, 145, 103, 0.16);
  border: 1px solid rgba(47, 207, 154, 0.18);
}

.signal-intent-holding {
  color: #fff2df;
  background: rgba(204, 107, 40, 0.16);
  border: 1px solid rgba(243, 157, 86, 0.18);
}

.quote-strip,
.price-strip {
  display: grid;
  gap: 12px;
}

.quote-strip {
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  align-items: stretch;
}

.quote-main,
.quote-side,
.metric-card {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.quote-main {
  align-content: center;
}

.quote-label,
.metric-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.quote-price,
.metric-value {
  font-size: 1.15rem;
  font-weight: 700;
}

.quote-change {
  font-size: 14px;
  font-weight: 600;
}

.quote-side {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.quote-pair {
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-sec);
}

.quote-pair strong {
  color: var(--color-text-main);
  font-size: 1rem;
}

.price-strip {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.condition-section {
  display: grid;
  gap: 12px;
}

.section-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.condition-panel-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.condition-panel-grid-watch {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.condition-panel {
  display: grid;
  gap: 14px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.condition-panel-trigger {
  box-shadow: inset 0 0 0 1px rgba(90, 182, 146, 0.08);
}

.condition-panel-confirm {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.08);
}

.condition-panel-invalid {
  box-shadow: inset 0 0 0 1px rgba(255, 143, 114, 0.08);
}

.panel-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.panel-step {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-text-main);
  font-weight: 700;
}

.panel-title {
  font-weight: 700;
}

.panel-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-sec);
  line-height: 1.45;
}

.panel-body {
  color: var(--color-text-main);
  line-height: 1.7;
}

.condition-title {
  font-size: 0.98rem;
}

.signal-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}

.footer-flag {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-text-main);
  white-space: nowrap;
}

.text-red {
  color: #ff7b86;
}

.text-green {
  color: #35c48b;
}

.text-neutral {
  color: var(--color-text-main);
}

@media (max-width: 1024px) {
  .overview-main,
  .signal-card-header,
  .signal-footer {
    flex-direction: column;
    align-items: flex-start;
  }

  .overview-stats,
  .price-strip,
  .condition-panel-grid,
  .condition-panel-grid-watch,
  .quote-side {
    grid-template-columns: 1fr;
  }

  .quote-strip,
  .top-focus-item {
    grid-template-columns: 1fr;
  }

  .top-focus-rank {
    display: none;
  }
}
</style>
