<template>
  <div class="pattern-analysis-view">
    <el-card class="pattern-shell">
      <template #header>
        <div class="pattern-header">
          <div>
            <div class="pattern-kicker">股票形态分析</div>
            <div class="pattern-title-row">
              <h2>{{ headerTitle }}</h2>
              <el-tag :type="confidenceTagType" effect="dark">{{ analysis.confidence || '低' }}置信</el-tag>
            </div>
            <div class="pattern-subtitle">{{ analysis.pattern_summary || '围绕结构、关键位和候选形态做收敛判断。' }}</div>
          </div>
          <div class="pattern-actions">
            <el-date-picker
              v-model="activeTradeDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择交易日"
              class="trade-date-picker"
            />
            <el-button :loading="loading" @click="loadData()">刷新</el-button>
            <el-button :loading="llmRefreshing" type="primary" plain @click="refreshLlm()">刷新解读</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="llmStatusText"
        :title="llmStatusText"
        :type="llmStatusType"
        show-icon
        :closable="false"
        class="pattern-alert"
      />

      <el-empty v-if="!tsCode" description="缺少股票代码，请从个股入口进入形态分析页。" />
      <el-skeleton v-else-if="loading && !data" :rows="10" animated />
      <el-empty v-else-if="!data" description="暂无形态分析结果" />
      <template v-else>
        <section class="hero-grid">
          <article class="hero-card hero-card-primary">
            <div class="hero-chip-row">
              <span class="hero-chip">{{ analysis.primary_pattern || '未识别明确形态' }}</span>
              <span class="hero-chip hero-chip-muted">{{ analysis.pattern_phase || '待确认' }}</span>
              <span class="hero-chip hero-chip-muted">{{ data.resolved_trade_date || activeTradeDate }}</span>
            </div>
            <div class="hero-headline">{{ analysis.primary_pattern || '未识别明确形态' }}</div>
            <div class="hero-copy">{{ analysis.pattern_rationale || analysis.pattern_summary || '-' }}</div>
            <div class="hero-meta-grid">
              <div class="hero-metric">
                <span>突破/颈线</span>
                <strong>{{ formatPrice(analysis.breakout_level) }}</strong>
              </div>
              <div class="hero-metric">
                <span>防守位</span>
                <strong>{{ formatPrice(analysis.defense_level) }}</strong>
              </div>
              <div class="hero-metric">
                <span>压力区</span>
                <strong>{{ joinPrices(analysis.pressure_levels) }}</strong>
              </div>
              <div class="hero-metric">
                <span>支撑区</span>
                <strong>{{ joinPrices(analysis.support_levels) }}</strong>
              </div>
            </div>
          </article>

          <article class="hero-card hero-card-side">
            <div class="side-section">
              <span class="side-kicker">执行提示</span>
              <strong>{{ analysis.execution_hint || '-' }}</strong>
            </div>
            <div class="side-section">
              <span class="side-kicker">风险提示</span>
              <strong>{{ analysis.risk_hint || '-' }}</strong>
            </div>
            <div class="side-section">
              <span class="side-kicker">失效条件</span>
              <strong>{{ analysis.invalid_if || '-' }}</strong>
            </div>
          </article>
        </section>

        <section class="chart-section">
          <div class="section-head">
            <div>
              <span class="section-kicker">结构主图</span>
              <h3>K 线与关键位</h3>
            </div>
            <div class="section-meta">
              <span>{{ basicInfo.stock_name }} / {{ basicInfo.ts_code }}</span>
              <span>{{ basicInfo.sector_name || '未分类' }}</span>
            </div>
          </div>
          <div ref="chartRef" class="chart-canvas" />
        </section>

        <section class="content-grid">
          <article class="content-card">
            <div class="section-kicker">候选形态</div>
            <div class="candidate-list">
              <div v-for="candidate in analysis.candidates || []" :key="candidate.name" class="candidate-item">
                <div class="candidate-top">
                  <strong>{{ candidate.name }}</strong>
                  <span>{{ candidate.confidence || '低' }} / {{ candidate.phase || '待确认' }}</span>
                </div>
                <div class="candidate-summary">{{ candidate.summary || '-' }}</div>
                <div class="candidate-bits">
                  <span v-for="hit in candidate.rule_hits || []" :key="`${candidate.name}-${hit}`" class="bit-pill">{{ hit }}</span>
                </div>
                <div v-if="candidate.conflict_points?.length" class="candidate-conflict">
                  {{ candidate.conflict_points.join('；') }}
                </div>
              </div>
            </div>
          </article>

          <article class="content-card">
            <div class="section-kicker">关键标注</div>
            <div class="annotation-list">
              <div v-for="item in analysis.key_annotations || []" :key="`${item.label}-${item.price}`" class="annotation-item">
                <span>{{ item.label }}</span>
                <strong>{{ formatPrice(item.price) }}</strong>
              </div>
            </div>
            <div class="section-kicker section-kicker-space">特征快照</div>
            <div class="feature-grid">
              <div class="feature-item"><span>均线关系</span><strong>{{ features.ma_alignment || '-' }}</strong></div>
              <div class="feature-item"><span>20日位置</span><strong>{{ features.range20_position || '-' }}</strong></div>
              <div class="feature-item"><span>60日位置</span><strong>{{ features.range60_position || '-' }}</strong></div>
              <div class="feature-item"><span>量能状态</span><strong>{{ features.volume_pattern || '-' }}</strong></div>
              <div class="feature-item"><span>K线偏向</span><strong>{{ features.candle_bias || '-' }}</strong></div>
              <div class="feature-item"><span>20日振幅</span><strong>{{ formatPct(features.amplitude_20d_pct) }}</strong></div>
              <div class="feature-item"><span>60日振幅</span><strong>{{ formatPct(features.amplitude_60d_pct) }}</strong></div>
              <div class="feature-item"><span>重心变化</span><strong>{{ formatSignedPct(features.center_shift_20d_pct) }}</strong></div>
            </div>
            <div v-if="features.notes?.length" class="feature-notes">
              {{ features.notes.join(' ') }}
            </div>
          </article>
        </section>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { stockApi } from '../api'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const llmRefreshing = ref(false)
const data = ref(null)
const chartRef = ref(null)
const activeTradeDate = ref(String(route.query.tradeDate || getLocalDate()))
let chartInstance = null

const tsCode = computed(() => String(route.query.tsCode || route.query.ts_code || '').trim())
const stockName = computed(() => String(route.query.stockName || route.query.stock_name || '').trim())
const basicInfo = computed(() => data.value?.basic_info || {})
const analysis = computed(() => data.value?.pattern_analysis || {})
const features = computed(() => data.value?.feature_snapshot || {})
const llmStatus = computed(() => data.value?.llm_status || null)
const headerTitle = computed(() => `${stockName.value || basicInfo.value.stock_name || '个股'}形态分析`)
const confidenceTagType = computed(() => {
  if (analysis.value.confidence === '高') return 'success'
  if (analysis.value.confidence === '中') return 'warning'
  return 'info'
})
const llmStatusText = computed(() => llmStatus.value?.message || '')
const llmStatusType = computed(() => {
  if (llmStatus.value?.success) return 'success'
  if (llmStatus.value?.enabled) return 'warning'
  return 'info'
})

const getPayloadTradeDate = () => String(activeTradeDate.value || getLocalDate())

const syncQuery = () => {
  router.replace({
    path: '/pattern-analysis',
    query: {
      ...route.query,
      tsCode: tsCode.value,
      stockName: stockName.value || basicInfo.value.stock_name || '',
      tradeDate: getPayloadTradeDate(),
    },
  })
}

const loadData = async (options = {}) => {
  if (!tsCode.value) return
  if (!options.forceLlmRefresh) loading.value = true
  try {
    const res = await stockApi.patternAnalysis(tsCode.value, getPayloadTradeDate(), {
      forceLlmRefresh: Boolean(options.forceLlmRefresh),
      timeout: 120000,
    })
    data.value = res.data?.data || null
    await nextTick()
    renderChart()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '形态分析加载失败')
  } finally {
    loading.value = false
    llmRefreshing.value = false
  }
}

const refreshLlm = async () => {
  llmRefreshing.value = true
  await loadData({ forceLlmRefresh: true })
}

const buildChartOption = () => {
  const chartPayload = data.value?.chart_payload || {}
  const candles = chartPayload.candles || []
  const categories = candles.map((item) => item.trade_date)
  const candleValues = candles.map((item) => [item.open, item.close, item.low, item.high])
  const volumes = candles.map((item) => item.volume ?? 0)
  const movingAverages = chartPayload.moving_averages || {}
  const priceLines = chartPayload.price_lines || []
  const zones = chartPayload.zones || []
  const annotations = chartPayload.annotations || []
  const markLines = priceLines.map((item) => {
    if (item.start_trade_date && item.end_trade_date && item.start_price !== null && item.end_price !== null) {
      return [
        {
          coord: [item.start_trade_date, item.start_price],
          name: item.label,
          lineStyle: {
            width: item.line_type === 'breakout' ? 0.9 : (item.line_type === 'neckline' ? 0.85 : 1.2),
            type: item.line_type === 'breakout' ? 'dashed' : 'solid',
            color: lineColor(item.line_type),
            opacity: item.line_type === 'breakout' ? 0.62 : 0.9,
          },
          label: { show: false },
        },
        {
          coord: [item.end_trade_date, item.end_price],
          label: {
            formatter: item.label,
            color: lineColor(item.line_type),
          },
        },
      ]
    }
    return {
      yAxis: item.price,
      name: item.label,
      lineStyle: {
        width: item.line_type === 'breakout' ? 0.8 : (item.line_type === 'neckline' ? 0.75 : (item.line_type === 'defense' ? 2 : 1)),
        type: item.line_type === 'support' || item.line_type === 'breakout' ? 'dashed' : 'solid',
        color: lineColor(item.line_type),
        opacity: item.line_type === 'breakout' ? 0.58 : 1,
      },
      label: {
        formatter: `${item.label} ${Number(item.price).toFixed(2)}`,
        color: lineColor(item.line_type),
      },
    }
  }).flat()
  const markPoints = annotations
    .map((item) => {
      const index = categories.indexOf(item.trade_date)
      if (index === -1) return null
      return {
        coord: [categories[index], item.price],
        value: item.label,
        label: {
          formatter: item.label,
          color: '#0f172a',
          fontWeight: 700,
        },
        itemStyle: {
          color: '#f97316',
        },
      }
    })
    .filter(Boolean)

  return {
    animation: false,
    backgroundColor: 'transparent',
    legend: {
      top: 4,
      textStyle: { color: '#475569' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
    },
    grid: [
      { left: 56, right: 24, top: 56, height: '58%' },
      { left: 56, right: 24, top: '74%', height: '14%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: categories,
        boundaryGap: true,
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        axisLabel: { color: '#64748b' },
        min: Math.max(0, categories.length - (chartPayload.default_window || 100)),
        max: Math.max(0, categories.length - 1),
      },
      {
        type: 'category',
        gridIndex: 1,
        data: categories,
        boundaryGap: true,
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        axisLabel: { show: false },
      },
    ],
    yAxis: [
      {
        scale: true,
        axisLine: { show: false },
        splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.15)' } },
        axisLabel: { color: '#64748b' },
      },
      {
        scale: true,
        gridIndex: 1,
        axisLine: { show: false },
        splitLine: { show: false },
        axisLabel: { color: '#94a3b8' },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], startValue: Math.max(0, categories.length - 100), endValue: Math.max(0, categories.length - 1) },
      { show: true, xAxisIndex: [0, 1], type: 'slider', bottom: 6, height: 20 },
    ],
    visualMap: {
      show: false,
      seriesIndex: 5,
      dimension: 1,
      pieces: [
        { value: 1, color: '#ef4444' },
        { value: -1, color: '#10b981' },
      ],
    },
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: candleValues,
        itemStyle: {
          color: '#ef4444',
          color0: '#10b981',
          borderColor: '#ef4444',
          borderColor0: '#10b981',
        },
        markLine: markLines.length ? { symbol: 'none', data: markLines } : undefined,
        markPoint: markPoints.length ? { symbolSize: 42, data: markPoints } : undefined,
      },
      {
        name: 'MA5',
        type: 'line',
        data: movingAverages.ma5 || [],
        symbol: 'none',
        lineStyle: { width: 1.4, color: '#2563eb' },
      },
      {
        name: 'MA10',
        type: 'line',
        data: movingAverages.ma10 || [],
        symbol: 'none',
        lineStyle: { width: 1.4, color: '#8b5cf6' },
      },
      {
        name: 'MA20',
        type: 'line',
        data: movingAverages.ma20 || [],
        symbol: 'none',
        lineStyle: { width: 1.5, color: '#f59e0b' },
      },
      {
        name: 'MA60',
        type: 'line',
        data: movingAverages.ma60 || [],
        symbol: 'none',
        lineStyle: { width: 1.4, color: '#0f766e' },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes.map((value, index) => [index, candleValues[index]?.[1] >= candleValues[index]?.[0] ? 1 : -1, value]),
        encode: { x: 0, y: 2 },
      },
    ],
  }
}

const renderChart = () => {
  if (!chartRef.value || !data.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }
  const option = buildChartOption()
  const zones = data.value?.chart_payload?.zones || []
  zones.forEach((zone) => {
    const categories = (data.value?.chart_payload?.candles || []).map((item) => item.trade_date)
    const startIndex = categories.indexOf(zone.start_trade_date)
    const endIndex = categories.indexOf(zone.end_trade_date)
    if (startIndex === -1 || endIndex === -1) return
    option.series[0].markArea = option.series[0].markArea || {
      itemStyle: { color: 'rgba(245, 158, 11, 0.10)' },
      data: [],
    }
    option.series[0].markArea.data.push([
      { xAxis: categories[startIndex], yAxis: zone.low_price, name: zone.label },
      { xAxis: categories[endIndex], yAxis: zone.high_price },
    ])
  })
  chartInstance.setOption(option, true)
}

const handleResize = () => {
  chartInstance?.resize()
}

watch(
  () => [tsCode.value, String(route.query.tradeDate || '')],
  ([nextCode, nextDate], [prevCode, prevDate]) => {
    if (!nextCode) return
    if (nextCode === prevCode && nextDate === prevDate) return
    activeTradeDate.value = String(route.query.tradeDate || getLocalDate())
    loadData()
  }
)

watch(activeTradeDate, (value) => {
  if (!value || !tsCode.value) return
  syncQuery()
})

onMounted(async () => {
  if (tsCode.value) {
    await loadData()
  }
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
  chartInstance = null
})

function lineColor(type) {
  if (type === 'breakout') return '#2563eb'
  if (type === 'defense') return '#dc2626'
  if (type === 'support') return '#16a34a'
  return '#f59e0b'
}

function formatPrice(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(2)
}

function joinPrices(values) {
  if (!values?.length) return '-'
  return values.map((item) => formatPrice(item)).join(' / ')
}

function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toFixed(2)}%`
}

function formatSignedPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const number = Number(value)
  return `${number > 0 ? '+' : ''}${number.toFixed(2)}%`
}

function getLocalDate() {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}
</script>

<style scoped>
.pattern-analysis-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pattern-shell {
  border-radius: 24px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background:
    radial-gradient(circle at top left, rgba(14, 165, 233, 0.14), transparent 30%),
    radial-gradient(circle at right top, rgba(245, 158, 11, 0.16), transparent 22%),
    linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
}

.pattern-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.pattern-kicker,
.section-kicker,
.side-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.pattern-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 8px 0;
}

.pattern-title-row h2,
.section-head h3 {
  margin: 0;
  font-size: 28px;
  color: #0f172a;
}

.pattern-subtitle {
  color: #475569;
  max-width: 720px;
  line-height: 1.6;
}

.pattern-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.trade-date-picker {
  width: 160px;
}

.pattern-alert {
  margin-bottom: 16px;
}

.hero-grid,
.content-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.hero-card,
.content-card,
.chart-section {
  border-radius: 22px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(14px);
  padding: 20px;
}

.hero-card-primary {
  background:
    linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(30, 64, 175, 0.92)),
    linear-gradient(180deg, #0f172a, #1d4ed8);
  color: #f8fafc;
}

.hero-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hero-chip {
  border-radius: 999px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.16);
  font-size: 12px;
}

.hero-chip-muted {
  background: rgba(148, 163, 184, 0.18);
}

.hero-headline {
  margin-top: 16px;
  font-size: 34px;
  font-weight: 700;
}

.hero-copy {
  margin-top: 12px;
  line-height: 1.7;
  color: rgba(248, 250, 252, 0.88);
}

.hero-meta-grid,
.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.hero-metric,
.feature-item,
.annotation-item {
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hero-metric span,
.feature-item span,
.annotation-item span {
  color: #94a3b8;
  font-size: 12px;
}

.hero-metric strong,
.feature-item strong,
.annotation-item strong {
  color: inherit;
  font-size: 18px;
}

.hero-card-side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.side-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.side-section strong {
  font-size: 16px;
  line-height: 1.7;
  color: #0f172a;
}

.chart-section {
  margin-bottom: 16px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
}

.section-meta {
  display: flex;
  gap: 10px;
  color: #64748b;
  flex-wrap: wrap;
}

.chart-canvas {
  width: 100%;
  height: 560px;
}

.candidate-list,
.annotation-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.candidate-item {
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  padding: 14px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.88), rgba(241, 245, 249, 0.92));
}

.candidate-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  color: #0f172a;
}

.candidate-summary,
.candidate-conflict,
.feature-notes {
  margin-top: 10px;
  line-height: 1.7;
  color: #475569;
}

.candidate-bits {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.bit-pill {
  border-radius: 999px;
  padding: 6px 10px;
  background: rgba(37, 99, 235, 0.08);
  color: #1d4ed8;
  font-size: 12px;
}

.section-kicker-space {
  margin-top: 18px;
}

@media (max-width: 1200px) {
  .hero-grid,
  .content-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .pattern-header,
  .section-head {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-meta-grid,
  .feature-grid {
    grid-template-columns: 1fr;
  }

  .chart-canvas {
    height: 420px;
  }
}
</style>
