<template>
  <view class="page">
    <!-- 下拉刷新 -->
    <view class="header">
      <text class="title">轻舟交易系统</text>
      <text class="date">{{ today }}</text>
    </view>

    <!-- 执行摘要 -->
    <view class="card summary-card" v-if="summary">
      <view class="card-title">今日执行摘要</view>
      <view class="summary-content">
        <view class="summary-item">
          <text class="label">操作建议</text>
          <text :class="['value', getActionClass(summary.today_action)]">{{ summary.today_action }}</text>
        </view>
        <view class="summary-item">
          <text class="label">市场环境</text>
          <text class="value">{{ summary.market_env_tag }}</text>
        </view>
        <view class="summary-item">
          <text class="label">账户状态</text>
          <text class="value">{{ summary.account_action_tag }}</text>
        </view>
        <view class="summary-item">
          <text class="label">优先动作</text>
          <text class="value">{{ summary.priority_action }}</text>
        </view>
      </view>
      <view class="summary-extra">
        <view>▶ 重点关注：{{ summary.focus }}</view>
        <view>▶ 规避方向：{{ summary.avoid }}</view>
      </view>
    </view>

    <!-- 加载状态 -->
    <view v-if="loading" class="loading">
      <text>加载中...</text>
    </view>

    <!-- 快捷入口 -->
    <view class="quick-links">
      <view class="link-item" @click="goTo('/market')">
        <text class="link-icon">📊</text>
        <text class="link-text">市场环境</text>
      </view>
      <view class="link-item" @click="goTo('/sectors')">
        <text class="link-icon">🔥</text>
        <text class="link-text">板块扫描</text>
      </view>
      <view class="link-item" @click="goTo('/pools')">
        <text class="link-icon">🏊</text>
        <text class="link-text">三池分类</text>
      </view>
      <view class="link-item" @click="goTo('/buy')">
        <text class="link-icon">💰</text>
        <text class="link-text">买点分析</text>
      </view>
    </view>

    <!-- 主线板块 -->
    <view class="card" v-if="leaderSector">
      <view class="card-title">主线板块</view>
      <view class="leader-sector">
        <text class="sector-name">{{ leaderSector.sector.sector_name }}</text>
        <text :class="['sector-change', leaderSector.sector.sector_change_pct > 0 ? 'text-red' : 'text-green']">
          {{ leaderSector.sector.sector_change_pct?.toFixed(2) }}%
        </text>
        <text class="sector-tag">{{ leaderSector.sector.sector_mainline_tag }}</text>
      </view>
    </view>

    <!-- 市场概览 -->
    <view class="card" v-if="marketEnv">
      <view class="card-title">市场环境</view>
      <view class="env-tag">
        <text :class="['tag', getEnvClass(marketEnv.market_env_tag)]">{{ marketEnv.market_env_tag }}</text>
      </view>
      <view class="env-comment">{{ marketEnv.market_comment }}</view>
    </view>

    <!-- 账户概况 -->
    <view class="card" v-if="accountProfile">
      <view class="card-title">账户概况</view>
      <view class="account-info">
        <view class="info-row">
          <text class="info-label">总资产</text>
          <text class="info-value">{{ formatMoney(accountProfile.total_asset) }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">可用资金</text>
          <text class="info-value">{{ formatMoney(accountProfile.available_cash) }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">仓位</text>
          <text class="info-value">{{ (accountProfile.total_position_ratio * 100).toFixed(1) }}%</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { decisionApi, marketApi, accountApi, sectorApi, getToday } from '../api'

const today = ref(getToday())
const loading = ref(false)
const summary = ref(null)
const marketEnv = ref(null)
const accountProfile = ref(null)
const leaderSector = ref(null)

const getActionClass = (action) => {
  if (action?.includes('少') || action?.includes('防守')) return 'text-red'
  if (action?.includes('适度') || action?.includes('积极')) return 'text-green'
  return 'text-yellow'
}

const getEnvClass = (tag) => {
  if (tag === '进攻') return 'tag-success'
  if (tag === '中性') return 'tag-warning'
  return 'tag-danger'
}

const formatMoney = (value) => {
  if (!value) return '-'
  return (value / 10000).toFixed(2) + '万'
}

const loadData = async () => {
  loading.value = true
  try {
    const [summaryRes, marketRes, accountRes, leaderRes] = await Promise.all([
      decisionApi.summary(today.value),
      marketApi.getEnv(today.value),
      accountApi.profile(),
      sectorApi.leader(today.value)
    ])
    summary.value = summaryRes.data
    marketEnv.value = marketRes.data.data
    accountProfile.value = accountRes.data
    leaderSector.value = leaderRes.data.data
  } catch (e) {
    console.error('加载失败', e)
  } finally {
    loading.value = false
  }
}

// 下拉刷新
const onPullDownRefresh = () => {
  loadData().then(() => {
    uni.stopPullDownRefresh()
  })
}

// 启用下拉刷新
onMounted(() => {
  loadData()
  // #ifdef MP-WEIXIN
  uni.showNavigationBarLoading()
  onPullDownRefresh().finally(() => {
    uni.hideNavigationBarLoading()
  })
  // #endif
})
</script>

<style scoped>
.page { padding: 10px; }

.header { padding: 15px 0; text-align: center; }
.title { font-size: 20px; font-weight: bold; display: block; }
.date { font-size: 14px; color: #999; }

.card { background: #fff; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
.card-title { font-size: 16px; font-weight: bold; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #eee; }

.summary-content { display: flex; flex-wrap: wrap; }
.summary-item { width: 50%; padding: 8px 0; }
.summary-item .label { font-size: 12px; color: #999; display: block; }
.summary-item .value { font-size: 16px; font-weight: bold; }
.summary-extra { margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; font-size: 14px; color: #666; }

.text-green { color: #67c23a; }
.text-yellow { color: #e6a23c; }
.text-red { color: #f56c6c; }

.quick-links { display: flex; flex-wrap: wrap; margin-bottom: 10px; }
.link-item { width: 25%; display: flex; flex-direction: column; align-items: center; padding: 15px 0; }
.link-icon { font-size: 28px; margin-bottom: 5px; }
.link-text { font-size: 12px; color: #666; }

.leader-sector { text-align: center; }
.sector-name { font-size: 20px; font-weight: bold; margin-right: 10px; }
.sector-change { font-size: 20px; font-weight: bold; margin-right: 10px; }
.sector-tag { font-size: 12px; padding: 2px 8px; background: #e1f3d8; color: #67c23a; border-radius: 4px; }

.env-tag { text-align: center; margin: 10px 0; }
.tag { padding: 5px 20px; border-radius: 15px; font-size: 16px; }
.tag-success { background: #e1f3d8; color: #67c23a; }
.tag-warning { background: #fdf6ec; color: #e6a23c; }
.tag-danger { background: #fef0f0; color: #f56c6c; }
.env-comment { text-align: center; color: #666; font-size: 14px; }

.account-info { display: flex; flex-direction: column; }
.info-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f5f5f5; }
.info-label { color: #999; }
.info-value { font-weight: bold; }

.loading { text-align: center; padding: 30px; color: #999; }
</style>
