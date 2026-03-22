<template>
  <view class="page">
    <view class="hero-card">
      <view class="hero-head">
        <view>
          <view class="page-title">三池分类</view>
          <view class="page-date">{{ today }}</view>
        </view>
        <view class="hero-badge" :class="heroBadgeClass">{{ heroBadge }}</view>
      </view>

      <view class="hero-title">{{ heroTitle }}</view>
      <view class="hero-desc">{{ heroDesc }}</view>

      <view class="stats-grid">
        <view class="stat-card stat-market">
          <text class="stat-label">观察池</text>
          <text class="stat-value">{{ marketCount }}</text>
          <text class="stat-tip">缩小盯盘范围</text>
        </view>
        <view class="stat-card stat-account">
          <text class="stat-label">可参与池</text>
          <text class="stat-value">{{ accountCount }}</text>
          <text class="stat-tip">通过账户准入</text>
        </view>
        <view class="stat-card stat-holding">
          <text class="stat-label">持仓处理池</text>
          <text class="stat-value">{{ holdingCount }}</text>
          <text class="stat-tip">今天优先处理</text>
        </view>
      </view>

      <view class="rule-row">
        <text v-for="rule in heroRules" :key="rule" class="rule-chip">{{ rule }}</text>
      </view>

      <view v-if="topFocusItems.length" class="focus-panel">
        <view class="focus-title">今天先看</view>
        <view v-for="item in topFocusItems" :key="item.poolKey + item.ts_code" class="focus-row">
          <view class="focus-rank">{{ item.rank }}</view>
          <view class="focus-main">
            <text class="focus-name">{{ item.orderLabel }}{{ item.stock_name }}</text>
            <text class="focus-meta">{{ item.meta }}</text>
            <text class="focus-text">{{ item.focus }}</text>
          </view>
        </view>
      </view>
    </view>

    <view class="tabs">
      <view
        v-for="tab in tabs"
        :key="tab.key"
        :class="['tab', activeTab === tab.key ? 'active' : '']"
        @click="activeTab = tab.key"
      >
        {{ tab.name }}
        <text class="tab-count">{{ getCount(tab.key) }}</text>
      </view>
    </view>

    <view v-if="loading" class="loading">
      <text>加载中...</text>
    </view>

    <view v-else class="card-stack">
      <view v-if="activeTab === 'market' && !marketCount" class="empty-card">
        <text>暂无需要观察的强势候选</text>
      </view>

      <view
        v-if="activeTab === 'market'"
        v-for="item in marketPool"
        :key="item.ts_code"
        class="signal-card signal-card-market"
      >
        <view class="signal-head">
          <view>
            <view class="signal-name">{{ item.stock_name }}</view>
            <view class="signal-code">{{ item.ts_code }}</view>
          </view>
          <view class="badge-row">
            <text class="badge badge-blue">{{ item.candidate_bucket_tag || '观察补充' }}</text>
            <text class="badge badge-gray">{{ item.stock_core_tag }}</text>
          </view>
        </view>

        <view class="meta-row">
          <text class="meta-chip">{{ item.sector_name || '无板块信息' }}</text>
          <text class="meta-chip">{{ item.candidate_source_tag || '无来源标记' }}</text>
        </view>

        <view class="intent-box intent-market">{{ item.stock_comment || '先看这只票是否继续保持强势结构。' }}</view>

        <view class="quote-grid">
          <view class="quote-card">
            <text class="quote-label">最新价</text>
            <text class="quote-value">{{ formatPrice(item.close) }}</text>
            <text :class="['quote-change', pctClass(item.change_pct)]">{{ formatSignedPct(item.change_pct) }}</text>
          </view>
          <view class="quote-card">
            <text class="quote-label">综合分</text>
            <text class="quote-value">{{ formatScore(item.stock_score) }}</text>
            <text class="quote-sub">量比 {{ formatRatio(item.vol_ratio) }}</text>
          </view>
        </view>

        <view class="mini-metrics">
          <view class="mini-card">
            <text class="mini-label">强弱</text>
            <text class="mini-value">{{ item.stock_strength_tag }}</text>
          </view>
          <view class="mini-card">
            <text class="mini-label">连续性</text>
            <text class="mini-value">{{ item.stock_continuity_tag }}</text>
          </view>
          <view class="mini-card">
            <text class="mini-label">交易性</text>
            <text class="mini-value">{{ item.stock_tradeability_tag }}</text>
          </view>
        </view>

        <view class="step-card">
          <text class="step-kicker">观察清单</text>
          <view class="step-panel">
            <view class="step-index">1</view>
            <view class="step-body">
              <text class="step-title">先看</text>
              <text class="step-text">{{ item.stock_comment || '先看板块和量能是否继续强化。' }}</text>
            </view>
          </view>
          <view class="step-panel step-risk">
            <view class="step-index">2</view>
            <view class="step-body">
              <text class="step-title">证伪</text>
              <text class="step-text">{{ item.stock_falsification_cond || '结构破坏或量能转弱时不再优先观察。' }}</text>
            </view>
          </view>
        </view>
      </view>

      <view v-if="activeTab === 'account' && !accountCount" class="empty-card">
        <text>当前没有满足账户准入的新标的</text>
      </view>

      <view
        v-if="activeTab === 'account'"
        v-for="item in accountPool"
        :key="item.ts_code"
        class="signal-card signal-card-account"
      >
        <view class="signal-head">
          <view>
            <view class="signal-name">{{ item.stock_name }}</view>
            <view class="signal-code">{{ item.ts_code }}</view>
          </view>
          <view class="badge-row">
            <text class="badge badge-green">{{ item.candidate_bucket_tag || '可参与' }}</text>
            <text :class="['badge', (item.pool_entry_reason || '').includes('防守') ? 'badge-orange' : 'badge-green-soft']">
              {{ (item.pool_entry_reason || '').includes('防守') ? '防守试错' : '满足准入' }}
            </text>
          </view>
        </view>

        <view class="meta-row">
          <text class="meta-chip">{{ item.sector_name || '无板块信息' }}</text>
          <text class="meta-chip">{{ item.candidate_source_tag || '无来源标记' }}</text>
        </view>

        <view class="intent-box intent-account">
          {{ item.pool_entry_reason || item.stock_comment || '这只票已通过账户准入，但仍要等买点确认。' }}
        </view>

        <view class="quote-grid">
          <view class="quote-card">
            <text class="quote-label">最新价</text>
            <text class="quote-value">{{ formatPrice(item.close) }}</text>
            <text :class="['quote-change', pctClass(item.change_pct)]">{{ formatSignedPct(item.change_pct) }}</text>
          </view>
          <view class="quote-card">
            <text class="quote-label">综合分</text>
            <text class="quote-value">{{ formatScore(item.stock_score) }}</text>
            <text class="quote-sub">换手 {{ formatPercent(item.turnover_rate) }}</text>
          </view>
        </view>

        <view class="mini-metrics">
          <view class="mini-card">
            <text class="mini-label">强弱</text>
            <text class="mini-value">{{ item.stock_strength_tag }}</text>
          </view>
          <view class="mini-card">
            <text class="mini-label">连续性</text>
            <text class="mini-value">{{ item.stock_continuity_tag }}</text>
          </view>
          <view class="mini-card">
            <text class="mini-label">交易性</text>
            <text class="mini-value">{{ item.stock_tradeability_tag }}</text>
          </view>
        </view>

        <view class="step-card">
          <text class="step-kicker">执行清单</text>
          <view class="step-panel">
            <view class="step-index">1</view>
            <view class="step-body">
              <text class="step-title">为什么能进池</text>
              <text class="step-text">{{ item.pool_entry_reason || item.stock_comment || '满足常规开仓条件。' }}</text>
            </view>
          </view>
          <view class="step-panel">
            <view class="step-index">2</view>
            <view class="step-body">
              <text class="step-title">仓位提示</text>
              <text class="step-text">{{ item.position_hint || '按计划仓位执行，不要超配。' }}</text>
            </view>
          </view>
        </view>
      </view>

      <view v-if="activeTab === 'holding' && !holdingCount" class="empty-card">
        <text>暂无持仓或持仓未进入当日行情</text>
      </view>

      <view
        v-if="activeTab === 'holding'"
        v-for="item in holdingPool"
        :key="item.ts_code"
        class="signal-card signal-card-holding"
      >
        <view class="signal-head">
          <view>
            <view class="signal-name">{{ item.stock_name }}</view>
            <view class="signal-code">{{ item.ts_code }}</view>
          </view>
          <view class="badge-row">
            <text :class="['badge', actionClass(item.sell_signal_tag)]">{{ item.sell_signal_tag || '观察' }}</text>
            <text :class="['badge', priorityBadgeClass(item.sell_priority)]">{{ `${item.sell_priority || '低'}优先` }}</text>
          </view>
        </view>

        <view class="meta-row">
          <text class="meta-chip">{{ item.sector_name || '无板块信息' }}</text>
          <text class="meta-chip">{{ item.holding_reason || '无买入理由记录' }}</text>
        </view>

        <view class="intent-box intent-holding">
          {{ `${item.sell_signal_tag || '观察'}：${item.sell_reason || item.sell_comment || '继续跟踪。'}` }}
        </view>

        <view class="quote-grid">
          <view class="quote-card">
            <text class="quote-label">现价 / 成本</text>
            <text class="quote-value">{{ formatPrice(item.close) }} / {{ formatPrice(item.cost_price) }}</text>
            <text :class="['quote-change', pctClass(item.pnl_pct)]">{{ formatSignedPct(item.pnl_pct) }}</text>
          </view>
          <view class="quote-card">
            <text class="quote-label">持仓 / 市值</text>
            <text class="quote-value">{{ formatQty(item.holding_qty) }}</text>
            <text class="quote-sub">{{ formatMoney(item.holding_market_value) }}</text>
          </view>
        </view>

        <view class="mini-metrics">
          <view class="mini-card">
            <text class="mini-label">持有天数</text>
            <text class="mini-value">{{ formatDays(item.holding_days) }}</text>
          </view>
          <view class="mini-card">
            <text class="mini-label">可卖状态</text>
            <text class="mini-value">{{ item.can_sell_today ? '今日可卖' : 'T+1锁定' }}</text>
          </view>
          <view class="mini-card">
            <text class="mini-label">交易性</text>
            <text class="mini-value">{{ item.stock_tradeability_tag }}</text>
          </view>
        </view>

        <view class="step-card">
          <text class="step-kicker">处理清单</text>
          <view class="step-panel">
            <view class="step-index">1</view>
            <view class="step-body">
              <text class="step-title">动作</text>
              <text class="step-text">{{ item.sell_reason || item.sell_comment || '当前没有明确动作建议。' }}</text>
            </view>
          </view>
          <view class="step-panel">
            <view class="step-index">2</view>
            <view class="step-body">
              <text class="step-title">动手条件</text>
              <text class="step-text">{{ item.sell_trigger_cond || '继续跟踪盘中强弱和板块共振。' }}</text>
            </view>
          </view>
          <view class="step-panel step-risk">
            <view class="step-index">3</view>
            <view class="step-body">
              <text class="step-title">买入前提</text>
              <text class="step-text">{{ item.stock_falsification_cond || '若买入逻辑失效，就不要继续硬扛。' }}</text>
            </view>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { stockApi, getToday } from '../../api'

const today = ref(getToday())
const activeTab = ref('holding')
const loading = ref(false)
const pools = ref({ market_watch_pool: [], account_executable_pool: [], holding_process_pool: [] })

const tabs = [
  { key: 'market', name: '观察池' },
  { key: 'account', name: '可参与池' },
  { key: 'holding', name: '处理池' }
]

const marketCount = computed(() => pools.value.market_watch_pool?.length || 0)
const accountCount = computed(() => pools.value.account_executable_pool?.length || 0)
const holdingCount = computed(() => pools.value.holding_process_pool?.length || 0)

const marketPool = computed(() =>
  [...(pools.value.market_watch_pool || [])].sort((a, b) => Number(b.stock_score || 0) - Number(a.stock_score || 0))
)
const accountPool = computed(() =>
  [...(pools.value.account_executable_pool || [])].sort((a, b) => Number(b.stock_score || 0) - Number(a.stock_score || 0))
)
const holdingPool = computed(() =>
  [...(pools.value.holding_process_pool || [])].sort(compareHoldingPriority)
)

const heroBadge = computed(() => {
  if (holdingCount.value) return '先处理持仓'
  if (accountCount.value) return '看可参与'
  return '先看观察池'
})

const heroBadgeClass = computed(() => {
  if (holdingCount.value) return 'hero-badge-holding'
  if (accountCount.value) return 'hero-badge-account'
  return 'hero-badge-market'
})

const heroTitle = computed(() => {
  if (holdingCount.value) return '已有仓位优先，先把该卖、该减、该持有的动作排清楚'
  if (accountCount.value) return '当前有能执行的新标的，先看账户可参与池'
  if (marketCount.value) return '当前更适合先观察市场最强结构'
  return '今天三池都比较清淡，先等新的结构和账户信号'
})

const heroDesc = computed(() => {
  if (holdingCount.value) return '持仓处理池优先级最高；先处理旧仓风险，再决定是否看新票。'
  if (accountCount.value) return '可参与池说明系统已通过账户准入，但真正执行仍要结合买点确认。'
  if (marketCount.value) return '观察池只负责缩小盯盘范围，不是直接下单列表。'
  return '当前没有明显需要处理的仓位，也没有通过准入的新标的。'
})

const heroRules = computed(() => {
  if (holdingCount.value) return ['先处理旧仓', '高优先级先动', '证伪到了就别拖']
  if (accountCount.value) return ['先看进池理由', '先按仓位提示执行', '别把可参与当立刻追价']
  return ['观察池只看方向', '先看最强结构', '没有确认就不执行']
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
      orderLabel: items.length === 0 ? '先处理 ' : '再处理 '
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
      orderLabel: items.length === 0 ? '先看 ' : '再看 '
    })
  } else if (marketPool.value.length) {
    const stock = marketPool.value[0]
    items.push({
      poolKey: 'market',
      ts_code: stock.ts_code,
      stock_name: stock.stock_name,
      focus: stock.stock_comment || stock.stock_falsification_cond || '先看板块和量能',
      meta: `观察池 / ${stock.candidate_bucket_tag || '未分层'} / ${formatSignedPct(stock.change_pct)}`,
      orderLabel: items.length === 0 ? '先盯 ' : '再盯 '
    })
  }

  return items.slice(0, 3).map((item, index) => ({
    ...item,
    rank: index + 1,
    orderLabel: index === 0 ? item.orderLabel : index === 1 ? item.orderLabel.replace(/^先/, '再') : item.orderLabel.replace(/^先|^再/, '最后')
  }))
})

const getCount = (key) => {
  if (key === 'market') return marketCount.value
  if (key === 'account') return accountCount.value
  return holdingCount.value
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

const formatPercent = (value) => {
  if (value === null || value === undefined) return '-'
  return `${Number(value).toFixed(1)}%`
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
  if (value === null || value === undefined) return 'text-neutral'
  if (Number(value) > 0) return 'text-red'
  if (Number(value) < 0) return 'text-green'
  return 'text-neutral'
}

const actionClass = (value) => {
  if (value === '卖出') return 'badge-red'
  if (value === '减仓') return 'badge-orange'
  if (value === '持有') return 'badge-green-soft'
  return 'badge-gray'
}

const priorityBadgeClass = (value) => {
  if (value === '高') return 'badge-red-soft'
  if (value === '中') return 'badge-orange-soft'
  return 'badge-gray'
}

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

const loadData = async () => {
  loading.value = true
  try {
    const res = await stockApi.pools(today.value, 50)
    pools.value = res.data.data
    if (holdingCount.value) activeTab.value = 'holding'
    else if (accountCount.value) activeTab.value = 'account'
    else activeTab.value = 'market'
  } catch (e) {
    console.error('加载失败', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.page {
  padding: 20rpx;
  background: #101521;
  min-height: 100vh;
  color: #edf2ff;
}

.hero-card,
.signal-card,
.empty-card {
  background: linear-gradient(180deg, rgba(33, 39, 52, 0.98), rgba(27, 33, 46, 0.98));
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 28rpx;
  padding: 28rpx;
  box-sizing: border-box;
}

.hero-card {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
  margin-bottom: 20rpx;
}

.hero-head {
  display: flex;
  justify-content: space-between;
  gap: 20rpx;
}

.page-title {
  font-size: 38rpx;
  font-weight: 700;
}

.page-date {
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #98a2b3;
}

.hero-badge {
  padding: 12rpx 18rpx;
  border-radius: 999rpx;
  font-size: 24rpx;
  font-weight: 700;
  align-self: flex-start;
}

.hero-badge-holding {
  background: rgba(243, 157, 86, 0.2);
  color: #ffd6b1;
}

.hero-badge-account {
  background: rgba(47, 207, 154, 0.2);
  color: #c8ffea;
}

.hero-badge-market {
  background: rgba(103, 165, 255, 0.2);
  color: #d7e6ff;
}

.hero-title {
  font-size: 32rpx;
  font-weight: 700;
  line-height: 1.5;
}

.hero-desc {
  font-size: 26rpx;
  color: #98a2b3;
  line-height: 1.7;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16rpx;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 10rpx;
  padding: 20rpx;
  border-radius: 22rpx;
  background: rgba(255, 255, 255, 0.03);
}

.stat-market {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.14);
}

.stat-account {
  box-shadow: inset 0 0 0 1px rgba(47, 207, 154, 0.14);
}

.stat-holding {
  box-shadow: inset 0 0 0 1px rgba(243, 157, 86, 0.14);
}

.stat-label,
.stat-tip,
.focus-title,
.step-kicker,
.quote-label,
.mini-label {
  font-size: 22rpx;
  color: #98a2b3;
}

.stat-value {
  font-size: 44rpx;
  font-weight: 800;
}

.rule-row,
.meta-row,
.badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
}

.rule-chip,
.meta-chip,
.badge {
  padding: 8rpx 16rpx;
  border-radius: 999rpx;
  font-size: 22rpx;
}

.rule-chip,
.meta-chip {
  background: rgba(255, 255, 255, 0.04);
  color: #c5cfdd;
}

.focus-panel {
  display: flex;
  flex-direction: column;
  gap: 14rpx;
  padding: 20rpx;
  border-radius: 24rpx;
  background: rgba(255, 255, 255, 0.025);
}

.focus-row {
  display: flex;
  gap: 16rpx;
  align-items: flex-start;
}

.focus-rank {
  width: 44rpx;
  height: 44rpx;
  border-radius: 999rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24rpx;
  font-weight: 700;
  background: linear-gradient(135deg, #f1606c, #ff8f72);
  color: #fff;
}

.focus-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.focus-name {
  font-size: 30rpx;
  font-weight: 700;
}

.focus-meta {
  font-size: 22rpx;
  color: #98a2b3;
}

.focus-text {
  font-size: 26rpx;
  line-height: 1.6;
}

.tabs {
  display: flex;
  gap: 10rpx;
  margin-bottom: 16rpx;
}

.tab {
  flex: 1;
  padding: 18rpx 10rpx;
  text-align: center;
  border-radius: 20rpx;
  background: rgba(255, 255, 255, 0.04);
  color: #98a2b3;
  font-size: 24rpx;
}

.tab.active {
  background: rgba(76, 116, 211, 0.18);
  color: #edf2ff;
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.18);
}

.tab-count {
  margin-left: 6rpx;
  font-size: 22rpx;
}

.card-stack {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.signal-card {
  display: flex;
  flex-direction: column;
  gap: 18rpx;
}

.signal-card-market {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.12);
}

.signal-card-account {
  box-shadow: inset 0 0 0 1px rgba(47, 207, 154, 0.12);
}

.signal-card-holding {
  box-shadow: inset 0 0 0 1px rgba(243, 157, 86, 0.12);
}

.signal-head {
  display: flex;
  justify-content: space-between;
  gap: 16rpx;
}

.signal-name {
  font-size: 40rpx;
  font-weight: 800;
  line-height: 1.15;
}

.signal-code {
  margin-top: 6rpx;
  font-size: 24rpx;
  color: #98a2b3;
}

.intent-box {
  padding: 22rpx;
  border-radius: 22rpx;
  font-size: 30rpx;
  line-height: 1.65;
  font-weight: 700;
}

.intent-market {
  color: #dbe9ff;
  background: rgba(76, 116, 211, 0.16);
}

.intent-account {
  color: #dffdf1;
  background: rgba(30, 145, 103, 0.16);
}

.intent-holding {
  color: #fff2df;
  background: rgba(204, 107, 40, 0.16);
}

.quote-grid,
.mini-metrics {
  display: grid;
  gap: 14rpx;
}

.quote-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.quote-card,
.mini-card,
.step-panel {
  padding: 20rpx;
  border-radius: 22rpx;
  background: rgba(255, 255, 255, 0.03);
}

.quote-card {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.quote-value,
.mini-value {
  font-size: 32rpx;
  font-weight: 700;
}

.quote-sub {
  font-size: 22rpx;
  color: #98a2b3;
}

.quote-change {
  font-size: 24rpx;
  font-weight: 600;
}

.mini-metrics {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.step-card {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.step-panel {
  display: flex;
  gap: 16rpx;
}

.step-risk {
  box-shadow: inset 0 0 0 1px rgba(255, 143, 114, 0.12);
}

.step-index {
  width: 44rpx;
  height: 44rpx;
  border-radius: 999rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24rpx;
  font-weight: 700;
  background: rgba(255, 255, 255, 0.08);
}

.step-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.step-title {
  font-size: 26rpx;
  font-weight: 700;
}

.step-text {
  font-size: 26rpx;
  line-height: 1.65;
  color: #edf2ff;
}

.empty-card,
.loading {
  text-align: center;
  padding: 40rpx 20rpx;
  color: #98a2b3;
  font-size: 26rpx;
}

.badge-blue {
  background: rgba(76, 116, 211, 0.18);
  color: #dbe9ff;
}

.badge-green {
  background: rgba(30, 145, 103, 0.18);
  color: #dffdf1;
}

.badge-green-soft {
  background: rgba(47, 207, 154, 0.14);
  color: #c8ffea;
}

.badge-orange {
  background: rgba(243, 157, 86, 0.18);
  color: #ffd6b1;
}

.badge-orange-soft {
  background: rgba(243, 157, 86, 0.12);
  color: #ffd6b1;
}

.badge-red {
  background: rgba(241, 96, 108, 0.2);
  color: #ffd0d5;
}

.badge-red-soft {
  background: rgba(241, 96, 108, 0.14);
  color: #ffd0d5;
}

.badge-gray {
  background: rgba(255, 255, 255, 0.08);
  color: #d3dae6;
}

.text-red {
  color: #ff7b86;
}

.text-green {
  color: #35c48b;
}

.text-neutral {
  color: #edf2ff;
}
</style>
