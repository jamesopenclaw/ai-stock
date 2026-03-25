<template>
  <div class="market-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>市场环境分析</span>
            <span v-if="displayDate" class="header-date">{{ displayDate }}</span>
            <span
              v-if="resolvedDate && resolvedDate !== displayDate"
              class="header-date"
            >
              实际数据日 {{ resolvedDate }}
            </span>
          </div>
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </template>
      <el-skeleton v-if="loading" :rows="14" animated />
      <template v-else>
        <div v-if="dataNotice" class="data-notice">
          {{ dataNotice }}
        </div>
        <div v-if="marketEnv" class="env-analysis">
          <div class="env-tag-wrap">
            <el-tag
              class="market-env-tag"
              size="large"
              effect="dark"
              :type="getEnvType(marketEnv.market_env_tag)"
            >
              {{ marketEnv.market_env_tag }}
            </el-tag>
          </div>
          <p class="market-env-comment">{{ marketEnv.market_comment }}</p>
          <el-row :gutter="20" class="env-scores-row">
            <el-col :span="8">
              <div class="stat-item">
                <div class="label">指数评分</div>
                <div class="value score-value" :class="scoreClass(marketEnv.index_score)">{{ marketEnv.index_score?.toFixed(1) }}</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="stat-item">
                <div class="label">情绪评分</div>
                <div class="value score-value" :class="scoreClass(marketEnv.sentiment_score)">{{ marketEnv.sentiment_score?.toFixed(1) }}</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="stat-item">
                <div class="label">综合评分</div>
                <div class="value score-value" :class="scoreClass(marketEnv.overall_score)">{{ marketEnv.overall_score?.toFixed(1) }}</div>
              </div>
            </el-col>
          </el-row>
        </div>
        <el-empty v-else description="暂无市场环境数据" />
      </template>
    </el-card>

    <el-card v-if="!loading" class="market-section-card">
      <template #header>
        <span>主要指数行情</span>
      </template>
      <div v-if="indexNotice" class="data-notice section-notice-index">
        {{ indexNotice }}
      </div>
      <el-empty v-if="!indexData?.length" description="暂无指数行情" />
      <el-table v-else :data="indexData" style="width: 100%">
        <el-table-column prop="name" label="指数" />
        <el-table-column prop="close" label="最新价" />
        <el-table-column prop="change_pct" label="涨跌幅">
          <template #default="{ row }">
            <span :class="row.change_pct > 0 ? 'text-red' : 'text-green'">
              {{ row.change_pct?.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="volume" label="成交量" />
        <el-table-column prop="amount" label="成交额" />
        <el-table-column label="来源 / 时间" width="170">
          <template #default="{ row }">
            <span :class="['index-source', { 'index-source-live': isRealtimeSource(row.data_source) }]">
              {{ quoteMetaLine(row.data_source, row.quote_time, row.trade_date) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="!loading" class="market-section-card">
      <template #header>
        <span>市场情绪指标</span>
      </template>
      <div v-if="statsNotice" class="data-notice section-notice-index">
        {{ statsNotice }}
      </div>
      <el-empty v-if="!marketStats" description="暂无市场情绪数据" />
      <el-row v-else :gutter="20" class="equal-height sentiment-row">
        <el-col :xs="12" :sm="12" :md="6">
          <div class="stat-card">
            <div class="label">涨停数</div>
            <div class="value value-emphasis text-red">{{ marketStats.limit_up_count }}</div>
          </div>
        </el-col>
        <el-col :xs="12" :sm="12" :md="6">
          <div class="stat-card">
            <div class="label">跌停数</div>
            <div class="value value-emphasis text-green">{{ marketStats.limit_down_count }}</div>
          </div>
        </el-col>
        <el-col :xs="12" :sm="12" :md="6">
          <div class="stat-card">
            <div class="label">炸板率</div>
            <div class="value stat-metric-value" :class="brokenBoardClass(marketStats.broken_board_rate)">{{ marketStats.broken_board_rate?.toFixed(1) }}%</div>
          </div>
        </el-col>
        <el-col :xs="12" :sm="12" :md="6">
          <div class="stat-card">
            <div class="label">成交额</div>
            <div class="value stat-metric-value">{{ (marketStats.market_turnover / 10000)?.toFixed(1) }}万亿</div>
          </div>
        </el-col>
      </el-row>
      <div v-if="marketStats?.up_down_ratio" class="market-breadth">
        <span>上涨 {{ marketStats.up_down_ratio.up || 0 }}</span>
        <span>下跌 {{ marketStats.up_down_ratio.down || 0 }}</span>
        <span>平盘 {{ marketStats.up_down_ratio.flat || 0 }}</span>
        <span>共 {{ marketStats.up_down_ratio.total || 0 }}</span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { marketApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const marketEnv = ref(null)
const indexData = ref([])
const marketStats = ref(null)
const displayDate = ref('')
const resolvedDate = ref('')
const indexNotice = ref('')
const statsNotice = ref('')

const getLocalDate = () => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const getEnvType = (tag) => {
  if (tag === '进攻') return 'success'
  if (tag === '中性') return 'warning'
  return 'danger'
}

/** 0–100 评分：越高越偏进攻 */
const scoreClass = (n) => {
  if (n == null || Number.isNaN(Number(n))) return ''
  const v = Number(n)
  if (v >= 60) return 'text-red'
  if (v >= 40) return 'text-yellow'
  return 'text-green'
}

/** 炸板率越高情绪越弱；高用绿、低用红（A 股涨跌色语义） */
const brokenBoardClass = (r) => {
  if (r == null || Number.isNaN(Number(r))) return ''
  const v = Number(r)
  if (v >= 50) return 'text-green'
  if (v >= 30) return 'text-yellow'
  return 'text-red'
}

const isRealtimeSource = (source) => String(source || '').startsWith('realtime_')

const quoteSourceLabel = (source) => {
  if (!source) return '日线回退'
  if (String(source).startsWith('realtime_')) return '盘中实时'
  if (source === 'mock') return '模拟数据'
  return '日线回退'
}

const quoteMetaLine = (source, quoteTime, fallbackTradeDate) => {
  const label = quoteSourceLabel(source)
  if (quoteTime) return `${label} ${quoteTime.slice(11, 19)}`
  const raw = String(fallbackTradeDate || '')
  if (raw.length === 8) {
    return `${label} ${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`
  }
  return label
}

const isMixedMode = (indexRows, stats) => {
  const indexRealtime = (indexRows || []).some((row) => isRealtimeSource(row?.data_source))
  const statsRealtime = isRealtimeSource(stats?.turnover_data_source) || isRealtimeSource(stats?.up_down_data_source)
  const statsFallback = !isRealtimeSource(stats?.limit_stats_data_source) || !isRealtimeSource(stats?.turnover_data_source) || !isRealtimeSource(stats?.up_down_data_source)
  return indexRealtime && (statsFallback || !statsRealtime)
}

const dataNotice = ref('')

const loadData = async () => {
  loading.value = true
  try {
    const tradeDate = getLocalDate()
    displayDate.value = tradeDate
    const [envRes, indexRes, statsRes] = await Promise.all([
      marketApi.getEnv(tradeDate),
      marketApi.getIndex(tradeDate),
      marketApi.getStats(tradeDate)
    ])
    marketEnv.value = envRes.data.data
    indexData.value = indexRes.data.data.indexes || []
    marketStats.value = statsRes.data.data
    resolvedDate.value = envRes.data.data?.resolved_trade_date || indexRes.data.data?.resolved_trade_date || statsRes.data.data?.resolved_trade_date || ''
    const firstIndex = indexData.value?.[0]
    indexNotice.value = firstIndex
      ? `指数行情当前使用${quoteMetaLine(firstIndex.data_source, firstIndex.quote_time, firstIndex.trade_date)}；情绪统计仍按 ${statsRes.data.data?.resolved_trade_date || resolvedDate.value || tradeDate} 口径计算。`
      : ''
    const turnoverText = quoteMetaLine(
      statsRes.data.data?.turnover_data_source,
      statsRes.data.data?.turnover_quote_time,
      statsRes.data.data?.resolved_trade_date?.replaceAll('-', '')
    )
    const breadthText = quoteMetaLine(
      statsRes.data.data?.up_down_data_source,
      statsRes.data.data?.up_down_quote_time,
      statsRes.data.data?.resolved_trade_date?.replaceAll('-', '')
    )
    const limitText = quoteMetaLine(
      statsRes.data.data?.limit_stats_data_source,
      statsRes.data.data?.limit_stats_quote_time,
      statsRes.data.data?.resolved_trade_date?.replaceAll('-', '')
    )
    statsNotice.value = `涨跌家数使用${breadthText}，成交额使用${turnoverText}；涨跌停和炸板率使用${limitText}。`
    const notices = []
    if (isMixedMode(indexData.value, statsRes.data.data)) {
      notices.push(`当前环境判断使用混合口径：指数已切到盘中实时，但情绪指标仍有部分沿用 ${statsRes.data.data?.resolved_trade_date || resolvedDate.value || tradeDate}。`)
    } else if (resolvedDate.value && resolvedDate.value !== tradeDate) {
      notices.push(`当前请求日没有完整行情，已回退到最近有数据的交易日 ${resolvedDate.value}。`)
    }
    if (indexRes.data.data?.used_mock) {
      notices.push('指数行情当前使用了模拟数据。')
    }
    if (statsRes.data.data?.used_mock) {
      notices.push('市场情绪统计当前使用了模拟数据。')
    }
    dataNotice.value = notices.join(' ')
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  displayDate.value = getLocalDate()
  loadData()
})
</script>

<style scoped>
.market-view {
  padding: 0;
}

.market-section-card {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.card-header-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.header-date {
  font-size: 13px;
  color: var(--color-text-sec);
  letter-spacing: 0.02em;
  font-weight: 400;
}

.data-notice {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 12px;
  line-height: 1.6;
  color: #f3c24d;
  background: rgba(243, 194, 77, 0.08);
  border: 1px solid rgba(243, 194, 77, 0.18);
}

.section-notice-index {
  margin-bottom: 12px;
}

.index-source {
  font-size: 12px;
  color: var(--color-text-sec);
}

.index-source-live {
  color: #54d2a4;
}

/* 首屏：全宽标签 + 文案 + 三评分 */
.env-analysis {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.env-tag-wrap {
  text-align: center;
  padding: 8px 0 16px;
}

.env-analysis :deep(.market-env-tag.el-tag) {
  font-size: clamp(1.35rem, 3vw, 2rem);
  font-weight: 700;
  line-height: 1.2;
  height: auto;
  padding: 14px 28px;
  border-radius: 10px;
  letter-spacing: 0.06em;
}

.market-env-comment {
  font-size: 16px;
  line-height: 1.55;
  color: var(--color-text-pri);
  margin: 0 auto 20px;
  max-width: 56rem;
  text-align: left;
}

.env-scores-row {
  margin-top: 4px;
}

.stat-item {
  text-align: center;
  padding: 8px 4px;
}

.stat-item .label {
  color: var(--color-text-sec);
  margin-bottom: 10px;
  font-size: 13px;
}

.stat-item .value.score-value {
  font-size: clamp(1.75rem, 4vw, 2.5rem);
  font-weight: 700;
  line-height: 1.15;
}
.stat-item .value.score-value:not(.text-red):not(.text-green):not(.text-yellow) {
  color: var(--color-text-pri);
}

/* 情绪指标：等高四宫格 */
.equal-height.sentiment-row {
  row-gap: 16px;
}

.equal-height {
  align-items: stretch;
}

.equal-height .el-col {
  display: flex;
  flex-direction: column;
}

.stat-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 120px;
  text-align: center;
  padding: 20px 16px;
  background: var(--color-hover);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.stat-card .label {
  color: var(--color-text-sec);
  margin-bottom: 10px;
  font-size: 13px;
}

.stat-card .value {
  font-weight: 700;
  line-height: 1.1;
}
.stat-card .value:not(.text-red):not(.text-green):not(.text-yellow) {
  color: var(--color-text-pri);
}

.stat-metric-value {
  font-size: clamp(1.75rem, 3.5vw, 2.75rem);
  letter-spacing: -0.02em;
}

.stat-card .value-emphasis {
  font-size: clamp(2rem, 3.8vw, 3rem);
  letter-spacing: -0.02em;
}

.market-breadth {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 16px;
  color: var(--color-text-sec);
  font-size: 13px;
}
</style>
