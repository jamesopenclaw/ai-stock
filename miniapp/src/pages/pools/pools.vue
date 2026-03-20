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
        <view v-if="activeTab === 'market'" v-for="item in pools.market_watch_pool" :key="item.ts_code" class="stock-item">
          <view class="stock-info">
            <text class="stock-name">{{ item.stock_name }}</text>
            <text class="stock-code">{{ item.ts_code }}</text>
          </view>
          <view class="stock-extra">
            <text class="stock-sector">{{ item.sector_name }}</text>
            <text :class="item.change_pct > 0 ? 'text-red' : 'text-green'">
              {{ item.change_pct?.toFixed(2) }}%
            </text>
          </view>
        </view>

        <view v-if="activeTab === 'account'" v-for="item in pools.account_executable_pool" :key="item.ts_code" class="stock-item">
          <view class="stock-info">
            <text class="stock-name">{{ item.stock_name }}</text>
            <text class="stock-code">{{ item.ts_code }}</text>
          </view>
          <view class="stock-extra">
            <text class="stock-sector">{{ item.sector_name }}</text>
            <text :class="item.change_pct > 0 ? 'text-red' : 'text-green'">
              {{ item.change_pct?.toFixed(2) }}%
            </text>
          </view>
        </view>

        <view v-if="activeTab === 'holding'" v-for="item in pools.holding_process_pool" :key="item.ts_code" class="stock-item">
          <view class="stock-info">
            <text class="stock-name">{{ item.stock_name }}</text>
            <text class="stock-code">{{ item.ts_code }}</text>
          </view>
          <view class="stock-extra">
            <text class="stock-sector">{{ item.sector_name }}</text>
            <text :class="item.change_pct > 0 ? 'text-red' : 'text-green'">
              {{ item.change_pct?.toFixed(2) }}%
            </text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { stockApi, getToday } from '../../api'

const today = ref(getToday())
const activeTab = ref('market')
const pools = ref({ market_watch_pool: [], account_executable_pool: [], holding_process_pool: [] })

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

const loadData = async () => {
  try {
    const res = await stockApi.pools(today.value, 50)
    pools.value = res.data.data
  } catch (e) {
    console.error('加载失败', e)
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
.stock-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #f5f5f5; }
.stock-info { display: flex; flex-direction: column; }
.stock-name { font-weight: bold; }
.stock-code { font-size: 12px; color: #999; }
.stock-extra { text-align: right; }
.stock-sector { font-size: 12px; color: #999; display: block; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
</style>
