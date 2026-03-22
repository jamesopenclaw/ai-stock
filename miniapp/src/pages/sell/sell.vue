<template>
  <view class="page">
    <view class="card">
      <view class="card-title">卖点分析</view>

      <view class="summary-card">
        <view class="summary-copy">
          <text class="summary-title">{{ summaryTitle }}</text>
          <text class="summary-desc">{{ summaryDesc }}</text>
        </view>
        <view class="summary-stats">
          <view class="stat-item stat-sell">
            <text class="stat-label">卖出</text>
            <text class="stat-value">{{ sellData.sell_positions?.length || 0 }}</text>
          </view>
          <view class="stat-item stat-reduce">
            <text class="stat-label">减仓</text>
            <text class="stat-value">{{ sellData.reduce_positions?.length || 0 }}</text>
          </view>
          <view class="stat-item stat-hold">
            <text class="stat-label">持有</text>
            <text class="stat-value">{{ sellData.hold_positions?.length || 0 }}</text>
          </view>
        </view>
        <view v-if="topActions.length" class="top-actions">
          <view class="top-actions-title">今天先处理</view>
          <view v-for="item in topActions" :key="item.ts_code" class="top-action-row">
            <text class="top-action-rank">{{ item.rank }}</text>
            <view class="top-action-copy">
              <text class="top-action-name">{{ item.orderLabel }}{{ item.stock_name }}</text>
              <text class="top-action-desc">{{ item.sell_trigger_cond || item.sell_reason }}</text>
            </view>
          </view>
        </view>
      </view>
      
      <view class="tabs">
        <view :class="['tab', activeTab === 'sell' ? 'active' : '']" @click="activeTab = 'sell'">
          卖出 ({{ sellData.sell_positions?.length || 0 }})
        </view>
        <view :class="['tab', activeTab === 'reduce' ? 'active' : '']" @click="activeTab = 'reduce'">
          减仓 ({{ sellData.reduce_positions?.length || 0 }})
        </view>
        <view :class="['tab', activeTab === 'hold' ? 'active' : '']" @click="activeTab = 'hold'">
          持有 ({{ sellData.hold_positions?.length || 0 }})
        </view>
      </view>

      <view class="sell-list">
        <view
          v-for="(item, index) in currentList"
          :key="item.ts_code + index"
          class="sell-item"
          @click="toggleDetail(item)"
        >
          <view class="sell-header">
            <view class="sell-info">
              <text class="sell-name">{{ item.stock_name }}</text>
              <text class="sell-code">{{ item.ts_code }}</text>
            </view>
            <view class="sell-right">
              <text :class="['signal-tag', signalClass(item.sell_signal_tag)]">{{ item.sell_signal_tag }}</text>
            </view>
          </view>

          <view :class="['action-box', actionClass(item.sell_signal_tag)]">
            <text>{{ actionLine(item) }}</text>
          </view>

          <view class="quote-grid">
            <view class="quote-card">
              <text class="quote-label">现价 / 成本</text>
              <text class="quote-value">{{ formatPrice(item.market_price) }} / {{ formatPrice(item.cost_price) }}</text>
            </view>
            <view class="quote-card">
              <text class="quote-label">浮盈亏</text>
              <text :class="['quote-value', pnlClass(item.pnl_pct)]">{{ formatSignedPct(item.pnl_pct) }}</text>
            </view>
            <view class="quote-card">
              <text class="quote-label">持仓 / 天数</text>
              <text class="quote-value">{{ formatQty(item.holding_qty) }} / {{ formatDays(item.holding_days) }}</text>
            </view>
          </view>

          <view v-if="expandedItem === item.ts_code" class="detail-panel">
            <view class="detail-block">
              <text class="detail-title">原因</text>
              <text class="detail-content">{{ item.sell_reason }}</text>
            </view>
            <view class="detail-block">
              <text class="detail-title">执行条件</text>
              <text class="detail-content">{{ item.sell_trigger_cond }}</text>
            </view>
            <view class="detail-block">
              <text class="detail-title">说明</text>
              <text class="detail-content">{{ item.sell_comment || '-' }}</text>
            </view>
            <view class="detail-block">
              <text class="detail-title">状态</text>
              <text class="detail-content">{{ item.sell_priority }}优先 / {{ item.can_sell_today ? '今日可卖' : 'T+1锁定' }}</text>
            </view>
          </view>
        </view>
      </view>
    </view>

    <view v-if="loading" class="loading">
      <text>加载中...</text>
    </view>
  </view>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { decisionApi, getToday } from '../../api'

const today = ref(getToday())
const activeTab = ref('sell')
const loading = ref(false)
const sellData = ref({ sell_positions: [], reduce_positions: [], hold_positions: [] })
const expandedItem = ref(null)

const currentList = computed(() => {
  if (activeTab.value === 'sell') return sellData.value.sell_positions || []
  if (activeTab.value === 'reduce') return sellData.value.reduce_positions || []
  return sellData.value.hold_positions || []
})

const summaryTitle = computed(() => {
  if (sellData.value.sell_positions?.length) return '先处理明确该卖的持仓'
  if (sellData.value.reduce_positions?.length) return '当前以减仓降风险为主'
  return '当前以持有观察为主'
})

const summaryDesc = computed(() => {
  if (sellData.value.sell_positions?.length) return '优先看卖出区，再看减仓区，不要把动作混在一起处理。'
  if (sellData.value.reduce_positions?.length) return '这批票更适合先收缩仓位，不代表整笔逻辑完全结束。'
  return '当前没有强制离场动作，先盯住后续处理条件。'
})

const topActions = computed(() => {
  const ordered = [
    ...(sellData.value.sell_positions || []),
    ...(sellData.value.reduce_positions || []),
    ...(sellData.value.hold_positions || []),
  ]
  return ordered.slice(0, 2).map((item, index) => ({
    ...item,
    rank: index + 1,
    orderLabel: orderLabel(index, item.sell_signal_tag),
  }))
})

const toggleDetail = (item) => {
  expandedItem.value = expandedItem.value === item.ts_code ? null : item.ts_code
}

const actionLine = (item) => {
  if (item.sell_signal_tag === '卖出') return `优先处理：${item.sell_reason}`
  if (item.sell_signal_tag === '减仓') return `先降风险：${item.sell_reason}`
  return `继续跟踪：${item.sell_comment || item.sell_reason}`
}

const orderLabel = (index, signal) => {
  const prefix = index === 0 ? '先' : '再'
  if (signal === '卖出') return `${prefix}卖出 `
  if (signal === '减仓') return `${prefix}减仓 `
  return `${prefix}观察 `
}

const actionClass = (signal) => {
  if (signal === '卖出') return 'action-sell'
  if (signal === '减仓') return 'action-reduce'
  return 'action-hold'
}

const signalClass = (signal) => {
  if (signal === '卖出') return 'signal-sell'
  if (signal === '减仓') return 'signal-reduce'
  return 'signal-hold'
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

const pnlClass = (value) => {
  if (value === null || value === undefined) return ''
  if (Number(value) > 0) return 'text-red'
  if (Number(value) < 0) return 'text-green'
  return 'text-neutral'
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await decisionApi.sellPoint(today.value)
    sellData.value = res.data.data
    if (sellData.value.sell_positions?.length) activeTab.value = 'sell'
    else if (sellData.value.reduce_positions?.length) activeTab.value = 'reduce'
    else activeTab.value = 'hold'
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
.page { padding: 10px; }

.card { background: #fff; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
.card-title { font-size: 16px; font-weight: bold; margin-bottom: 12px; }

.summary-card {
  margin-bottom: 14px;
  padding: 14px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(245, 108, 108, 0.08), rgba(64, 158, 255, 0.04));
}

.summary-copy { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.summary-title { font-size: 15px; font-weight: 700; }
.summary-desc { font-size: 12px; color: #666; line-height: 1.5; }

.summary-stats { display: flex; gap: 10px; }
.stat-item { flex: 1; display: flex; flex-direction: column; gap: 4px; padding: 10px; border-radius: 10px; background: rgba(255,255,255,0.65); }
.stat-label { font-size: 12px; color: #666; }
.stat-value { font-size: 22px; font-weight: 700; }
.stat-sell .stat-value { color: #f56c6c; }
.stat-reduce .stat-value { color: #e6a23c; }
.stat-hold .stat-value { color: #67c23a; }

.top-actions { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.top-actions-title { font-size: 12px; color: #666; letter-spacing: 0.08em; text-transform: uppercase; }
.top-action-row { display: flex; gap: 10px; align-items: flex-start; padding: 10px; border-radius: 10px; background: rgba(255,255,255,0.65); }
.top-action-rank { width: 22px; height: 22px; border-radius: 999px; background: #f56c6c; color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
.top-action-copy { display: flex; flex-direction: column; gap: 3px; }
.top-action-name { font-size: 13px; font-weight: 600; }
.top-action-desc { font-size: 12px; color: #666; line-height: 1.5; }

.tabs { display: flex; margin-bottom: 15px; }
.tab { flex: 1; text-align: center; padding: 10px; border-bottom: 2px solid transparent; }
.tab.active { border-color: #409eff; color: #409eff; }

.sell-list { display: flex; flex-direction: column; gap: 12px; }
.sell-item { padding: 12px; border-radius: 12px; background: #fafafa; border: 1px solid #f0f0f0; }
.sell-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.sell-info { display: flex; flex-direction: column; }
.sell-name { font-weight: bold; }
.sell-code { font-size: 12px; color: #999; }
.signal-tag { font-size: 12px; padding: 4px 10px; border-radius: 999px; }
.signal-sell { background: #fef0f0; color: #f56c6c; }
.signal-reduce { background: #fdf6ec; color: #e6a23c; }
.signal-hold { background: #f0f9eb; color: #67c23a; }

.action-box { padding: 12px; border-radius: 12px; line-height: 1.6; margin-bottom: 10px; }
.action-sell { background: rgba(245, 108, 108, 0.08); border: 1px solid rgba(245, 108, 108, 0.18); }
.action-reduce { background: rgba(230, 162, 60, 0.08); border: 1px solid rgba(230, 162, 60, 0.18); }
.action-hold { background: rgba(103, 194, 58, 0.08); border: 1px solid rgba(103, 194, 58, 0.18); }

.quote-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 10px; }
.quote-card { display: flex; flex-direction: column; gap: 4px; padding: 10px; border-radius: 10px; background: #fff; }
.quote-label { font-size: 12px; color: #999; }
.quote-value { font-size: 15px; font-weight: 600; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
.text-neutral { color: #909399; }

.detail-panel { margin-top: 6px; padding-top: 10px; border-top: 1px solid #eee; display: flex; flex-direction: column; gap: 10px; }
.detail-block { display: flex; flex-direction: column; gap: 4px; }
.detail-title { font-size: 12px; color: #999; }
.detail-content { font-size: 14px; color: #333; line-height: 1.6; }

.loading { text-align: center; padding: 30px; color: #999; }
</style>
