<template>
  <view class="page">
    <view class="card">
      <view class="card-title">三池分类</view>
      
      <view class="tabs">
        <view 
          v-for="tab in tabs" 
          :key="tab.key" 
          :class="['tab', activeTab === tab.key ? 'active' : '']"
          @click="activeTab = tab.key"
        >
          {{ tab.name }} ({{ getCount(tab.key) }})
        </view>
      </view>

      <view class="stock-list">
        <!-- 市场观察池 -->
        <view v-if="activeTab === 'market'" v-for="(item, index) in pools.market_watch_pool" :key="item.ts_code + index" class="stock-item" @click="toggleDetail(item)">
          <view class="stock-header">
            <view class="stock-info">
              <text class="stock-name">{{ item.stock_name }}</text>
              <text class="stock-code">{{ item.ts_code }}</text>
            </view>
            <view class="stock-right">
              <text class="stock-sector">{{ item.sector_name }}</text>
              <text :class="['stock-change', item.change_pct > 0 ? 'text-red' : 'text-green']">
                {{ item.change_pct?.toFixed(2) }}%
              </text>
            </view>
          </view>
          <!-- 详情展开 -->
          <view v-if="expandedItem === item.ts_code" class="stock-detail">
            <view class="detail-row">
              <text class="detail-label">强度标签</text>
              <text class="detail-value">{{ item.stock_strength_tag }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">连续性</text>
              <text class="detail-value">{{ item.stock_continuity_tag }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">核心属性</text>
              <text class="detail-value">{{ item.stock_core_tag }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">交易性</text>
              <text class="detail-value">{{ item.stock_tradeability_tag }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">证伪条件</text>
              <text class="detail-value">{{ item.stock_falsification_cond }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">简评</text>
              <text class="detail-value">{{ item.stock_comment }}</text>
            </view>
          </view>
        </view>

        <!-- 账户可参与池 -->
        <view v-if="activeTab === 'account'" v-for="(item, index) in pools.account_executable_pool" :key="item.ts_code + index" class="stock-item" @click="toggleDetail(item)">
          <view class="stock-header">
            <view class="stock-info">
              <text class="stock-name">{{ item.stock_name }}</text>
              <text class="stock-code">{{ item.ts_code }}</text>
            </view>
            <view class="stock-right">
              <text class="stock-sector">{{ item.sector_name }}</text>
              <text :class="['stock-change', item.change_pct > 0 ? 'text-red' : 'text-green']">
                {{ item.change_pct?.toFixed(2) }}%
              </text>
            </view>
          </view>
          <view v-if="expandedItem === item.ts_code" class="stock-detail">
            <view class="detail-row">
              <text class="detail-label">核心属性</text>
              <text class="detail-value">{{ item.stock_core_tag }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">交易性</text>
              <text class="detail-value">{{ item.stock_tradeability_tag }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">简评</text>
              <text class="detail-value">{{ item.stock_comment }}</text>
            </view>
          </view>
        </view>

        <!-- 持仓处理池 -->
        <view v-if="activeTab === 'holding'" v-for="(item, index) in pools.holding_process_pool" :key="item.ts_code + index" class="stock-item" @click="toggleDetail(item)">
          <view class="stock-header">
            <view class="stock-info">
              <text class="stock-name">{{ item.stock_name }}</text>
              <text class="stock-code">{{ item.ts_code }}</text>
            </view>
            <view class="stock-right">
              <text class="stock-sector">{{ item.sector_name }}</text>
              <text :class="['stock-change', item.change_pct > 0 ? 'text-red' : 'text-green']">
                {{ item.change_pct?.toFixed(2) }}%
              </text>
            </view>
          </view>
          <view v-if="expandedItem === item.ts_code" class="stock-detail">
            <view class="detail-row">
              <text class="detail-label">强度标签</text>
              <text class="detail-value">{{ item.stock_strength_tag }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">连续性</text>
              <text class="detail-value">{{ item.stock_continuity_tag }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">核心属性</text>
              <text class="detail-value">{{ item.stock_core_tag }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">简评</text>
              <text class="detail-value">{{ item.stock_comment }}</text>
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
import { ref, onMounted } from 'vue'
import { stockApi, getToday } from '../../api'

const today = ref(getToday())
const activeTab = ref('market')
const loading = ref(false)
const pools = ref({ market_watch_pool: [], account_executable_pool: [], holding_process_pool: [] })
const expandedItem = ref(null)

const tabs = [
  { key: 'market', name: '观察池' },
  { key: 'account', name: '可参与' },
  { key: 'holding', name: '处理池' }
]

const getCount = (key) => {
  if (key === 'market') return pools.value.market_watch_pool?.length || 0
  if (key === 'account') return pools.value.account_executable_pool?.length || 0
  return pools.value.holding_process_pool?.length || 0
}

const toggleDetail = (item) => {
  expandedItem.value = expandedItem.value === item.ts_code ? null : item.ts_code
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await stockApi.pools(today.value, 50)
    pools.value = res.data.data
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
.card-title { font-size: 16px; font-weight: bold; margin-bottom: 10px; }

.tabs { display: flex; margin-bottom: 15px; }
.tab { flex: 1; text-align: center; padding: 10px; border-bottom: 2px solid transparent; }
.tab.active { border-color: #409eff; color: #409eff; }

.stock-list { display: flex; flex-direction: column; }
.stock-item { padding: 12px 0; border-bottom: 1px solid #f5f5f5; }
.stock-header { display: flex; justify-content: space-between; align-items: center; }
.stock-info { display: flex; flex-direction: column; }
.stock-name { font-weight: bold; }
.stock-code { font-size: 12px; color: #999; }
.stock-right { display: flex; flex-direction: column; align-items: flex-end; }
.stock-sector { font-size: 12px; color: #999; }
.stock-change { font-weight: bold; }

.stock-detail { margin-top: 10px; padding: 10px; background: #f9f9f9; border-radius: 8px; }
.detail-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #eee; }
.detail-row:last-child { border-bottom: none; }
.detail-label { font-size: 12px; color: #999; }
.detail-value { font-size: 14px; color: #333; }

.loading { text-align: center; padding: 30px; color: #999; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
</style>
