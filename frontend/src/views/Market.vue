<template>
  <div class="market-view">
    <el-card class="market-hero-card">
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
        <DataFreshnessBar
          :items="freshnessItems"
          :note="freshnessNote"
        />
        <div v-if="marketEnv" class="market-hero-shell">
          <section class="hero-overview">
            <div class="hero-tag-panel">
              <div class="hero-kicker">今日交易温度</div>
              <el-tag
                class="market-env-tag"
                size="large"
                effect="dark"
                :type="getEnvType(marketEnv.market_env_tag)"
              >
                {{ marketEnv.market_env_tag }}
              </el-tag>
              <div class="hero-headline">{{ marketHeadline }}</div>
              <div class="hero-subheadline">{{ marketSubheadline }}</div>
            </div>
            <div class="hero-comment-stack">
              <div
                v-for="(item, index) in marketCommentSections"
                :key="`${item.label}-${index}`"
                class="market-env-comment-line"
              >
                <span class="market-env-comment-label">{{ item.label }}</span>
                <span class="market-env-comment-text">{{ item.text }}</span>
              </div>
            </div>
          </section>

          <section class="hero-insights">
            <article
              v-for="item in heroInsights"
              :key="item.label"
              class="hero-insight-card"
              :class="`hero-insight-${item.tone}`"
            >
              <div class="hero-insight-label">{{ item.label }}</div>
              <div class="hero-insight-value">{{ item.value }}</div>
              <div class="hero-insight-copy">{{ item.copy }}</div>
            </article>
          </section>

          <div class="score-grid">
            <article
              v-for="item in scoreCards"
              :key="item.label"
              class="score-panel"
              :class="`score-panel-${item.tone}`"
            >
              <div class="score-panel-head">
                <div class="score-panel-label">{{ item.label }}</div>
                <div class="score-panel-value">{{ item.value }}</div>
              </div>
              <div class="score-track">
                <div class="score-fill" :style="{ width: `${item.progress}%` }" />
              </div>
              <div class="score-panel-copy">{{ item.copy }}</div>
            </article>
          </div>
        </div>
        <el-empty v-else description="暂无市场环境数据" />
      </template>
    </el-card>

    <el-card v-if="!loading" class="market-section-card index-section-card">
      <template #header>
        <div class="section-header">
          <span>主要指数行情</span>
          <span class="section-caption">看方向、斜率和量能是否共振</span>
        </div>
      </template>
      <div v-if="indexNotice" class="data-notice section-notice-index">
        {{ indexNotice }}
      </div>
      <el-empty v-if="!indexData?.length" description="暂无指数行情" />
      <div v-else class="index-card-grid">
        <article
          v-for="row in indexData"
          :key="row.name"
          class="index-quote-card"
        >
          <div class="index-quote-head">
            <div>
              <div class="index-quote-name">{{ row.name }}</div>
              <div :class="['index-source', { 'index-source-live': isRealtimeSource(row.data_source) }]">
                {{ quoteMetaLine(row.data_source, row.quote_time, row.trade_date) }}
              </div>
            </div>
            <div class="index-quote-price">{{ formatIndexPrice(row.close) }}</div>
          </div>
          <div class="index-change-line" :class="row.change_pct > 0 ? 'text-red' : 'text-green'">
            {{ formatSignedPct(row.change_pct) }}
          </div>
          <div class="index-quote-metrics">
            <div class="index-quote-metric">
              <span>成交量</span>
              <strong>{{ formatCompactAmount(row.volume) }}</strong>
            </div>
            <div class="index-quote-metric">
              <span>成交额</span>
              <strong>{{ formatCompactAmount(row.amount) }}</strong>
            </div>
          </div>
        </article>
      </div>
    </el-card>

    <el-card v-if="!loading" class="market-section-card">
      <template #header>
        <div class="section-header">
          <span>市场情绪指标</span>
          <span class="section-caption">看赚钱效应、亏钱效应和量能承接</span>
        </div>
      </template>
      <div v-if="statsNotice" class="data-notice section-notice-index">
        {{ statsNotice }}
      </div>
      <div v-if="marketStatsUnavailable" class="data-notice section-notice-index">
        实时市场状态暂不可用{{ staleFallbackSuffix }}
      </div>
      <el-empty v-if="!marketStats" description="暂无市场情绪数据" />
      <template v-else>
        <div class="sentiment-grid">
          <article
            v-for="item in sentimentCards"
            :key="item.label"
            class="sentiment-card"
          >
            <div class="sentiment-card-label">{{ item.label }}</div>
            <div class="sentiment-card-value" :class="item.className">{{ item.value }}</div>
            <div class="sentiment-card-copy">{{ item.copy }}</div>
          </article>
        </div>
        <div v-if="marketStats?.up_down_ratio" class="breadth-panel">
          <div class="breadth-panel-head">
            <div class="breadth-panel-title">市场广度</div>
            <div class="breadth-panel-summary">{{ breadthSummary }}</div>
          </div>
          <div class="breadth-bar">
            <div class="breadth-bar-up" :style="{ width: `${breadthRatios.up}%` }" />
            <div class="breadth-bar-flat" :style="{ width: `${breadthRatios.flat}%` }" />
            <div class="breadth-bar-down" :style="{ width: `${breadthRatios.down}%` }" />
          </div>
          <div class="breadth-chip-row">
            <span class="breadth-chip breadth-chip-up">上涨 {{ marketStats.up_down_ratio.up || 0 }}</span>
            <span class="breadth-chip breadth-chip-down">下跌 {{ marketStats.up_down_ratio.down || 0 }}</span>
            <span class="breadth-chip breadth-chip-flat">平盘 {{ marketStats.up_down_ratio.flat || 0 }}</span>
            <span class="breadth-chip">共 {{ marketStats.up_down_ratio.total || 0 }}</span>
          </div>
        </div>
      </template>
      <div v-if="marketStats && marketStats.up_down_ratio" class="market-breadth market-breadth-legacy">
        <span>上涨 {{ marketStats.up_down_ratio.up || 0 }}</span>
        <span>下跌 {{ marketStats.up_down_ratio.down || 0 }}</span>
        <span>平盘 {{ marketStats.up_down_ratio.flat || 0 }}</span>
        <span>共 {{ marketStats.up_down_ratio.total || 0 }}</span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { marketApi } from '../api'
import { ElMessage } from 'element-plus'
import { formatLocalTime } from '../utils/datetime'
import DataFreshnessBar from '../components/DataFreshnessBar.vue'

const loading = ref(false)
const marketEnv = ref(null)
const indexData = ref([])
const marketStats = ref(null)
const displayDate = ref('')
const resolvedDate = ref('')
const indexNotice = ref('')
const statsNotice = ref('')
const marketStatsUnavailable = ref(false)
const staleFallbackSuffix = ref('')
const statsRealtimeStatus = ref('')

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
const normalizeTradeDate = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (raw.length === 8) return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`
  return raw
}

const quoteSourceLabel = (source, sourceTradeDate, requestedTradeDate) => {
  if (!source) return '日线数据'
  if (String(source).startsWith('realtime_')) return '盘中实时'
  if (source === 'realtime_cache') return '实时缓存'
  if (source === 'unavailable') return '实时不可用'
  if (source === 'mock') return '模拟数据'
  const normalizedSourceDate = normalizeTradeDate(sourceTradeDate)
  const normalizedRequestedDate = normalizeTradeDate(requestedTradeDate)
  if (normalizedSourceDate && normalizedRequestedDate && normalizedSourceDate !== normalizedRequestedDate) {
    return '日线回退'
  }
  return '当日收盘'
}

const formatTurnover = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num) || num <= 0) return '-'
  return `${(num / 10000).toFixed(1)}万亿`
}

const formatIndexPrice = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return num.toFixed(2)
}

const formatSignedPct = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const formatCompactAmount = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num) || num <= 0) return '-'
  if (num >= 1e12) return `${(num / 1e12).toFixed(2)}万亿`
  if (num >= 1e8) return `${(num / 1e8).toFixed(2)}亿`
  if (num >= 1e4) return `${(num / 1e4).toFixed(1)}万`
  return `${Math.round(num)}`
}

const quoteMetaLine = (source, quoteTime, sourceTradeDate, requestedTradeDate = displayDate.value) => {
  const normalizedSourceDate = normalizeTradeDate(sourceTradeDate)
  const label = quoteSourceLabel(source, normalizedSourceDate, requestedTradeDate)
  if (quoteTime) return `${label} ${formatLocalTime(quoteTime)}`
  if (normalizedSourceDate) return `${label} ${normalizedSourceDate}`
  return label
}

const primaryIndexRow = computed(() => indexData.value?.[0] || null)
const freshnessItems = computed(() => {
  const envFallback = resolvedDate.value && resolvedDate.value !== displayDate.value
  const statsValue = marketStatsUnavailable.value
    ? `实时不可用${staleFallbackSuffix.value || ''}`
    : statsRealtimeStatus.value === 'live'
      ? '盘中实时'
      : statsRealtimeStatus.value === 'stale'
        ? '最近成功缓存'
        : (resolvedDate.value || displayDate.value || '-')

  return [
    { label: '请求日', value: displayDate.value || '-', tone: 'strong' },
    {
      label: '环境口径',
      value: envFallback ? `回退到 ${resolvedDate.value}` : '当日口径',
      tone: envFallback ? 'warn' : 'strong',
    },
    {
      label: '指数行情',
      value: primaryIndexRow.value
        ? quoteMetaLine(
            primaryIndexRow.value.data_source,
            primaryIndexRow.value.quote_time,
            primaryIndexRow.value.trade_date,
            displayDate.value
          )
        : '待加载',
      tone: primaryIndexRow.value && isRealtimeSource(primaryIndexRow.value.data_source) ? 'strong' : 'muted',
    },
    {
      label: '情绪统计',
      value: statsValue,
      tone: marketStatsUnavailable.value ? 'warn' : statsRealtimeStatus.value === 'live' ? 'strong' : 'muted',
    },
  ]
})

const freshnessNote = computed(() => (
  [dataNotice.value, indexNotice.value, statsNotice.value]
    .filter(Boolean)
    .join(' ')
))

const parseMarketComment = (comment) => {
  const segments = String(comment || '')
    .split(/[；;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
  if (!segments.length) return []

  const labels = ['市场结论', '主要依据', '操作建议']
  return segments.map((text, index) => ({
    label: labels[index] || `补充说明 ${index - labels.length + 1}`,
    text,
  }))
}

const scoreTone = (score) => {
  const value = Number(score)
  if (!Number.isFinite(value)) return 'neutral'
  if (value >= 70) return 'strong'
  if (value >= 40) return 'balanced'
  return 'weak'
}

const scoreCopy = (label, score) => {
  const value = Number(score)
  if (!Number.isFinite(value)) return `${label}暂无有效评分`
  if (value >= 70) return `${label}偏强，可以承担更多主动决策`
  if (value >= 40) return `${label}一般，最好等更清晰的确认`
  return `${label}偏弱，今天更适合先控风险`
}

const dominantSide = computed(() => {
  if (!marketEnv.value) return '-'
  const indexScore = Number(marketEnv.value.index_score || 0)
  const sentimentScore = Number(marketEnv.value.sentiment_score || 0)
  const delta = Math.abs(indexScore - sentimentScore)
  if (delta < 8) return '指数与情绪均衡'
  return indexScore > sentimentScore ? '指数端主导' : '情绪端主导'
})

const marketCommentSections = computed(() => parseMarketComment(marketEnv.value?.market_comment))

const marketHeadline = computed(() => {
  if (!marketEnv.value) return ''
  const tag = marketEnv.value.market_env_tag
  if (tag === '进攻') return '可以做确认后的主动进攻'
  if (tag === '防守') return '先守住回撤，再等下一次舒服机会'
  return '可以盯盘，但别急着抢第一笔'
})

const marketSubheadline = computed(() => {
  if (!marketEnv.value) return ''
  return `${dominantSide.value}，综合分 ${Number(marketEnv.value.overall_score || 0).toFixed(1)}`
})

const marketDataStatus = computed(() => {
  if (marketStatsUnavailable.value) return '实时不可用'
  if (statsRealtimeStatus.value === 'stale') return '使用最近缓存'
  if (statsRealtimeStatus.value === 'live') return '盘中实时'
  return resolvedDate.value && resolvedDate.value !== displayDate.value ? `按 ${resolvedDate.value} 口径` : '数据稳定'
})

const heroInsights = computed(() => {
  if (!marketEnv.value) return []
  return [
    {
      label: '交易节奏',
      value: marketEnv.value.breakout_allowed ? '可盯确认突破' : '暂停追突破',
      copy: marketEnv.value.breakout_allowed ? '更适合做确认后的主动出手。' : '以等确认、回踩承接和控仓为主。',
      tone: marketEnv.value.breakout_allowed ? 'strong' : 'weak',
    },
    {
      label: '风险等级',
      value: marketEnv.value.risk_level,
      copy: marketEnv.value.risk_level === '低' ? '可承受更高主动度。' : marketEnv.value.risk_level === '中' ? '仓位与节奏都要留余地。' : '先处理风险，不抢新机会。',
      tone: marketEnv.value.risk_level === '低' ? 'strong' : marketEnv.value.risk_level === '中' ? 'balanced' : 'weak',
    },
    {
      label: '主导因子',
      value: dominantSide.value,
      copy: '用于判断今天更该信指数，还是更该信情绪侧。',
      tone: 'balanced',
    },
    {
      label: '数据口径',
      value: marketDataStatus.value,
      copy: statsRealtimeStatus.value === 'stale' ? '页面正在使用最近一次成功实时缓存。' : '帮助判断结论是否来自盘中实时。', 
      tone: marketStatsUnavailable.value ? 'weak' : statsRealtimeStatus.value === 'stale' ? 'balanced' : 'strong',
    },
  ]
})

const scoreCards = computed(() => {
  if (!marketEnv.value) return []
  return [
    {
      label: '指数评分',
      value: Number(marketEnv.value.index_score || 0).toFixed(1),
      progress: Math.max(0, Math.min(100, Number(marketEnv.value.index_score || 0))),
      copy: scoreCopy('指数端', marketEnv.value.index_score),
      tone: scoreTone(marketEnv.value.index_score),
    },
    {
      label: '情绪评分',
      value: Number(marketEnv.value.sentiment_score || 0).toFixed(1),
      progress: Math.max(0, Math.min(100, Number(marketEnv.value.sentiment_score || 0))),
      copy: scoreCopy('情绪端', marketEnv.value.sentiment_score),
      tone: scoreTone(marketEnv.value.sentiment_score),
    },
    {
      label: '综合评分',
      value: Number(marketEnv.value.overall_score || 0).toFixed(1),
      progress: Math.max(0, Math.min(100, Number(marketEnv.value.overall_score || 0))),
      copy: scoreCopy('整体环境', marketEnv.value.overall_score),
      tone: scoreTone(marketEnv.value.overall_score),
    },
  ]
})

const sentimentCards = computed(() => {
  if (!marketStats.value) return []
  const brokenBoard = Number(marketStats.value.broken_board_rate || 0)
  return [
    {
      label: '涨停数',
      value: `${marketStats.value.limit_up_count ?? 0}`,
      copy: (marketStats.value.limit_up_count || 0) >= 50 ? '主线仍有打板扩散能力。' : '题材活跃度一般，别把局部当全市场。',
      className: 'text-red',
    },
    {
      label: '跌停数',
      value: `${marketStats.value.limit_down_count ?? 0}`,
      copy: (marketStats.value.limit_down_count || 0) >= 15 ? '亏钱效应抬头，追涨容错低。' : '亏钱效应暂未全面扩散。',
      className: 'text-green',
    },
    {
      label: '炸板率',
      value: `${brokenBoard.toFixed(1)}%`,
      copy: brokenBoard >= 30 ? '封板质量偏差，追高容易吃面。' : '封板质量尚可，但仍要看主线承接。',
      className: brokenBoardClass(brokenBoard),
    },
    {
      label: '成交额',
      value: formatTurnover(marketStats.value.market_turnover),
      copy: Number(marketStats.value.market_turnover || 0) >= 15000 ? '流动性够，分歧后更容易出修复。' : '量能一般，动作要更挑机会。',
      className: '',
    },
  ]
})

const breadthRatios = computed(() => {
  const source = marketStats.value?.up_down_ratio || {}
  const up = Number(source.up || 0)
  const down = Number(source.down || 0)
  const flat = Number(source.flat || 0)
  const total = Math.max(up + down + flat, 1)
  return {
    up: (up / total) * 100,
    down: (down / total) * 100,
    flat: (flat / total) * 100,
  }
})

const breadthSummary = computed(() => {
  const source = marketStats.value?.up_down_ratio || {}
  const up = Number(source.up || 0)
  const down = Number(source.down || 0)
  const ratio = up / Math.max(down, 1)
  if (ratio >= 1.5) return `上涨/下跌比 ${ratio.toFixed(2)}，个股赚钱效应占优`
  if (ratio >= 1.0) return `上涨/下跌比 ${ratio.toFixed(2)}，广度中性偏平衡`
  return `上涨/下跌比 ${ratio.toFixed(2)}，个股普遍偏弱`
})

const shouldShowSourceNotice = (source, sourceTradeDate, requestedTradeDate) => {
  const normalizedSourceDate = normalizeTradeDate(sourceTradeDate)
  const normalizedRequestedDate = normalizeTradeDate(requestedTradeDate)
  if (!source) return false
  if (source === 'mock') return true
  if (isRealtimeSource(source)) return true
  return Boolean(
    normalizedSourceDate &&
    normalizedRequestedDate &&
    normalizedSourceDate !== normalizedRequestedDate
  )
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
    statsRealtimeStatus.value = statsRes.data.data?.realtime_status || ''
    marketStatsUnavailable.value = statsRes.data.data?.realtime_status === 'unavailable'
    staleFallbackSuffix.value = statsRes.data.data?.realtime_stale_from_quote_time
      ? `，最近一次成功缓存时间 ${formatLocalTime(statsRes.data.data.realtime_stale_from_quote_time)}`
      : ''
    marketStats.value = marketStatsUnavailable.value ? null : statsRes.data.data
    resolvedDate.value = envRes.data.data?.resolved_trade_date || indexRes.data.data?.resolved_trade_date || statsRes.data.data?.resolved_trade_date || ''
    const firstIndex = indexData.value?.[0]
    indexNotice.value = firstIndex && shouldShowSourceNotice(
      firstIndex.data_source,
      firstIndex.trade_date,
      tradeDate
    )
      ? `指数行情当前使用${quoteMetaLine(firstIndex.data_source, firstIndex.quote_time, firstIndex.trade_date, tradeDate)}；情绪统计按 ${statsRes.data.data?.resolved_trade_date || resolvedDate.value || tradeDate} 口径计算。`
      : ''
    const turnoverText = quoteMetaLine(
      statsRes.data.data?.turnover_data_source,
      statsRes.data.data?.turnover_quote_time,
      statsRes.data.data?.resolved_trade_date,
      tradeDate
    )
    const breadthText = quoteMetaLine(
      statsRes.data.data?.up_down_data_source,
      statsRes.data.data?.up_down_quote_time,
      statsRes.data.data?.resolved_trade_date,
      tradeDate
    )
    const limitText = quoteMetaLine(
      statsRes.data.data?.limit_stats_data_source,
      statsRes.data.data?.limit_stats_quote_time,
      statsRes.data.data?.resolved_trade_date,
      tradeDate
    )
    const shouldShowStatsNotice = [
      shouldShowSourceNotice(
        statsRes.data.data?.up_down_data_source,
        statsRes.data.data?.resolved_trade_date,
        tradeDate
      ),
      shouldShowSourceNotice(
        statsRes.data.data?.turnover_data_source,
        statsRes.data.data?.resolved_trade_date,
        tradeDate
      ),
      shouldShowSourceNotice(
        statsRes.data.data?.limit_stats_data_source,
        statsRes.data.data?.resolved_trade_date,
        tradeDate
      )
    ].some(Boolean)
    if (statsRes.data.data?.realtime_status === 'stale') {
      const staleAt = statsRes.data.data?.realtime_stale_from_quote_time
      statsNotice.value = `实时市场状态当前使用最近一次成功缓存${staleAt ? `（${formatLocalTime(staleAt)}）` : ''}。`
    } else if (statsRes.data.data?.realtime_status === 'unavailable') {
      statsNotice.value = ''
    } else {
      statsNotice.value = shouldShowStatsNotice
        ? `涨跌家数使用${breadthText}，成交额使用${turnoverText}；涨跌停和炸板率使用${limitText}。`
        : ''
    }
    const notices = []
    if (statsRes.data.data?.realtime_status === 'unavailable') {
      notices.push('实时市场状态主源与兜底链路当前都不可用，已暂停展示盘中情绪统计。')
    } else if (isMixedMode(indexData.value, statsRes.data.data)) {
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

.market-hero-card {
  overflow: hidden;
}

.market-section-card {
  margin-top: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.section-caption {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.03em;
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
.market-hero-shell {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.hero-overview {
  display: grid;
  grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
  gap: 20px;
  align-items: stretch;
}

.hero-tag-panel {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 12px;
  justify-content: center;
  padding: 24px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top left, rgba(242, 54, 69, 0.22), transparent 48%),
    linear-gradient(160deg, rgba(42, 46, 57, 0.96), rgba(28, 32, 42, 0.94));
  border: 1px solid rgba(242, 54, 69, 0.16);
}

.hero-kicker {
  font-size: 12px;
  color: rgba(209, 212, 220, 0.66);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.market-hero-shell :deep(.market-env-tag.el-tag) {
  align-self: flex-start;
  font-size: clamp(1.35rem, 3vw, 2rem);
  font-weight: 700;
  line-height: 1.2;
  height: auto;
  padding: 14px 24px;
  border-radius: 14px;
  letter-spacing: 0.06em;
}

.hero-headline {
  font-size: clamp(1.4rem, 3vw, 2.2rem);
  font-weight: 700;
  line-height: 1.2;
  color: #f6f7fb;
}

.hero-subheadline {
  color: var(--color-text-sec);
  line-height: 1.6;
  max-width: 28rem;
}

.hero-comment-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.market-env-comment-line {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 18px;
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(42, 46, 57, 0.9), rgba(31, 35, 46, 0.92));
  border: 1px solid rgba(255, 255, 255, 0.04);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
  text-align: left;
}

.market-env-comment-label {
  flex-shrink: 0;
  min-width: 72px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--color-text-sec);
  letter-spacing: 0.04em;
}

.market-env-comment-text {
  font-size: 15px;
  line-height: 1.7;
  color: var(--color-text-pri);
}

.hero-insights {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.hero-insight-card {
  padding: 18px 18px 16px;
  border-radius: 16px;
  background: rgba(42, 46, 57, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.hero-insight-strong {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.14);
}

.hero-insight-balanced {
  box-shadow: inset 0 0 0 1px rgba(243, 194, 77, 0.14);
}

.hero-insight-weak {
  box-shadow: inset 0 0 0 1px rgba(242, 54, 69, 0.14);
}

.hero-insight-label {
  font-size: 12px;
  color: var(--color-text-sec);
  margin-bottom: 8px;
}

.hero-insight-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-pri);
  margin-bottom: 6px;
}

.hero-insight-copy {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-sec);
}

.score-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.score-panel {
  padding: 18px 18px 16px;
  border-radius: 16px;
  background: rgba(42, 46, 57, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.score-panel-strong {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.14);
}

.score-panel-balanced {
  box-shadow: inset 0 0 0 1px rgba(243, 194, 77, 0.14);
}

.score-panel-weak {
  box-shadow: inset 0 0 0 1px rgba(242, 54, 69, 0.14);
}

.score-panel-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
}

.score-panel-label {
  color: var(--color-text-sec);
  font-size: 13px;
}

.score-panel-value {
  font-size: clamp(1.85rem, 4vw, 2.7rem);
  font-weight: 700;
  line-height: 1;
}

.score-track {
  position: relative;
  width: 100%;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
}

.score-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, rgba(84, 210, 164, 0.68), rgba(243, 194, 77, 0.82), rgba(242, 54, 69, 0.86));
}

.score-panel-copy {
  margin-top: 12px;
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}

.index-card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.index-quote-card {
  padding: 18px;
  border-radius: 16px;
  background: rgba(42, 46, 57, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.index-quote-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.index-quote-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-pri);
  margin-bottom: 6px;
}

.index-quote-price {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-pri);
  letter-spacing: -0.02em;
}

.index-change-line {
  margin: 16px 0 14px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.index-quote-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.index-quote-metric {
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.index-quote-metric span {
  display: block;
  color: var(--color-text-sec);
  font-size: 12px;
  margin-bottom: 6px;
}

.index-quote-metric strong {
  color: var(--color-text-pri);
  font-size: 14px;
  font-weight: 600;
}

.sentiment-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.sentiment-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 156px;
  padding: 20px 18px;
  border-radius: 16px;
  background: rgba(42, 46, 57, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.sentiment-card-label {
  color: var(--color-text-sec);
  font-size: 13px;
  margin-bottom: 10px;
}

.sentiment-card-value {
  font-weight: 700;
  line-height: 1;
  font-size: clamp(2rem, 3.8vw, 3rem);
  margin-bottom: 12px;
}

.sentiment-card-value:not(.text-red):not(.text-green):not(.text-yellow) {
  color: var(--color-text-pri);
}

.sentiment-card-copy {
  color: var(--color-text-sec);
  line-height: 1.65;
  font-size: 13px;
}

.breadth-panel {
  margin-top: 18px;
  padding: 18px;
  border-radius: 16px;
  background: rgba(42, 46, 57, 0.56);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.breadth-panel-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.breadth-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-pri);
}

.breadth-panel-summary {
  color: var(--color-text-sec);
  font-size: 13px;
}

.breadth-bar {
  display: flex;
  overflow: hidden;
  height: 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
}

.breadth-bar-up {
  background: rgba(242, 54, 69, 0.88);
}

.breadth-bar-flat {
  background: rgba(243, 194, 77, 0.72);
}

.breadth-bar-down {
  background: rgba(8, 153, 129, 0.88);
}

.breadth-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.breadth-chip {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-text-sec);
  font-size: 12px;
}

.breadth-chip-up {
  color: var(--color-up);
}

.breadth-chip-down {
  color: var(--color-down);
}

.breadth-chip-flat {
  color: var(--color-neutral);
}

.market-breadth {
  margin-top: 12px;
  color: var(--color-text-sec);
  font-size: 12px;
}

.market-breadth-legacy {
  display: none;
}

@media (max-width: 1200px) {
  .hero-overview,
  .hero-insights,
  .score-grid,
  .index-card-grid,
  .sentiment-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .hero-overview,
  .hero-insights,
  .score-grid,
  .index-card-grid,
  .sentiment-grid,
  .index-quote-metrics {
    grid-template-columns: 1fr;
  }

  .hero-tag-panel,
  .market-env-comment-line,
  .hero-insight-card,
  .score-panel,
  .index-quote-card,
  .sentiment-card,
  .breadth-panel {
    padding: 16px;
  }

  .market-env-comment-label {
    min-width: 60px;
  }

  .breadth-panel-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
