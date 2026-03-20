<template>
  <view class="page">
    <view class="card">
      <view class="card-title">市场环境分析</view>
      <view v-if="marketEnv" class="env-content">
        <view class="env-tag">
          <text :class="['tag', getEnvClass(marketEnv.market_env_tag)]">{{ marketEnv.market_env_tag }}</text>
        </view>
        <view class="env-comment">{{ marketEnv.market_comment }}</view>
        <view class="score-row">
          <view class="score-item">
            <text class="score-label">指数评分</text>
            <text class="score-value">{{ marketEnv.index_score?.toFixed(1) }}</text>
          </view>
          <view class="score-item">
            <text class="score-label">情绪评分</text>
            <text class="score-value">{{ marketEnv.sentiment_score?.toFixed(1) }}</text>
          </view>
          <view class="score-item">
            <text class="score-label">综合评分</text>
            <text class="score-value">{{ marketEnv.overall_score?.toFixed(1) }}</text>
          </view>
        </view>
      </view>
    </view>

    <view class="card">
      <view class="card-title">主要指数</view>
      <view v-if="indexData.length" class="index-list">
        <view v-for="item in indexData" :key="item.ts_code" class="index-item">
          <text class="index-name">{{ item.name }}</text>
          <text class="index-close">{{ item.close?.toFixed(2) }}</text>
          <text :class="['index-change', item.change_pct > 0 ? 'text-red' : 'text-green']">
            {{ item.change_pct?.toFixed(2) }}%
          </text>
        </view>
      </view>
    </view>

    <view class="card">
      <view class="card-title">市场情绪</view>
      <view v-if="marketStats" class="stats-row">
        <view class="stat-item">
          <text class="stat-value text-red">{{ marketStats.limit_up_count }}</text>
          <text class="stat-label">涨停</text>
        </view>
        <view class="stat-item">
          <text class="stat-value text-green">{{ marketStats.limit_down_count }}</text>
          <text class="stat-label">跌停</text>
        </view>
        <view class="stat-item">
          <text class="stat-value">{{ marketStats.broken_board_rate?.toFixed(1) }}%</text>
          <text class="stat-label">炸板率</text>
        </view>
        <view class="stat-item">
          <text class="stat-value">{{ (marketStats.market_turnover / 10000)?.toFixed(1) }}万亿</text>
          <text class="stat-label">成交额</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { marketApi, getToday } from '../../api'

const today = ref(getToday())
const marketEnv = ref(null)
const indexData = ref([])
const marketStats = ref(null)

const getEnvClass = (tag) => {
  if (tag === '进攻') return 'tag-success'
  if (tag === '中性') return 'tag-warning'
  return 'tag-danger'
}

const loadData = async () => {
  try {
    const [envRes, indexRes, statsRes] = await Promise.all([
      marketApi.getEnv(today.value),
      marketApi.getIndex(today.value),
      marketApi.getStats(today.value)
    ])
    marketEnv.value = envRes.data.data
    indexData.value = indexRes.data.data.indexes || []
    marketStats.value = statsRes.data.data
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

.env-content { text-align: center; }
.env-tag { margin-bottom: 10px; }
.tag { padding: 5px 20px; border-radius: 15px; font-size: 16px; }
.tag-success { background: #e1f3d8; color: #67c23a; }
.tag-warning { background: #fdf6ec; color: #e6a23c; }
.tag-danger { background: #fef0f0; color: #f56c6c; }
.env-comment { color: #666; margin-bottom: 15px; }

.score-row { display: flex; justify-content: space-around; }
.score-item { text-align: center; }
.score-label { font-size: 12px; color: #999; display: block; }
.score-value { font-size: 20px; font-weight: bold; }

.index-list { display: flex; flex-direction: column; }
.index-item { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f5f5f5; }
.index-name { font-weight: bold; }
.index-close { color: #666; }
.index-change { font-weight: bold; }

.stats-row { display: flex; justify-content: space-around; }
.stat-item { text-align: center; }
.stat-value { font-size: 18px; font-weight: bold; display: block; }
.stat-label { font-size: 12px; color: #999; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
</style>
