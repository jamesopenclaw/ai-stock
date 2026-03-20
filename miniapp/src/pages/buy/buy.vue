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
        <!-- 可买 -->
        <view v-if="activeTab === 'available'" v-for="(item, index) in buyData.available_buy_points" :key="item.ts_code + index" class="buy-item" @click="toggleDetail(item)">
          <view class="buy-header">
            <view class="buy-info">
              <text class="buy-name">{{ item.stock_name }}</text>
              <text class="buy-code">{{ item.ts_code }}</text>
            </view>
            <view class="buy-right">
              <text :class="['buy-type', 'type-' + item.buy_point_type]">{{ item.buy_point_type }}</text>
              <text :class="['risk-tag', 'risk-' + item.buy_risk_level]">{{ item.buy_risk_level }}风险</text>
            </view>
          </view>
          <!-- 详情展开 -->
          <view v-if="expandedItem === item.ts_code" class="buy-detail">
            <view class="detail-section">
              <text class="detail-title">触发条件</text>
              <text class="detail-content">{{ item.buy_trigger_cond }}</text>
            </view>
            <view class="detail-section">
              <text class="detail-title">确认条件</text>
              <text class="detail-content">{{ item.buy_confirm_cond }}</text>
            </view>
            <view class="detail-section">
              <text class="detail-title">失效条件</text>
              <text class="detail-content error">{{ item.buy_invalid_cond }}</text>
            </view>
            <view class="detail-section">
              <text class="detail-title">账户适合度</text>
              <text class="detail-content">{{ item.buy_account_fit }}</text>
            </view>
            <view class="detail-section">
              <text class="detail-title">简评</text>
              <text class="detail-content">{{ item.buy_comment }}</text>
            </view>
          </view>
        </view>

        <!-- 观察 -->
        <view v-if="activeTab === 'observe'" v-for="(item, index) in buyData.observe_buy_points" :key="item.ts_code + index" class="buy-item" @click="toggleDetail(item)">
          <view class="buy-header">
            <view class="buy-info">
              <text class="buy-name">{{ item.stock_name }}</text>
              <text class="buy-code">{{ item.ts_code }}</text>
            </view>
            <view class="buy-right">
              <text class="buy-type type-observe">{{ item.buy_point_type }}</text>
            </view>
          </view>
          <view v-if="expandedItem === item.ts_code" class="buy-detail">
            <view class="detail-section">
              <text class="detail-title">触发条件</text>
              <text class="detail-content">{{ item.buy_trigger_cond }}</text>
            </view>
            <view class="detail-section">
              <text class="detail-title">风险提示</text>
              <text class="detail-content">{{ item.buy_comment }}</text>
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
const activeTab = ref('available')
const loading = ref(false)
const buyData = ref({ available_buy_points: [], observe_buy_points: [] })
const expandedItem = ref(null)

const toggleDetail = (item) => {
  expandedItem.value = expandedItem.value === item.ts_code ? null : item.ts_code
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await decisionApi.buyPoint(today.value, 30)
    buyData.value = res.data.data
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
.env-tip { font-size: 14px; color: #666; margin-bottom: 10px; }

.tabs { display: flex; margin-bottom: 15px; }
.tab { flex: 1; text-align: center; padding: 10px; border-bottom: 2px solid transparent; }
.tab.active { border-color: #409eff; color: #409eff; }

.buy-list { display: flex; flex-direction: column; }
.buy-item { padding: 12px 0; border-bottom: 1px solid #f5f5f5; }
.buy-header { display: flex; justify-content: space-between; align-items: center; }
.buy-info { display: flex; flex-direction: column; }
.buy-name { font-weight: bold; }
.buy-code { font-size: 12px; color: #999; }
.buy-right { display: flex; align-items: center; gap: 8px; }
.buy-type { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
.type-突破 { background: #e1f3d8; color: #67c23a; }
.type-回踩承接 { background: #fdf6ec; color: #e6a23c; }
.type-修复转强 { background: #ecf5ff; color: #409eff; }
.type-observe { background: #f5f5f5; color: #999; }

.risk-tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; }
.risk-低 { background: #e1f3d8; color: #67c23a; }
.risk-中 { background: #fdf6ec; color: #e6a23c; }
.risk-高 { background: #fef0f0; color: #f56c6c; }

.buy-detail { margin-top: 10px; padding: 10px; background: #f9f9f9; border-radius: 8px; }
.detail-section { margin-bottom: 10px; }
.detail-section:last-child { margin-bottom: 0; }
.detail-title { font-size: 12px; color: #999; margin-bottom: 4px; }
.detail-content { font-size: 14px; color: #333; }
.detail-content.error { color: #f56c6c; }

.loading { text-align: center; padding: 30px; color: #999; }
</style>
