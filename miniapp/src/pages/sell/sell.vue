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
        <!-- 卖出 -->
        <view v-if="activeTab === 'sell'" v-for="(item, index) in sellData.sell_positions" :key="item.ts_code + index" class="sell-item" @click="toggleDetail(item)">
          <view class="sell-header">
            <view class="sell-info">
              <text class="sell-name">{{ item.stock_name }}</text>
              <text class="sell-code">{{ item.ts_code }}</text>
            </view>
            <view class="sell-right">
              <text class="sell-type">{{ item.sell_point_type }}</text>
            </view>
          </view>
          <view v-if="expandedItem === item.ts_code" class="sell-detail">
            <view class="detail-row">
              <text class="detail-label">触发条件</text>
              <text class="detail-content">{{ item.sell_trigger_cond }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">卖出原因</text>
              <text class="detail-content error">{{ item.sell_reason }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">优先级</text>
              <text :class="['priority-tag', 'priority-' + item.sell_priority]">{{ item.sell_priority }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">简评</text>
              <text class="detail-content">{{ item.sell_comment }}</text>
            </view>
          </view>
        </view>

        <!-- 减仓 -->
        <view v-if="activeTab === 'reduce'" v-for="(item, index) in sellData.reduce_positions" :key="item.ts_code + index" class="sell-item" @click="toggleDetail(item)">
          <view class="sell-header">
            <view class="sell-info">
              <text class="sell-name">{{ item.stock_name }}</text>
              <text class="sell-code">{{ item.ts_code }}</text>
            </view>
            <view class="sell-right">
              <text class="sell-type type-reduce">{{ item.sell_point_type }}</text>
            </view>
          </view>
          <view v-if="expandedItem === item.ts_code" class="sell-detail">
            <view class="detail-row">
              <text class="detail-label">触发条件</text>
              <text class="detail-content">{{ item.sell_trigger_cond }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">减仓原因</text>
              <text class="detail-content">{{ item.sell_reason }}</text>
            </view>
          </view>
        </view>

        <!-- 持有 -->
        <view v-if="activeTab === 'hold'" v-for="(item, index) in sellData.hold_positions" :key="item.ts_code + index" class="sell-item" @click="toggleDetail(item)">
          <view class="sell-header">
            <view class="sell-info">
              <text class="sell-name">{{ item.stock_name }}</text>
              <text class="sell-code">{{ item.ts_code }}</text>
            </view>
            <view class="sell-right">
              <text class="sell-type type-hold">{{ item.sell_point_type }}</text>
            </view>
          </view>
          <view v-if="expandedItem === item.ts_code" class="sell-detail">
            <view class="detail-row">
              <text class="detail-label">持有说明</text>
              <text class="detail-content">{{ item.sell_comment }}</text>
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
import { decisionApi, getToday } from '../../api'

const today = ref(getToday())
const activeTab = ref('sell')
const loading = ref(false)
const sellData = ref({ sell_positions: [], reduce_positions: [], hold_positions: [] })
const expandedItem = ref(null)

const toggleDetail = (item) => {
  expandedItem.value = expandedItem.value === item.ts_code ? null : item.ts_code
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await decisionApi.sellPoint(today.value)
    sellData.value = res.data.data
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

.sell-list { display: flex; flex-direction: column; }
.sell-item { padding: 12px 0; border-bottom: 1px solid #f5f5f5; }
.sell-header { display: flex; justify-content: space-between; align-items: center; }
.sell-info { display: flex; flex-direction: column; }
.sell-name { font-weight: bold; }
.sell-code { font-size: 12px; color: #999; }
.sell-right { display: flex; align-items: center; }
.sell-type { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: #fef0f0; color: #f56c6c; }
.type-reduce { background: #fdf6ec; color: #e6a23c; }
.type-hold { background: #f5f5f5; color: #999; }

.sell-detail { margin-top: 10px; padding: 10px; background: #f9f9f9; border-radius: 8px; }
.detail-row { display: flex; justify-content: space-between; align-items: flex-start; padding: 8px 0; border-bottom: 1px solid #eee; }
.detail-row:last-child { border-bottom: none; }
.detail-label { font-size: 12px; color: #999; width: 80px; flex-shrink: 0; }
.detail-content { font-size: 14px; color: #333; text-align: right; flex: 1; }
.detail-content.error { color: #f56c6c; }

.priority-tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; }
.priority-高 { background: #fef0f0; color: #f56c6c; }
.priority-中 { background: #fdf6ec; color: #e6a23c; }
.priority-低 { background: #f5f5f5; color: #999; }

.loading { text-align: center; padding: 30px; color: #999; }
</style>
