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
            <div class="hero-direction-panel">
              <div class="hero-direction-head">
                <span class="hero-direction-kicker">基于形态的后续看法（LLM）</span>
                <el-tag
                  v-if="analysis.direction_bias"
                  :type="directionBiasTagType"
                  effect="dark"
                  size="small"
                  class="hero-direction-tag"
                >
                  {{ analysis.direction_bias }}
                </el-tag>
                <span v-else class="hero-direction-pending">{{ directionBiasPlaceholder }}</span>
              </div>
              <p class="hero-direction-copy">
                {{ analysis.direction_rationale || directionRationalePlaceholder }}
              </p>
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
            <div class="side-section side-section-advice">
              <span class="side-kicker side-kicker-advice">操作建议</span>
              <strong>{{ analysis.action_advice || '-' }}</strong>
            </div>
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
          <div class="chart-workspace">
            <div class="chart-main">
              <div class="legend-strip">
                <span v-for="item in chartLegendItems" :key="item.label" class="legend-item">
                  <i :style="{ background: item.color }" />
                  <span>{{ item.label }}</span>
                </span>
              </div>
              <div ref="chartRef" class="chart-canvas" />
            </div>

            <aside class="chart-insight-rail">
              <article class="chart-insight-card chart-insight-card-primary">
                <div class="insight-card-head">
                  <span class="section-kicker">当日K线</span>
                  <strong>{{ currentCandleTitle }}</strong>
                </div>
                <div class="today-kline-price">
                  <strong>{{ formatPrice(currentClosePrice) }}</strong>
                  <span :class="['today-kline-badge', `today-kline-badge-${currentCandleTone}`]">
                    {{ currentCandleBadge }}
                  </span>
                </div>
                <p class="today-kline-note">{{ currentCandleNote }}</p>
                <div class="today-kline-grid">
                  <div v-for="item in currentCandleMetrics" :key="item.label" class="today-kline-item">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </div>
                </div>
              </article>

              <article class="chart-insight-card">
                <div class="insight-card-head">
                  <span class="section-kicker">关键价位</span>
                  <strong>今天最该盯的线</strong>
                </div>
                <div class="key-level-list">
                  <div
                    v-for="item in keyLevelRows"
                    :key="item.label"
                    :class="['key-level-row', `key-level-row-${item.tone}`]"
                  >
                    <div class="key-level-copy">
                      <span>{{ item.label }}</span>
                      <small>{{ item.note }}</small>
                    </div>
                    <strong>{{ item.value }}</strong>
                  </div>
                </div>
              </article>
            </aside>
          </div>
        </section>

        <section class="content-grid">
          <article class="content-card">
            <div class="section-kicker">候选形态</div>
            <div class="pattern-evidence-lead">为什么不是别的结构</div>
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
            <div class="feature-snapshot-bar">
              <div class="section-kicker section-kicker-space">特征快照</div>
              <el-button text type="primary" size="small" @click="featureSnapshotOpen = !featureSnapshotOpen">
                {{ featureSnapshotOpen ? '收起' : '展开' }}
              </el-button>
            </div>
            <div v-show="featureSnapshotOpen" class="feature-snapshot-body">
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
/** 右侧「特征快照」默认收起，与抽屉端一致 */
const featureSnapshotOpen = ref(false)
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
const isNecklinePattern = computed(() => ['双底修复', '双顶风险'].includes(analysis.value.primary_pattern))
const breakoutLabel = computed(() => (isNecklinePattern.value ? '颈线' : '突破线'))
const confidenceTagType = computed(() => {
  if (analysis.value.confidence === '高') return 'success'
  if (analysis.value.confidence === '中') return 'warning'
  return 'info'
})
const directionBiasTagType = computed(() => {
  const b = analysis.value.direction_bias
  if (b === '看多') return 'danger'
  if (b === '看空') return 'success'
  return 'info'
})
const directionBiasPlaceholder = computed(() => {
  if (!llmStatus.value?.enabled) return '未配置 LLM'
  if (llmStatus.value?.success && !analysis.value.direction_bias) return '待模型标注'
  if (!llmStatus.value?.success && llmStatus.value?.enabled) return '推理未就绪'
  return '—'
})
const directionRationalePlaceholder = computed(() => {
  if (analysis.value.direction_rationale) return ''
  if (!llmStatus.value?.enabled) {
    return '启用并配置 LLM 后，将结合当前 K 线形态与特征快照给出看多/看空倾向及理由。'
  }
  if (!llmStatus.value?.success && llmStatus.value?.enabled) {
    return String(llmStatus.value?.message || '请稍后点击「刷新解读」重试。')
  }
  return '模型未返回理由摘要，可点击「刷新解读」重试。'
})
const llmStatusText = computed(() => llmStatus.value?.message || '')
const llmStatusType = computed(() => {
  if (llmStatus.value?.success) return 'success'
  if (llmStatus.value?.enabled) return 'warning'
  return 'info'
})
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
const chartLegendItems = computed(() => ([
  { label: 'K线', color: '#ef4444' },
  { label: 'MA5', color: '#2563eb' },
  { label: 'MA10', color: '#8b5cf6' },
  { label: 'MA20', color: '#f59e0b' },
  { label: 'MA60', color: '#0f766e' },
  { label: '成交量', color: '#7dd3fc' },
  { label: breakoutLabel.value, color: '#2563eb' },
  { label: '防守线', color: '#dc2626' },
  { label: '支撑线', color: '#16a34a' },
  ...(analysis.value.primary_pattern === '上升趋势延续'
    ? [{ label: '抬升趋势线', color: '#0d9488' }]
    : []),
  { label: '平台区', color: 'rgba(245, 158, 11, 0.55)' },
]))
const currentCandleSnapshot = computed(() => {
  const candles = data.value?.chart_payload?.candles || []
  const today = data.value?.today_candle
  const hasHistoricalToday = Boolean(today?.trade_date && candles.some((item) => item.trade_date === today.trade_date))
  if (today?.trade_date && !hasHistoricalToday) {
    return { ...today, isPreview: true }
  }
  const latest = candles[candles.length - 1]
  if (latest) {
    return { ...latest, isPreview: false }
  }
  if (today?.trade_date) {
    return { ...today, isPreview: true }
  }
  return null
})
const currentClosePrice = computed(() => {
  const snapshot = currentCandleSnapshot.value
  if (snapshot?.close !== null && snapshot?.close !== undefined) return Number(snapshot.close)
  if (data.value?.latest_price !== null && data.value?.latest_price !== undefined) return Number(data.value.latest_price)
  return null
})
const currentCandleChangePct = computed(() => {
  const snapshot = currentCandleSnapshot.value
  if (!snapshot) return null
  if (snapshot.isPreview && data.value?.latest_change_pct !== null && data.value?.latest_change_pct !== undefined) {
    return Number(data.value.latest_change_pct)
  }
  const open = Number(snapshot.open)
  const close = Number(snapshot.close)
  if (!Number.isFinite(open) || !Number.isFinite(close) || open === 0) return null
  return ((close - open) / open) * 100
})
const currentCandleTone = computed(() => {
  const pct = currentCandleChangePct.value
  if (pct > 0) return 'up'
  if (pct < 0) return 'down'
  return currentCandleSnapshot.value?.isPreview ? 'watch' : 'flat'
})
const currentCandleTitle = computed(() => currentCandleSnapshot.value?.isPreview ? '盘中未完成K线' : '最新收盘K线')
const currentCandleBadge = computed(() => {
  const snapshot = currentCandleSnapshot.value
  if (!snapshot) return '暂无数据'
  if (snapshot.isPreview) {
    if (currentCandleChangePct.value === null) return '实时跟踪'
    return `${currentCandleChangePct.value > 0 ? '+' : ''}${currentCandleChangePct.value.toFixed(2)}%`
  }
  return snapshot.trade_date || data.value?.resolved_trade_date || '最新'
})
const currentCandleNote = computed(() => {
  if (!currentCandleSnapshot.value) return '暂无当日 K 线数据。'
  if (currentCandleSnapshot.value.isPreview) {
    return `虚线 K 线代表盘中未完成，优先盯现价与${breakoutLabel.value}、防守线的相对位置。`
  }
  return '收盘后优先确认收盘价站位是否仍然守住关键位，再结合量能判断结构是否延续。'
})
const currentCandleMetrics = computed(() => {
  const snapshot = currentCandleSnapshot.value
  return [
    { label: '日期', value: snapshot?.trade_date || '-' },
    { label: '开盘', value: formatPrice(snapshot?.open) },
    { label: '最高', value: formatPrice(snapshot?.high) },
    { label: '最低', value: formatPrice(snapshot?.low) },
    { label: snapshot?.isPreview ? '现价' : '收盘', value: formatPrice(snapshot?.close) },
    { label: '涨跌', value: formatSignedPct(currentCandleChangePct.value) },
  ]
})
const keyLevelRows = computed(() => patternFeatureItems.value.map((item) => ({
  ...item,
  tone: resolveLevelTone(item.label),
  note: buildLevelNote(item.value, currentClosePrice.value),
})))

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

  // 盘中未完成 K 线：若日期不在历史序列中则追加到最右侧
  const todayCandle = data.value?.today_candle
  if (todayCandle && todayCandle.trade_date && !categories.includes(todayCandle.trade_date)) {
    const tc = todayCandle
    const isUp = tc.close >= tc.open
    categories.push(tc.trade_date)
    candleValues.push({
      value: [tc.open, tc.close, tc.low, tc.high],
      itemStyle: {
        color:        isUp ? 'rgba(239,68,68,0.30)'   : 'rgba(16,185,129,0.30)',
        color0:       isUp ? 'rgba(239,68,68,0.30)'   : 'rgba(16,185,129,0.30)',
        borderColor:  isUp ? '#ef4444' : '#10b981',
        borderColor0: isUp ? '#ef4444' : '#10b981',
        borderWidth:  1.2,
        borderType:   'dashed',
      },
    })
    const tcVol = tc.volume > 0 ? tc.volume : 0
    const tcIsUp = tc.close >= tc.open
    volumes.push({
      value: tcVol,
      itemStyle: {
        color:   tcIsUp ? 'rgba(239,68,68,0.30)' : 'rgba(16,185,129,0.30)',
        borderColor: tcIsUp ? '#ef4444' : '#10b981',
        borderWidth: 1,
        borderType: 'dashed',
      },
    })
  }

  const movingAverages = chartPayload.moving_averages || {}
  const priceLines = chartPayload.price_lines || []
  const zones = chartPayload.zones || []
  const annotations = chartPayload.annotations || []
  const zoneColor = (zoneType) => {
    if (zoneType === 'neckline') return 'rgba(37, 99, 235, 0.07)'
    if (zoneType === 'flag_face') return 'rgba(245, 158, 11, 0.13)'
    return 'rgba(245, 158, 11, 0.10)'
  }

  const markLineLabelWithPrice = (label, priceVal) => {
    const p = formatPrice(priceVal)
    return p === '-' ? label : `${label} ${p}`
  }

  const markLines = priceLines.map((item) => {
    if (item.start_trade_date && item.end_trade_date && item.start_price !== null && item.end_price !== null) {
      const w = item.line_type === 'breakout' ? 0.9 : (item.line_type === 'neckline' ? 0.85 : 1.2)
      return [
        {
          coord: [item.start_trade_date, item.start_price],
          name: item.label,
          lineStyle: {
            width: w,
            type: item.line_type === 'breakout' ? 'dashed' : 'solid',
            color: lineColor(item.line_type),
            opacity: item.line_type === 'breakout' ? 0.62 : 0.9,
          },
          label: { show: false },
          emphasis: { label: { show: false } },
        },
        {
          coord: [item.end_trade_date, item.end_price],
          label: {
            show: true,
            formatter: item.label,
            position: 'end',
            distance: 8,
            color: lineColor(item.line_type),
            fontSize: 11,
            fontWeight: 700,
            backgroundColor: 'rgba(255,255,255,0.86)',
            borderRadius: 4,
            padding: [1, 4],
          },
          emphasis: {
            label: {
              formatter: markLineLabelWithPrice(item.label, item.end_price),
              fontSize: 12,
            },
            lineStyle: { width: w + 0.9 },
          },
        },
      ]
    }
    const baseW = item.line_type === 'breakout' ? 0.8 : (item.line_type === 'neckline' ? 0.75 : (item.line_type === 'defense' ? 2 : 1))
    return {
      yAxis: item.price,
      name: item.label,
      lineStyle: {
        width: baseW,
        type: item.line_type === 'support' || item.line_type === 'breakout' ? 'dashed' : 'solid',
        color: lineColor(item.line_type),
        opacity: item.line_type === 'breakout' ? 0.58 : 1,
      },
      label: {
        show: true,
        formatter: item.label,
        position: 'end',
        distance: 8,
        color: lineColor(item.line_type),
        fontSize: 11,
        fontWeight: 700,
        backgroundColor: 'rgba(255,255,255,0.86)',
        borderRadius: 4,
        padding: [1, 4],
      },
      emphasis: {
        label: {
          formatter: markLineLabelWithPrice(item.label, item.price),
          fontSize: 12,
        },
        lineStyle: { width: baseW + 0.9 },
      },
    }
  })
  const markPoints = annotations
    .map((item) => {
      const index = categories.indexOf(item.trade_date)
      if (index === -1) return null
      const isRetest = item.annotation_type === 'db_retest'
      const isBounce = item.annotation_type === 'channel_bounce'
      const isUptrendLow = item.annotation_type === 'uptrend_low'
      const isBottom = ['left_bottom', 'right_bottom', 'swing_low', 'db_retest', 'channel_bounce', 'uptrend_low'].includes(item.annotation_type)
      const isNeckline = item.annotation_type === 'neckline'
      const isBreakoutOrDefense = item.annotation_type === 'breakout' || item.annotation_type === 'defense'
      const ptColor = isRetest ? '#ef4444'
        : isUptrendLow ? '#0d9488'
        : isBounce ? '#10b981'
        : isBottom && !isUptrendLow ? '#16a34a'
        : ['left_top', 'right_top', 'swing_high'].includes(item.annotation_type) ? '#f97316'
        : item.annotation_type === 'defense' ? '#dc2626'
        : ['neckline', 'breakout'].includes(item.annotation_type) ? '#2563eb'
        : '#f97316'
      return {
        coord: [categories[index], item.price],
        value: item.label,
        symbol: isNeckline ? 'rect' : isBreakoutOrDefense ? 'roundRect' : 'circle',
        symbolSize: isNeckline ? [18, 2] : isBreakoutOrDefense ? [14, 9] : (isRetest || isBounce) ? 12 : isUptrendLow ? 13 : 16,
        label: {
          formatter: item.label,
          color: ptColor,
          fontWeight: 700,
          fontSize: isBreakoutOrDefense ? 10 : 11,
          position: isBottom ? 'bottom' : 'top',
          backgroundColor: 'rgba(255,255,255,0.92)',
          borderRadius: isBreakoutOrDefense ? 5 : 6,
          padding: isBreakoutOrDefense ? [0, 3] : [2, 5],
        },
        itemStyle: { color: ptColor },
      }
    })
    .filter(Boolean)

  // 形态示意连线：双底 W 形 / 双顶 M 形
  const patternShapeLines = []
  const annoMap = annotations.reduce((m, a) => {
    m[a.annotation_type] = m[a.annotation_type] || []
    m[a.annotation_type].push(a)
    return m
  }, {})
  const leftBottom = annoMap['left_bottom']?.[0]
  const rightBottom = annoMap['right_bottom']?.[0]
  const leftTop = annoMap['left_top']?.[0]
  const rightTop = annoMap['right_top']?.[0]
  if (leftBottom && rightBottom) {
    const midNeck = annotations.find(
      (a) => a.annotation_type === 'neckline' &&
        a.trade_date >= leftBottom.trade_date &&
        a.trade_date <= rightBottom.trade_date,
    )
    if (midNeck) {
      const s  = { width: 1.5, type: 'solid', color: '#2563eb', opacity: 0.55 }
      const sr = { width: 1.5, type: 'solid', color: '#10b981', opacity: 0.65 }
      // W 形左半：左底 → 颈线 → 右底
      patternShapeLines.push(
        [{ coord: [leftBottom.trade_date, leftBottom.price], lineStyle: s, label: { show: false } },
         { coord: [midNeck.trade_date, midNeck.price] }],
        [{ coord: [midNeck.trade_date, midNeck.price], lineStyle: s, label: { show: false } },
         { coord: [rightBottom.trade_date, rightBottom.price] }],
      )
      // W 形右半：右底 → 当前收盘（绿色，表示修复/突破）
      if (candles.length > 0) {
        const lastCandle = candles[candles.length - 1]
        patternShapeLines.push(
          [{ coord: [rightBottom.trade_date, rightBottom.price], lineStyle: sr, label: { show: false } },
           { coord: [lastCandle.trade_date, lastCandle.close] }],
        )
        // 颈线水平虚线延伸到当前（突破参考）
        const snk = { width: 1, type: 'dashed', color: '#2563eb', opacity: 0.35 }
        patternShapeLines.push(
          [{ coord: [midNeck.trade_date, midNeck.price], lineStyle: snk, label: { show: false } },
           { coord: [lastCandle.trade_date, midNeck.price] }],
        )
      }
    }
  }
  if (leftTop && rightTop) {
    const midNeck = annotations.find(
      (a) => a.annotation_type === 'neckline' &&
        a.trade_date >= leftTop.trade_date &&
        a.trade_date <= rightTop.trade_date,
    )
    if (midNeck) {
      const s  = { width: 1.5, type: 'solid', color: '#dc2626', opacity: 0.55 }
      const sd = { width: 1.5, type: 'solid', color: '#f97316', opacity: 0.60 }
      // M 形左半：左顶 → 颈线 → 右顶
      patternShapeLines.push(
        [{ coord: [leftTop.trade_date, leftTop.price], lineStyle: s, label: { show: false } },
         { coord: [midNeck.trade_date, midNeck.price] }],
        [{ coord: [midNeck.trade_date, midNeck.price], lineStyle: s, label: { show: false } },
         { coord: [rightTop.trade_date, rightTop.price] }],
      )
      // M 形右半：右顶 → 当前收盘（橙色，表示回落风险）
      if (candles.length > 0) {
        const lastCandle = candles[candles.length - 1]
        patternShapeLines.push(
          [{ coord: [rightTop.trade_date, rightTop.price], lineStyle: sd, label: { show: false } },
           { coord: [lastCandle.trade_date, lastCandle.close] }],
        )
        // 颈线水平虚线延伸到当前（跌破参考）
        const snk = { width: 1, type: 'dashed', color: '#dc2626', opacity: 0.35 }
        patternShapeLines.push(
          [{ coord: [midNeck.trade_date, midNeck.price], lineStyle: snk, label: { show: false } },
           { coord: [lastCandle.trade_date, midNeck.price] }],
        )
      }
    }
  }
  // 形态示意连线：V形修复  ── 顶点→底部→当前收盘
  const vPeak = annoMap['v_peak']?.[0]
  const vLow  = annoMap['v_low']?.[0]
  if (vPeak && vLow && candles.length > 0) {
    const lastCandle = candles[candles.length - 1]
    const sv = { width: 1.8, type: 'solid', color: '#10b981', opacity: 0.65 }
    patternShapeLines.push(
      [{ coord: [vPeak.trade_date, vPeak.price], lineStyle: sv, label: { show: false } },
       { coord: [vLow.trade_date,  vLow.price]  }],
      [{ coord: [vLow.trade_date,  vLow.price],  lineStyle: sv, label: { show: false } },
       { coord: [lastCandle.trade_date, lastCandle.close] }],
    )
  }

  // 形态示意连线：旗形中继  ── 旗杆线 + 旗面上下轨
  const flagPoleStart = annoMap['flag_pole_start']?.[0]
  const flagPoleTop   = annoMap['flag_pole_top']?.[0]
  if (flagPoleStart && flagPoleTop && candles.length > 0) {
    const lastCandle = candles[candles.length - 1]
    // 旗杆线：金色粗线，从旗杆起点到旗杆顶
    const sPole = { width: 2.2, type: 'solid', color: '#f59e0b', opacity: 0.80 }
    patternShapeLines.push(
      [{ coord: [flagPoleStart.trade_date, flagPoleStart.price], lineStyle: sPole, label: { show: false } },
       { coord: [flagPoleTop.trade_date,   flagPoleTop.price]   }],
    )
    // 旗面上下轨：从旗杆顶延伸到最后一根 K 线，蓝色虚线
    const flagFaceHigh = data.value?.feature_snapshot?.flag_face_high
    const flagFaceLow  = data.value?.feature_snapshot?.flag_face_low
    if (flagFaceHigh && flagFaceLow) {
      const sRail = { width: 1, type: 'dashed', color: '#3b82f6', opacity: 0.45 }
      patternShapeLines.push(
        [{ coord: [flagPoleTop.trade_date, flagFaceHigh], lineStyle: sRail, label: { show: false } },
         { coord: [lastCandle.trade_date,  flagFaceHigh] }],
        [{ coord: [flagPoleTop.trade_date, flagFaceLow],  lineStyle: sRail, label: { show: false } },
         { coord: [lastCandle.trade_date,  flagFaceLow]  }],
      )
    }
  }

  // 形态示意连线：下跌通道反抽  ── 从反抽低点到当前收盘画绿色弹升线
  const channelBounce = annoMap['channel_bounce']?.[0]
  if (channelBounce && candles.length > 0) {
    const lastCandle = candles[candles.length - 1]
    const sBounce = { width: 1.8, type: 'solid', color: '#10b981', opacity: 0.70 }
    patternShapeLines.push(
      [{ coord: [channelBounce.trade_date, channelBounce.price], lineStyle: sBounce, label: { show: false } },
       { coord: [lastCandle.trade_date,    lastCandle.close] }],
    )
  }

  // 形态示意连线：上升趋势延续  ── 抬升低点连线 + 趋势线外延（虚线）
  const uptrendLows = annoMap['uptrend_low'] || []
  if (uptrendLows.length >= 2 && categories.length > 0) {
    const sTrend = { width: 1.65, type: 'solid', color: '#0d9488', opacity: 0.68 }
    for (let i = 0; i < uptrendLows.length - 1; i += 1) {
      patternShapeLines.push(
        [{ coord: [uptrendLows[i].trade_date, uptrendLows[i].price], lineStyle: sTrend, label: { show: false } },
         { coord: [uptrendLows[i + 1].trade_date, uptrendLows[i + 1].price] }],
      )
    }
    const xEnd = categories[categories.length - 1]
    const penult = uptrendLows[uptrendLows.length - 2]
    const lastLow = uptrendLows[uptrendLows.length - 1]
    const i0 = categories.indexOf(penult.trade_date)
    const i1 = categories.indexOf(lastLow.trade_date)
    const i2 = categories.length - 1
    if (i0 >= 0 && i1 > i0 && i2 > i1) {
      const slope = (lastLow.price - penult.price) / (i1 - i0)
      const yExt = lastLow.price + slope * (i2 - i1)
      const sExt = { width: 1, type: 'dashed', color: '#0d9488', opacity: 0.42 }
      patternShapeLines.push(
        [{ coord: [lastLow.trade_date, lastLow.price], lineStyle: sExt, label: { show: false } },
         { coord: [xEnd, Math.round(yExt * 100) / 100] }],
      )
    }
  }

  // 现价参考线：仅在盘后（无虚 K 线）时显示水平参考线
  const latestPrice = data.value?.latest_price
  const latestChangePct = data.value?.latest_change_pct
  const latestPriceLines = []
  const hasTodayCandle = !!(todayCandle && todayCandle.trade_date && categories.includes(todayCandle.trade_date))
  if (!hasTodayCandle && latestPrice != null) {
    const lpColor = latestChangePct > 0 ? '#ef4444' : (latestChangePct < 0 ? '#10b981' : '#94a3b8')
    latestPriceLines.push({
      yAxis: latestPrice,
      name: '现价',
      lineStyle: { width: 1, type: 'dashed', color: lpColor, opacity: 0.80 },
      label: { show: false },
      emphasis: {
        label: {
          show: true,
          formatter: markLineLabelWithPrice('现价', latestPrice),
          position: 'end',
          distance: 8,
          color: lpColor,
          fontSize: 12,
          fontWeight: 700,
          backgroundColor: 'rgba(255,255,255,0.86)',
          borderRadius: 4,
          padding: [1, 4],
        },
        lineStyle: { width: 1.6 },
      },
    })
  }

  const allMarkLines = [...markLines, ...patternShapeLines, ...latestPriceLines]

  return {
    animation: false,
    backgroundColor: 'transparent',
    legend: { show: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
    },
    grid: [
      { left: 56, right: 120, top: 26, height: '62%' },
      { left: 56, right: 120, top: '76%', height: '12%' },
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
        markLine: allMarkLines.length ? { symbol: 'none', data: allMarkLines } : undefined,
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
        data: volumes.map((v, index) => {
          const raw = candleValues[index]
          const rawVal = raw?.value ?? raw
          const dir = (rawVal?.[1] ?? rawVal?.[0] ?? 0) >= (rawVal?.[0] ?? 0) ? 1 : -1
          const isObj = v !== null && typeof v === 'object' && !Array.isArray(v)
          const volNum = isObj ? (v.value ?? 0) : (v ?? 0)
          const item = { value: [index, dir, volNum] }
          if (isObj && v.itemStyle) item.itemStyle = v.itemStyle
          return item
        }),
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
  const zoneColorFn = (zoneType) => {
    if (zoneType === 'neckline') return 'rgba(37, 99, 235, 0.07)'
    if (zoneType === 'flag_face') return 'rgba(245, 158, 11, 0.13)'
    return 'rgba(245, 158, 11, 0.10)'
  }
  const zoneCategories = (data.value?.chart_payload?.candles || []).map((item) => item.trade_date)
  zones.forEach((zone) => {
    const startIndex = zoneCategories.indexOf(zone.start_trade_date)
    const endIndex = zoneCategories.indexOf(zone.end_trade_date)
    if (startIndex === -1 || endIndex === -1) return
    option.series[0].markArea = option.series[0].markArea || { data: [] }
    option.series[0].markArea.data.push([
      { xAxis: zoneCategories[startIndex], yAxis: zone.low_price, name: zone.label, itemStyle: { color: zoneColorFn(zone.zone_type) } },
      { xAxis: zoneCategories[endIndex], yAxis: zone.high_price },
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

function resolveLevelTone(label) {
  if (String(label).includes('防守')) return 'defense'
  if (String(label).includes('支撑') || String(label).includes('下沿') || String(label).includes('低')) return 'support'
  if (String(label).includes('压力')) return 'pressure'
  if (String(label).includes('突破') || String(label).includes('颈线') || String(label).includes('上沿') || String(label).includes('高')) return 'breakout'
  return 'neutral'
}

function buildLevelNote(value, currentPrice) {
  const price = Number(value)
  if (!Number.isFinite(price)) return '区间参考'
  if (!Number.isFinite(currentPrice) || currentPrice === 0) return '关键跟踪位'
  const deltaPct = ((price - currentPrice) / currentPrice) * 100
  if (Math.abs(deltaPct) < 0.35) return '接近现价'
  return deltaPct > 0 ? `高于现价 ${deltaPct.toFixed(2)}%` : `低于现价 ${Math.abs(deltaPct).toFixed(2)}%`
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
  if (patternName === '上升趋势延续') {
    return [
      pick('抬升低①'),
      pick('抬升低②'),
      pick('抬升低③'),
      pick(breakoutLabel.value, analysisState.breakout_level),
      pick('防守线', analysisState.defense_level),
      { label: '压力区', value: joinPrices(analysisState.pressure_levels) },
      { label: '支撑区', value: joinPrices(analysisState.support_levels) },
    ].filter((item) => item.value !== '-')
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

.side-kicker-advice {
  color: #f59e0b;
}

.side-section-advice {
  padding: 10px 12px;
  background: rgba(245, 158, 11, 0.07);
  border-left: 3px solid rgba(245, 158, 11, 0.6);
  border-radius: 0 6px 6px 0;
}

.side-section-advice strong {
  color: #fbbf24 !important;
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

.hero-direction-panel {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(15, 23, 42, 0.35);
}

.hero-direction-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.hero-direction-kicker {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #94a3b8;
}

.hero-direction-tag {
  font-weight: 600;
}

.hero-direction-pending {
  font-size: 13px;
  color: #cbd5e1;
}

.hero-direction-copy {
  margin: 10px 0 0;
  font-size: 14px;
  line-height: 1.65;
  color: rgba(248, 250, 252, 0.9);
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

.chart-workspace {
  display: grid;
  grid-template-columns: minmax(0, 2.15fr) 320px;
  gap: 16px;
  align-items: start;
}

.chart-main {
  min-width: 0;
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
  border-radius: 18px;
}

.chart-insight-rail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chart-insight-card {
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.94));
  padding: 18px;
  backdrop-filter: blur(12px);
}

.chart-insight-card-primary {
  background:
    radial-gradient(circle at top left, rgba(96, 165, 250, 0.2), transparent 30%),
    linear-gradient(135deg, #eff6ff 0%, #dbeafe 48%, #f8fafc 100%);
  border-color: rgba(59, 130, 246, 0.2);
}

.insight-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
}

.insight-card-head strong {
  color: #0f172a;
  font-size: 17px;
}

.today-kline-price {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.today-kline-price strong {
  color: #0f172a;
  font-size: 32px;
  line-height: 1;
}

.today-kline-badge {
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 600;
}

.today-kline-badge-up {
  background: rgba(239, 68, 68, 0.12);
  color: #dc2626;
}

.today-kline-badge-down {
  background: rgba(22, 163, 74, 0.12);
  color: #15803d;
}

.today-kline-badge-flat,
.today-kline-badge-watch {
  background: rgba(148, 163, 184, 0.14);
  color: #475569;
}

.today-kline-note {
  margin: 0 0 14px;
  color: #475569;
  line-height: 1.7;
  font-size: 13px;
}

.today-kline-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.today-kline-item,
.key-level-row {
  border-radius: 16px;
  padding: 12px 14px;
}

.today-kline-item {
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(148, 163, 184, 0.12);
}

.today-kline-item span,
.key-level-copy span,
.key-level-copy small {
  display: block;
}

.today-kline-item span,
.key-level-copy span {
  color: #64748b;
  font-size: 12px;
}

.today-kline-item strong {
  margin-top: 6px;
  color: #0f172a;
  font-size: 16px;
}

.key-level-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.key-level-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  border-left: 4px solid transparent;
  background: rgba(15, 23, 42, 0.04);
}

.key-level-copy {
  min-width: 0;
}

.key-level-copy small {
  margin-top: 4px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.5;
}

.key-level-row strong {
  color: #0f172a;
  font-size: 17px;
}

.key-level-row-breakout {
  border-left-color: #2563eb;
  background: rgba(37, 99, 235, 0.06);
}

.key-level-row-defense {
  border-left-color: #dc2626;
  background: rgba(220, 38, 38, 0.06);
}

.key-level-row-support {
  border-left-color: #16a34a;
  background: rgba(22, 163, 74, 0.06);
}

.key-level-row-pressure {
  border-left-color: #f59e0b;
  background: rgba(245, 158, 11, 0.08);
}

.key-level-row-neutral {
  border-left-color: #94a3b8;
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
  margin-top: 0;
}

.pattern-evidence-lead {
  margin: 6px 0 14px;
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.feature-snapshot-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 18px;
  flex-wrap: wrap;
}

.feature-snapshot-body {
  margin-top: 10px;
}

@media (max-width: 1200px) {
  .hero-grid,
  .content-grid,
  .chart-workspace {
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
  .feature-grid,
  .today-kline-grid {
    grid-template-columns: 1fr;
  }

  .chart-canvas {
    height: 420px;
  }
}
</style>
