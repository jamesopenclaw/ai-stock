<template>
  <view class="page">
    <view class="card">
      <view class="card-title">买点分析</view>
      <view v-if="buyData.market_env_tag" class="env-tip">
        市场环境：{{ buyData.market_env_tag }}
      </view>
      
      <view class="tabs">
        <view :class="['tab', activeTab === 'available' ? 'active' : '']" @click="activeTab = 'available'">
          可买 ({{ buyData.available_buy_points?.length || 0 }})
        </view>
        <view :class="['tab', activeTab === 'observe' ? 'active' : '']" @click="activeTab = 'observe'">
          观察 ({{ buyData.observe_buy_points?.length || 0 }})
        </view>
      </view>

      <view class="buy-list">
        <view v-if="activeTab === 'available'" v-for="item in buyData.available_buy_points" :key="item.ts_code" class="buy-item">
          <view class="buy-info">
            <text class="buy-name">{{ item.stock_name }}</text>
            <text class="buy-code">{{ item.ts_code }}</text>
          </view>
          <view class="buy-type">{{ item.buy_point_type }}</view>
        </view>

        <view v-if="activeTab === 'observe'" v-for="item in buyData.observe_buy_points" :key="item.ts_code" class="buy-item">
          <view class="buy-info">
            <text class="buy-name">{{ item.stock_name }}</text>
            <text class="buy-code">{{ item.ts_code }}</text>
          </view>
          <view class="buy-type">{{ item.buy_point_type }}</view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { decisionApi, getToday } from '../../api'

const today = ref(getToday())
const activeTab = ref('available')
const buyData = ref({ available_buy_points: [], observe_buy_points: [] })

const loadData = async () => {
  try {
    const res = await decisionApi.buyPoint(today.value, 30)
    buyData.value = res.data.data
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
.env-tip { font-size: 14px; color: #666; margin-bottom: 10px; }

.tabs { display: flex; margin-bottom: 15px; }
.tab { flex: 1; text-align: center; padding: 10px; border-bottom: 2px solid transparent; }
.tab.active { border-color: #409eff; color: #409eff; }

.buy-list { display: flex; flex-direction: column; }
.buy-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #f5f5f5; }
.buy-info { display: flex; flex-direction: column; }
.buy-name { font-weight: bold; }
.buy-code { font-size: 12px; color: #999; }
.buy-type { font-size: 14px; color: #409eff; }
</style>
