<template>
  <view class="page">
    <view class="card">
      <view class="card-title">卖点分析</view>
      
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
        <view v-if="activeTab === 'sell'" v-for="item in sellData.sell_positions" :key="item.ts_code" class="sell-item">
          <view class="sell-info">
            <text class="sell-name">{{ item.stock_name }}</text>
            <text class="sell-code">{{ item.ts_code }}</text>
          </view>
          <view class="sell-reason">{{ item.sell_reason }}</view>
        </view>

        <view v-if="activeTab === 'reduce'" v-for="item in sellData.reduce_positions" :key="item.ts_code" class="sell-item">
          <view class="sell-info">
            <text class="sell-name">{{ item.stock_name }}</text>
            <text class="sell-code">{{ item.ts_code }}</text>
          </view>
          <view class="sell-reason">{{ item.sell_reason }}</view>
        </view>

        <view v-if="activeTab === 'hold'" v-for="item in sellData.hold_positions" :key="item.ts_code" class="sell-item">
          <view class="sell-info">
            <text class="sell-name">{{ item.stock_name }}</text>
            <text class="sell-code">{{ item.ts_code }}</text>
          </view>
          <view class="sell-reason">{{ item.sell_comment }}</view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { decisionApi, getToday } from '../../api'

const today = ref(getToday())
const activeTab = ref('sell')
const sellData = ref({ sell_positions: [], reduce_positions: [], hold_positions: [] })

const loadData = async () => {
  try {
    const res = await decisionApi.sellPoint(today.value)
    sellData.value = res.data.data
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

.sell-list { display: flex; flex-direction: column; }
.sell-item { padding: 12px 0; border-bottom: 1px solid #f5f5f5; }
.sell-info { display: flex; align-items: center; margin-bottom: 5px; }
.sell-name { font-weight: bold; margin-right: 10px; }
.sell-code { font-size: 12px; color: #999; }
.sell-reason { font-size: 14px; color: #f56c6c; }
</style>
