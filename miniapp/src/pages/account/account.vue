<template>
  <view class="page">
    <view class="card">
      <view class="card-title">账户概况</view>
      <view v-if="profile" class="account-info">
        <view class="info-row">
          <text class="info-label">总资产</text>
          <text class="info-value">{{ formatMoney(profile.total_asset) }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">可用资金</text>
          <text class="info-value">{{ formatMoney(profile.available_cash) }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">持仓市值</text>
          <text class="info-value">{{ formatMoney(profile.market_value) }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">仓位</text>
          <text class="info-value">{{ (profile.total_position_ratio * 100).toFixed(1) }}%</text>
        </view>
        <view class="info-row">
          <text class="info-label">持仓数量</text>
          <text class="info-value">{{ profile.holding_count }}只</text>
        </view>
      </view>
    </view>

    <view class="card">
      <view class="card-title">账户状态</view>
      <view v-if="status" class="status-content">
        <text :class="['status-tag', status.can_trade ? 'tag-success' : 'tag-danger']">
          {{ status.can_trade ? '可以交易' : '暂停交易' }}
        </text>
        <view class="status-info">
          <view class="status-row">
            <text class="status-label">操作建议</text>
            <text class="status-value">{{ status.action }}</text>
          </view>
          <view class="status-row">
            <text class="status-label">优先动作</text>
            <text class="status-value">{{ status.priority }}</text>
          </view>
        </view>
      </view>
    </view>

    <view class="card">
      <view class="card-title">持仓明细</view>
      <view class="position-list">
        <view v-for="item in positions" :key="item.ts_code" class="position-item">
          <view class="position-info">
            <text class="position-name">{{ item.stock_name }}</text>
            <text class="position-code">{{ item.ts_code }}</text>
          </view>
          <view class="position-extra">
            <view>数量: {{ item.holding_qty }}</view>
            <view>成本: {{ item.cost_price?.toFixed(2) }}</view>
            <view :class="item.pnl_pct > 0 ? 'text-red' : 'text-green'">
              {{ item.pnl_pct?.toFixed(2) }}%
            </view>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { accountApi } from '../../api'

const profile = ref(null)
const status = ref(null)
const positions = ref([])

const formatMoney = (value) => {
  if (!value) return '-'
  return (value / 10000).toFixed(2) + '万'
}

const loadData = async () => {
  try {
    const [profileRes, statusRes, posRes] = await Promise.all([
      accountApi.profile(),
      accountApi.status(),
      accountApi.positions()
    ])
    profile.value = profileRes.data
    status.value = statusRes.data.data
    positions.value = posRes.data.data.positions || []
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

.account-info { display: flex; flex-direction: column; }
.info-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f5f5f5; }
.info-label { color: #999; }
.info-value { font-weight: bold; }

.status-content { text-align: center; }
.status-tag { display: inline-block; padding: 5px 20px; border-radius: 15px; font-size: 16px; margin-bottom: 15px; }
.tag-success { background: #e1f3d8; color: #67c23a; }
.tag-danger { background: #fef0f0; color: #f56c6c; }

.status-info { display: flex; flex-direction: column; }
.status-row { display: flex; justify-content: space-between; padding: 8px 0; }
.status-label { color: #999; }
.status-value { font-weight: bold; }

.position-list { display: flex; flex-direction: column; }
.position-item { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #f5f5f5; }
.position-info { display: flex; flex-direction: column; }
.position-name { font-weight: bold; }
.position-code { font-size: 12px; color: #999; }
.position-extra { text-align: right; font-size: 14px; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
</style>
