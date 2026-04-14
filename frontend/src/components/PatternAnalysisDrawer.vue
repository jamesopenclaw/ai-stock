<template>
  <el-dialog
    :model-value="modelValue"
    width="92%"
    top="4vh"
    append-to-body
    destroy-on-close
    class="pattern-analysis-dialog"
    @close="handleClose"
  >
    <template #header>
      <div class="pattern-header">
        <div class="pattern-header-copy">
          <div class="pattern-kicker">股票形态分析</div>
          <div class="pattern-title-row">
            <h2>{{ headerTitle }}</h2>
            <el-tag :type="confidenceTagType" effect="dark">{{ analysis.confidence || '低' }}置信</el-tag>
          </div>
          <div class="pattern-subtitle">{{ analysis.pattern_summary || '围绕结构、关键位和候选形态做收敛判断。' }}</div>
          <div class="pattern-meta-row">
            <span class="meta-pill">{{ basicInfo.stock_name || stockName || '-' }} / {{ basicInfo.ts_code || tsCode || '-' }}</span>
            <span class="meta-pill">{{ basicInfo.sector_name || '未分类方向' }}</span>
            <span class="meta-pill">{{ data?.resolved_trade_date || tradeDate }}</span>
          </div>
        </div>
        <div class="pattern-actions">
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

    <el-empty v-if="!tsCode" description="缺少股票代码，请从个股入口进入形态分析。" />
    <el-skeleton v-else-if="loading && !data" :rows="10" animated />
    <el-empty v-else-if="!data" description="暂无形态分析结果" />
    <template v-else>
      <section class="decision-stage">
        <article class="thesis-panel">
          <div class="hero-chip-row">
            <span v-for="chip in stageChips" :key="chip" class="hero-chip">{{ chip }}</span>
          </div>
          <div class="thesis-title">{{ analysis.primary_pattern || '未识别明确形态' }}</div>
          <div class="thesis-copy">{{ analysis.pattern_rationale || analysis.pattern_summary || '-' }}</div>
          <div class="thesis-points">
            <div v-for="item in thesisPoints" :key="item.label" class="thesis-point">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </article>

        <aside class="decision-rail">
          <article class="rail-card rail-card-action">
            <span class="side-kicker">下一步怎么盯</span>
            <strong>{{ analysis.execution_hint || '-' }}</strong>
            <p>{{ analysis.invalid_if || '关键位失守后需要重新评估。' }}</p>
          </article>
          <article class="rail-card">
            <span class="side-kicker">最易误判点</span>
            <strong>{{ analysis.risk_hint || '-' }}</strong>
          </article>
        </aside>
      </section>

      <section class="signal-ribbon">
        <article v-for="item in quickSignalCards" :key="item.label" class="signal-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <em>{{ item.note }}</em>
        </article>
      </section>

      <section class="workspace-grid">
        <article class="chart-shell">
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
          <div class="legend-strip">
            <span v-for="item in chartLegendItems" :key="item.label" class="legend-item">
              <i :style="{ background: item.color }" />
              <span>{{ item.label }}</span>
            </span>
          </div>
          <div ref="chartRef" class="chart-canvas" />
        </article>

        <aside class="insight-rail">
          <article class="insight-card">
            <div class="insight-card-head">
              <span class="section-kicker">关键价位</span>
              <strong>今天最该盯的线</strong>
            </div>
            <div class="key-level-list">
              <div v-for="item in keyLevelItems" :key="item.label" class="key-level-row">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
          </article>

          <article class="insight-card">
            <div class="insight-card-head">
              <span class="section-kicker">结构信号</span>
              <strong>先看这几项</strong>
            </div>
            <div class="mini-signal-list">
              <div v-for="item in featureSummaryItems" :key="item.label" class="mini-signal-item">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
            <div v-if="features.notes?.length" class="feature-notes">
              {{ features.notes.join(' ') }}
            </div>
          </article>
        </aside>
      </section>

      <section class="evidence-grid">
        <article class="content-card content-card-candidate">
          <div class="content-card-head">
            <span class="section-kicker">候选形态</span>
            <strong>为什么不是别的结构</strong>
          </div>
          <div class="candidate-list">
            <div v-for="candidate in analysis.candidates || []" :key="candidate.name" class="candidate-item">
              <div class="candidate-top">
                <div class="candidate-title-group">
                  <strong>{{ candidate.name }}</strong>
                  <span>{{ candidate.confidence || '低' }} / {{ candidate.phase || '待确认' }}</span>
                </div>
                <em>{{ formatCandidateScore(candidate.score) }}</em>
              </div>
              <div class="candidate-summary">{{ candidate.summary || '-' }}</div>
              <div class="candidate-bits">
                <span v-for="hit in candidate.rule_hits || []" :key="`${candidate.name}-${hit}`" class="bit-pill">{{ hit }}</span>
              </div>
              <div v-if="candidate.conflictPoints?.length || candidate.conflict_points?.length" class="candidate-conflict">
                {{ (candidate.conflictPoints || candidate.conflict_points || []).join('；') }}
              </div>
            </div>
          </div>
        </article>

        <article class="content-card content-card-features">
          <div class="content-card-head">
            <span class="section-kicker">规则证据</span>
            <strong>机器实际看到了什么</strong>
          </div>
          <div class="feature-grid">
            <div v-for="item in detailedFeatureItems" :key="item.label" class="feature-item">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
          <div class="annotation-cluster">
            <span class="annotation-cluster-title">关键标注</span>
            <div class="annotation-list">
              <div v-for="item in analysis.key_annotations || []" :key="`${item.label}-${item.price}`" class="annotation-item">
                <span>{{ item.label }}</span>
                <strong>{{ formatPrice(item.price) }}</strong>
              </div>
            </div>
          </div>
        </article>
      </section>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { stockApi } from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  tsCode: { type: String, default: '' },
  stockName: { type: String, default: '' },
  tradeDate: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const llmRefreshing = ref(false)
const data = ref(null)
const chartRef = ref(null)
let chartInstance = null
let latestRequestId = 0

const basicInfo = computed(() => data.value?.basic_info || {})
const analysis = computed(() => data.value?.pattern_analysis || {})
const features = computed(() => data.value?.feature_snapshot || {})
const llmStatus = computed(() => data.value?.llm_status || null)
const headerTitle = computed(() => `${props.stockName || basicInfo.value.stock_name || '个股'}形态分析`)
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
const isNecklinePattern = computed(() => ['双底修复', '双顶风险'].includes(analysis.value.primary_pattern))
const breakoutLabel = computed(() => (isNecklinePattern.value ? '颈线' : '突破线'))
const annotationMap = computed(() => {
  const map = new Map()
  for (const item of analysis.value.key_annotations || []) {
    if (!item?.label || map.has(item.label)) continue
    map.set(item.label, item.price)
  }
  return map
})
const patternFeatureItems = computed(() => buildPatternFeatureItems(
  analysis.value.primary_pattern,
  annotationMap.value,
  analysis.value,
))
const stageChips = computed(() => ([
  analysis.value.primary_pattern || '未识别明确形态',
  analysis.value.pattern_phase || '待确认',
  `${analysis.value.confidence || '低'}置信`,
]).filter(Boolean))
const thesisPoints = computed(() => patternFeatureItems.value.slice(0, 4))
const quickSignalCards = computed(() => ([
  {
    label: '均线状态',
    value: features.value.ma_alignment || '-',
    note: features.value.candle_bias || '等待K线确认',
  },
  {
    label: '区间位置',
    value: `${features.value.range20_position || '-'} / ${features.value.range60_position || '-'}`,
    note: `20日振幅 ${formatPct(features.value.amplitude_20d_pct)}`,
  },
  {
    label: '量能状态',
    value: features.value.volume_pattern || '-',
    note: `量比 ${formatNumber(features.value.latest_vol_ratio)}`,
  },
  {
    label: '重心变化',
    value: formatSignedPct(features.value.center_shift_20d_pct),
    note: `收盘质量 ${formatRatio(features.value.close_quality)}`,
  },
]))
const chartLegendItems = computed(() => ([
  { label: breakoutLabel.value, color: '#2563eb' },
  { label: '防守线', color: '#dc2626' },
  { label: '支撑线', color: '#16a34a' },
  { label: '波段高低点', color: '#f97316' },
  { label: '平台区', color: 'rgba(245, 158, 11, 0.45)' },
]))
const keyLevelItems = computed(() => patternFeatureItems.value)
const featureSummaryItems = computed(() => ([
  { label: '均线关系', value: features.value.ma_alignment || '-' },
  { label: 'K线偏向', value: features.value.candle_bias || '-' },
  { label: '20日位置', value: features.value.range20_position || '-' },
  { label: '60日位置', value: features.value.range60_position || '-' },
  { label: '量能状态', value: features.value.volume_pattern || '-' },
  { label: '重心变化', value: formatSignedPct(features.value.center_shift_20d_pct) },
]))
const detailedFeatureItems = computed(() => ([
  { label: 'MA5', value: formatPrice(features.value.ma5) },
  { label: 'MA10', value: formatPrice(features.value.ma10) },
  { label: 'MA20', value: formatPrice(features.value.ma20) },
  { label: 'MA60', value: formatPrice(features.value.ma60) },
  { label: '20日高点', value: formatPrice(features.value.range20_high) },
  { label: '20日低点', value: formatPrice(features.value.range20_low) },
  { label: '60日高点', value: formatPrice(features.value.range60_high) },
  { label: '60日低点', value: formatPrice(features.value.range60_low) },
  { label: '20日振幅', value: formatPct(features.value.amplitude_20d_pct) },
  { label: '60日振幅', value: formatPct(features.value.amplitude_60d_pct) },
  { label: '量比', value: formatNumber(features.value.latest_vol_ratio) },
  { label: '换手', value: formatPct(features.value.latest_turnover_rate) },
]))

const handleClose = () => emit('update:modelValue', false)

const resetChart = () => {
  chartInstance?.dispose()
  chartInstance = null
}

const loadData = async (options = {}) => {
  if (!props.tsCode || !props.modelValue) return
  const requestId = ++latestRequestId
  if (!options.forceLlmRefresh) loading.value = true
  try {
    const res = await stockApi.patternAnalysis(props.tsCode, props.tradeDate || getLocalDate(), {
      forceLlmRefresh: Boolean(options.forceLlmRefresh),
      timeout: 120000,
    })
    if (requestId !== latestRequestId) return
    resetChart()
    data.value = res.data?.data || null
    await nextTick()
    await nextTick()
    renderChart()
  } catch (error) {
    if (requestId !== latestRequestId) return
    ElMessage.error(error?.response?.data?.message || '形态分析加载失败')
  } finally {
    if (requestId !== latestRequestId) return
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
          label: {
            show: false,
          },
        },
        {
          coord: [item.end_trade_date, item.end_price],
          label: {
            formatter: item.label,
            color: lineColor(item.line_type),
            position: 'end',
            distance: 10,
            backgroundColor: 'rgba(255,255,255,0.92)',
            borderRadius: 10,
            padding: [3, 8],
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
        formatter: item.label,
        color: lineColor(item.line_type),
        position: 'end',
        distance: 10,
        backgroundColor: 'rgba(255,255,255,0.92)',
        borderRadius: 10,
        padding: item.line_type === 'breakout' ? [2, 6] : [3, 8],
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
        symbol: annotationSymbol(item.annotation_type),
        symbolSize: annotationSymbolSize(item.annotation_type),
        label: {
          formatter: item.label,
          color: annotationColor(item.annotation_type),
          fontWeight: 700,
          position: annotationLabelPosition(item.annotation_type),
          backgroundColor: 'rgba(255,255,255,0.96)',
          borderRadius: 8,
          padding: item.annotation_type === 'neckline' ? [1, 4] : [3, 6],
        },
        itemStyle: {
          color: annotationColor(item.annotation_type),
        },
      }
    })
    .filter(Boolean)

  const option = {
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
      { left: 56, right: 92, top: 56, height: '58%' },
      { left: 56, right: 92, top: '74%', height: '14%' },
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
        markPoint: markPoints.length ? { data: markPoints } : undefined,
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
  zones.forEach((zone) => {
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
  return option
}

const renderChart = () => {
  if (!chartRef.value || !data.value) return
  if (chartRef.value.clientWidth <= 0 || chartRef.value.clientHeight <= 0) {
    requestAnimationFrame(() => {
      if (props.modelValue) renderChart()
    })
    return
  }
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }
  chartInstance.clear()
  chartInstance.setOption(buildChartOption(), true)
  chartInstance.resize()
}

const handleResize = () => chartInstance?.resize()

watch(
  () => [props.modelValue, props.tsCode, props.tradeDate],
  async ([visible, tsCode, tradeDate], [prevVisible, prevCode, prevDate]) => {
    if (!visible || !tsCode) {
      latestRequestId += 1
      loading.value = false
      llmRefreshing.value = false
      data.value = null
      resetChart()
      return
    }
    if (visible === prevVisible && tsCode === prevCode && tradeDate === prevDate) return
    data.value = null
    resetChart()
    await loadData()
  },
  { immediate: true }
)

watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible) {
      latestRequestId += 1
      data.value = null
      loading.value = false
      llmRefreshing.value = false
      resetChart()
      return
    }
    await nextTick()
    await nextTick()
    renderChart()
  }
)

onMounted(() => {
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

function annotationColor(type) {
  if (type === 'neckline' || type === 'breakout') return '#2563eb'
  if (type === 'defense') return '#dc2626'
  if (type === 'left_bottom' || type === 'right_bottom' || type === 'swing_low') return '#16a34a'
  if (type === 'left_top' || type === 'right_top' || type === 'swing_high') return '#f97316'
  return '#475569'
}

function annotationSymbol(type) {
  if (type === 'neckline') return 'rect'
  if (type === 'breakout' || type === 'defense') return 'roundRect'
  return 'circle'
}

function annotationSymbolSize(type) {
  if (type === 'neckline') return [18, 2]
  if (type === 'breakout' || type === 'defense') return [52, 22]
  return 16
}

function annotationLabelPosition(type) {
  if (type === 'left_bottom' || type === 'right_bottom' || type === 'swing_low') return 'bottom'
  return 'top'
}

function buildPatternFeatureItems(patternName, annotations, analysisState) {
  const pick = (label, fallback) => ({
    label,
    value: formatPrice(annotations.get(label) ?? fallback),
  })

  if (patternName === '双底修复') {
    return [
      pick('颈线', analysisState.breakout_level),
      pick('左底'),
      pick('右底'),
      pick('防守线', analysisState.defense_level),
      { label: '压力区', value: joinPrices(analysisState.pressure_levels) },
    ]
  }
  if (patternName === '双顶风险') {
    return [
      pick('颈线', analysisState.breakout_level),
      pick('左顶'),
      pick('右顶'),
      pick('防守线', analysisState.defense_level),
      { label: '支撑区', value: joinPrices(analysisState.support_levels) },
    ]
  }
  if (patternName === '平台整理' || patternName === '平台突破临界') {
    return [
      pick('平台上沿', analysisState.pressure_levels?.[0]),
      pick('平台下沿', analysisState.support_levels?.[0]),
      pick('突破线', analysisState.breakout_level),
      pick('防守线', analysisState.defense_level),
    ]
  }
  if (patternName === '箱体震荡') {
    return [
      pick('箱体上沿', analysisState.pressure_levels?.[0]),
      pick('箱体下沿', analysisState.support_levels?.[0]),
      pick('防守线', analysisState.defense_level),
      { label: '压力区', value: joinPrices(analysisState.pressure_levels) },
    ]
  }
  if (patternName === '三角收敛') {
    return [
      pick('收敛上沿', analysisState.pressure_levels?.[0]),
      pick('收敛下沿', analysisState.support_levels?.[0]),
      pick('突破线', analysisState.breakout_level),
      pick('防守线', analysisState.defense_level),
    ]
  }
  if (patternName === '旗形中继') {
    return [
      pick('旗面上沿', analysisState.pressure_levels?.[0]),
      pick('旗面下沿', analysisState.support_levels?.[0]),
      pick('突破线', analysisState.breakout_level),
      pick('防守线', analysisState.defense_level),
    ]
  }
  return [
    pick(breakoutLabel.value, analysisState.breakout_level),
    pick('防守线', analysisState.defense_level),
    pick('波段高点'),
    pick('波段低点'),
    { label: '压力区', value: joinPrices(analysisState.pressure_levels) },
    { label: '支撑区', value: joinPrices(analysisState.support_levels) },
  ].filter((item) => item.value !== '-')
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

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(2)
}

function formatRatio(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Math.round(Number(value) * 100)} / 100`
}

function formatCandidateScore(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '规则分 -'
  return `规则分 ${Math.round(Number(value) * 100)}`
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
.pattern-header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
  font-family: "Avenir Next", "PingFang SC", "Helvetica Neue", sans-serif;
  margin: -8px -6px 0;
  padding: 14px 16px 12px;
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(30, 41, 59, 0.92)),
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.22), transparent 34%);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.08);
}

.pattern-header-copy {
  min-width: 0;
}

.pattern-kicker,
.section-kicker,
.side-kicker {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #6b7280;
}

.pattern-kicker {
  color: rgba(191, 219, 254, 0.78);
}

.pattern-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 8px 0 10px;
}

.pattern-title-row h2,
.section-head h3 {
  margin: 0;
  font-size: 30px;
  line-height: 1.1;
  color: #0f172a;
  font-family: Georgia, "Times New Roman", "PingFang SC", serif;
}

.pattern-subtitle {
  max-width: 920px;
  color: #475569;
  line-height: 1.65;
}

.pattern-title-row h2 {
  color: #f8fafc;
}

.pattern-subtitle {
  color: rgba(226, 232, 240, 0.82);
}

.pattern-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.meta-pill,
.hero-chip,
.bit-pill {
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 12px;
}

.meta-pill {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(226, 232, 240, 0.88);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.pattern-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.pattern-alert {
  margin-bottom: 16px;
}

.decision-stage {
  display: grid;
  grid-template-columns: 2.2fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.thesis-panel,
.rail-card,
.signal-card,
.chart-shell,
.insight-card,
.content-card {
  border-radius: 24px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  backdrop-filter: blur(16px);
}

.thesis-panel {
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(96, 165, 250, 0.28), transparent 28%),
    radial-gradient(circle at right bottom, rgba(37, 99, 235, 0.24), transparent 32%),
    linear-gradient(135deg, #0f172a 0%, #172554 42%, #1d4ed8 100%);
  color: #f8fafc;
  box-shadow: 0 22px 40px rgba(15, 23, 42, 0.22);
}

.hero-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hero-chip {
  background: rgba(255, 255, 255, 0.12);
  color: #e2e8f0;
}

.thesis-title {
  margin-top: 16px;
  font-size: 42px;
  line-height: 1;
  font-weight: 700;
  font-family: Georgia, "Times New Roman", "PingFang SC", serif;
}

.thesis-copy {
  margin-top: 14px;
  max-width: 900px;
  color: rgba(241, 245, 249, 0.88);
  line-height: 1.75;
  font-size: 15px;
}

.thesis-points {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 20px;
}

.thesis-point {
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.thesis-point span {
  color: rgba(191, 219, 254, 0.82);
  font-size: 12px;
}

.thesis-point strong {
  font-size: 24px;
  color: #ffffff;
}

.decision-rail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.rail-card {
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.94), rgba(255, 255, 255, 0.92));
  padding: 20px;
}

.rail-card-action {
  background:
    linear-gradient(180deg, rgba(255, 251, 235, 0.96), rgba(255, 255, 255, 0.92));
  border-color: rgba(245, 158, 11, 0.24);
}

.rail-card strong {
  display: block;
  margin-top: 10px;
  font-size: 18px;
  line-height: 1.6;
  color: #111827;
}

.rail-card p {
  margin: 10px 0 0;
  color: #64748b;
  line-height: 1.65;
}

.signal-ribbon {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.signal-card {
  padding: 16px 18px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.9));
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.signal-card span {
  color: #64748b;
  font-size: 12px;
}

.signal-card strong {
  color: #0f172a;
  font-size: 20px;
}

.signal-card em {
  color: #475569;
  font-style: normal;
  line-height: 1.55;
  font-size: 13px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 2.1fr) 360px;
  gap: 16px;
  margin-bottom: 16px;
  align-items: start;
}

.chart-shell,
.content-card,
.insight-card {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(248, 250, 252, 0.92));
}

.chart-shell {
  padding: 20px;
}

.section-head,
.content-card-head,
.insight-card-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 14px;
}

.section-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #64748b;
  font-size: 13px;
}

.legend-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.04);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  font-size: 12px;
}

.legend-item i {
  width: 18px;
  height: 4px;
  border-radius: 999px;
  display: inline-block;
}

.chart-canvas {
  width: 100%;
  height: 520px;
  border-radius: 18px;
}

.insight-rail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.insight-card {
  padding: 18px;
}

.key-level-list,
.mini-signal-list,
.candidate-list,
.annotation-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.key-level-row,
.mini-signal-item,
.annotation-item,
.feature-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.04);
}

.key-level-row span,
.mini-signal-item span,
.annotation-item span,
.feature-item span {
  color: #64748b;
  font-size: 12px;
}

.key-level-row strong,
.mini-signal-item strong,
.annotation-item strong,
.feature-item strong {
  color: #0f172a;
  font-size: 17px;
}

.feature-notes {
  margin-top: 12px;
  color: #475569;
  line-height: 1.7;
  font-size: 13px;
}

.evidence-grid {
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: 16px;
}

.content-card {
  padding: 20px;
}

.content-card-head strong,
.insight-card-head strong {
  color: #111827;
  font-size: 18px;
}

.candidate-item {
  border-radius: 18px;
  padding: 16px;
  background:
    linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(241, 245, 249, 0.94));
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.candidate-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  color: #0f172a;
}

.candidate-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.candidate-title-group strong {
  font-size: 18px;
}

.candidate-title-group span,
.candidate-top em {
  color: #64748b;
  font-size: 12px;
  font-style: normal;
}

.candidate-summary,
.candidate-conflict {
  margin-top: 10px;
  line-height: 1.7;
  color: #475569;
}

.candidate-bits {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.bit-pill {
  background: rgba(37, 99, 235, 0.08);
  color: #1d4ed8;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.annotation-cluster {
  margin-top: 18px;
}

.annotation-cluster-title {
  display: inline-block;
  margin-bottom: 10px;
  color: #475569;
  font-size: 13px;
}

@media (max-width: 1360px) {
  .decision-stage,
  .workspace-grid,
  .evidence-grid {
    grid-template-columns: 1fr;
  }

  .signal-ribbon {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .thesis-points {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .pattern-header,
  .pattern-title-row,
  .section-head,
  .content-card-head,
  .insight-card-head {
    flex-direction: column;
    align-items: stretch;
  }

  .thesis-title {
    font-size: 32px;
  }

  .signal-ribbon,
  .thesis-points,
  .feature-grid {
    grid-template-columns: 1fr;
  }

  .chart-canvas {
    height: 420px;
  }
}
</style>
