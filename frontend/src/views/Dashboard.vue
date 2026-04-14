<template>
  <div class="dashboard">
    <el-card class="dashboard-hero-card">
      <template #header>
        <div class="card-header">
          <div class="section-header-copy">
            <span>今日执行摘要</span>
            <span class="section-caption">先判断今天该不该动，再看主线和执行清单。</span>
          </div>
          <el-button type="primary" @click="refreshData({ refresh: true })" :loading="refreshing">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>
      <div v-if="summary" class="dashboard-hero">
        <section class="hero-command">
          <div class="hero-kicker">今日主指令</div>
          <div class="hero-action" :class="getActionClass(summary.today_action)">
            {{ summary.today_action }}
          </div>
          <div class="hero-priority">{{ summary.priority_action }}</div>
          <div class="hero-tag-row">
            <span class="hero-chip">
              <strong>市场</strong>{{ marketEnvProfile || summary.market_env_tag || '-' }}
            </span>
            <span class="hero-chip">
              <strong>账户</strong>{{ summary.account_action_tag || '-' }}
            </span>
            <span class="hero-chip">
              <strong>突破</strong>{{ marketEnv?.breakout_allowed ? '可确认后做' : '先不追' }}
            </span>
          </div>
        </section>

        <section class="hero-sequence">
          <article
            v-for="item in todaySequence"
            :key="item.label"
            class="sequence-card"
            :class="`sequence-card-${item.tone}`"
          >
            <div class="sequence-step">{{ item.step }}</div>
            <div class="sequence-label">{{ item.label }}</div>
            <div class="sequence-value">{{ item.value }}</div>
            <div class="sequence-copy">{{ item.copy }}</div>
          </article>
        </section>

        <section class="hero-pulse">
          <article
            v-for="item in heroPulseCards"
            :key="item.label"
            class="pulse-card"
            :class="`pulse-card-${item.tone}`"
          >
            <div class="pulse-label">{{ item.label }}</div>
            <div class="pulse-value">{{ item.value }}</div>
            <div class="pulse-copy">{{ item.copy }}</div>
          </article>
        </section>
      </div>
      <el-skeleton v-else :rows="4" animated />
    </el-card>

    <div class="dashboard-core-grid">
      <el-card class="fill-card market-card dashboard-panel">
        <template #header>
          <div class="section-header-copy">
            <span>市场环境</span>
            <span class="section-caption">确认今天是进攻日、分歧日还是防守日。</span>
          </div>
        </template>
        <div v-if="marketEnv" class="market-env">
          <div class="market-env-tag-wrap">
            <el-tag
              class="market-env-tag"
              :type="getEnvTagType(marketEnvProfile)"
              effect="dark"
              size="large"
            >
              {{ marketEnvProfile }}
            </el-tag>
          </div>
          <div class="market-env-headline">{{ dashboardMarketHeadline }}</div>
          <div class="market-env-comment">
            <div
              v-for="(item, index) in parseMarketComment(marketEnv.market_comment)"
              :key="`${item.label}-${index}`"
              class="market-env-comment-line"
            >
              <span class="market-env-comment-label">{{ item.label }}</span>
              <span class="market-env-comment-text">{{ item.text }}</span>
            </div>
          </div>
          <div class="env-detail">
            <div class="env-detail-item">
              <span>突破允许</span>
              <strong>{{ marketEnv.breakout_allowed ? '是' : '否' }}</strong>
            </div>
            <div class="env-detail-item">
              <span>风险等级</span>
              <strong>{{ marketEnv.risk_level }}</strong>
            </div>
          </div>
        </div>
        <el-skeleton v-else :rows="3" animated class="fill-skeleton" />
      </el-card>

      <el-card class="fill-card sector-card dashboard-panel">
        <template #header>
          <div class="section-header-copy">
            <span>主线方向</span>
            <span class="section-caption">首页只保留一个焦点，但会明确它是题材主线还是承接行业。</span>
          </div>
        </template>
        <div v-if="leaderSector" class="leader-sector">
          <div class="leader-sector-hero">
            <div class="leader-sector-name">{{ leaderSector.sector.sector_name }}</div>
            <div class="leader-sector-change">{{ formatSignedPct(leaderSector.sector.sector_change_pct) }}</div>
            <el-tag size="small" effect="plain">{{ leaderSourceLabel }}</el-tag>
            <el-tag size="small" effect="plain">{{ leaderSector.sector.sector_mainline_tag }}</el-tag>
          </div>
          <div class="leader-sector-copy">{{ sectorNarrative }}</div>
        </div>
        <el-skeleton v-else :rows="3" animated class="fill-skeleton" />
      </el-card>

      <el-card class="fill-card account-card dashboard-panel">
        <template #header>
          <div class="section-header-copy">
            <span>账户概况</span>
            <span class="section-caption">先看仓位弹性，再决定今天能不能开仓。</span>
          </div>
        </template>
        <div v-if="accountProfile" class="account-profile">
          <div class="account-topline">
            <div class="account-topline-item">
              <span>总资产</span>
              <strong>{{ formatMoney(accountProfile.total_asset) }}</strong>
            </div>
            <div class="account-topline-item">
              <span>可用资金</span>
              <strong>{{ formatMoney(accountProfile.available_cash) }}</strong>
            </div>
          </div>
          <div class="position-meter">
            <div class="position-meter-head">
              <span>仓位</span>
              <strong>{{ formatPercent(accountProfile.total_position_ratio) }}</strong>
            </div>
            <div class="position-track">
              <div class="position-fill" :style="{ width: `${Math.min(Math.max((accountProfile.total_position_ratio || 0) * 100, 0), 100)}%` }" />
            </div>
            <div class="position-copy">{{ accountNarrative }}</div>
          </div>
          <div class="account-grid">
            <div class="account-metric-card">
              <span>持仓数</span>
              <strong>{{ accountProfile.holding_count }}只</strong>
            </div>
            <div class="account-metric-card">
              <span>账户动作</span>
              <strong>{{ summary?.account_action_tag || '-' }}</strong>
            </div>
          </div>
        </div>
        <el-skeleton v-else :rows="3" animated class="fill-skeleton" />
      </el-card>
    </div>

    <div class="dashboard-execution-grid">
      <el-card class="fill-card dashboard-bottom-card execution-panel">
        <template #header>
          <div class="section-header-copy">
            <span>持仓处理 ({{ holdingPreview.length }})</span>
            <span class="section-caption">先处理旧仓，再决定是否给新机会腾仓位。</span>
          </div>
        </template>
        <div class="bottom-card-body">
          <div class="execution-panel-intro execution-panel-intro-sell">
            <strong>{{ holdingPanelTitle }}</strong>
            <span>{{ holdingPanelCopy }}</span>
          </div>
          <el-skeleton v-if="loadingState.sellPoints && !sellPoints" :rows="5" animated class="fill-skeleton" />
          <el-empty
            v-else-if="!holdingPreview.length"
            description="暂无卖出/减仓信号"
          />
          <div v-else class="action-list">
            <article v-for="item in holdingPreview" :key="`${item.ts_code}-${item.stock_name}`" class="action-row action-row-sell">
              <div class="action-main">
                <div class="action-title">
                  <span class="action-name">{{ item.stock_name }}</span>
                  <span class="action-code">{{ item.ts_code }}</span>
                </div>
                <div class="action-meta">
                  <span class="action-chip action-chip-danger">{{ item.sell_signal_tag || '处理' }}</span>
                  <span class="action-chip">{{ item.sell_point_type || '未分类' }}</span>
                  <span v-if="item.pnl_pct !== null && item.pnl_pct !== undefined" class="action-chip">{{ formatSignedPct(item.pnl_pct) }}</span>
                </div>
                <div class="action-reason">{{ getHoldingReasonText(item) }}</div>
                <div class="action-row-actions">
                  <el-button type="warning" link size="small" @click="openPatternAnalysis(item)">形态分析</el-button>
                </div>
              </div>
              <div class="action-side">
                <div class="action-side-label">优先级</div>
                <div class="action-side-value">{{ getHoldingActionText(item) }}</div>
              </div>
            </article>
          </div>
        </div>
      </el-card>

      <el-card class="fill-card dashboard-bottom-card execution-panel">
        <template #header>
          <div class="section-header-copy">
            <span>可买候选 ({{ buyCandidates.length }})</span>
            <span class="section-caption">旧仓处理完，再看今天真正值得盯的开仓机会。</span>
          </div>
        </template>
        <div class="bottom-card-body">
          <div class="execution-panel-intro execution-panel-intro-buy">
            <strong>{{ buyPanelTitle }}</strong>
            <span>{{ buyPanelCopy }}</span>
          </div>
          <el-skeleton v-if="loadingState.buyPoints && !buyPoints" :rows="5" animated class="fill-skeleton" />
          <el-empty v-else-if="!buyCandidates.length" description="暂无可买候选" />
          <div v-else class="action-list">
            <article v-for="item in buyCandidates" :key="`${item.ts_code}-${item.stock_name}`" class="action-row">
              <div class="action-main">
                <div class="action-title">
                  <span class="action-name">{{ item.stock_name }}</span>
                  <span class="action-code">{{ item.ts_code }}</span>
                </div>
                <div class="action-meta">
                  <span class="action-chip">{{ item.candidate_bucket_tag || '未分层' }}</span>
                  <span class="action-chip">{{ item.buy_point_type || '待观察' }}</span>
                  <span class="action-chip">{{ item.buy_risk_level || '风险未标注' }}</span>
                </div>
                <div class="action-reason">{{ getBuyReasonText(item) }}</div>
                <div class="action-row-actions">
                  <el-button type="warning" link size="small" @click="openPatternAnalysis(item)">形态分析</el-button>
                </div>
              </div>
              <div class="action-side">
                <div class="action-side-label">今日动作</div>
                <div class="action-side-value">{{ getBuyActionText(item) }}</div>
              </div>
            </article>
          </div>
        </div>
      </el-card>
    </div>

    <el-card class="dashboard-review-card">
      <template #header>
        <div class="section-header-copy">
          <span>分层复盘统计</span>
          <span class="section-caption">执行顺序确定后，再用它校验今天优先看哪类机会。</span>
        </div>
      </template>
      <el-skeleton v-if="loadingState.reviewStats && !reviewStats" :rows="4" animated />
      <el-empty v-else-if="!reviewStats?.bucket_stats?.length" description="暂无复盘快照" />
      <template v-else>
        <div class="review-highlight-grid">
          <article
            v-for="item in reviewHighlights"
            :key="item.label"
            class="review-highlight-card"
          >
            <div class="review-highlight-label">{{ item.label }}</div>
            <div class="review-highlight-value">{{ item.value }}</div>
            <div class="review-highlight-copy">{{ item.copy }}</div>
          </article>
        </div>
        <el-table :data="reviewStats.bucket_stats.slice(0, 8)" style="width: 100%">
          <el-table-column label="类型" width="150">
            <template #default="{ row }">
              {{ reviewSnapshotTypeLabel(row.snapshot_type) }}
            </template>
          </el-table-column>
          <el-table-column prop="candidate_bucket_tag" label="分层" width="120" />
          <el-table-column prop="count" label="出现次数" width="100" />
          <el-table-column prop="avg_return_1d" label="1日均值" width="90" />
          <el-table-column prop="avg_return_3d" label="3日均值" width="90" />
          <el-table-column prop="avg_return_5d" label="5日均值" width="90" />
        </el-table>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { decisionApi, marketApi, sectorApi, accountApi } from '../api'
import { authState } from '../auth'
import { ElMessage } from 'element-plus'

const summary = ref(null)
const marketEnv = ref(null)
const leaderSector = ref(null)
const accountProfile = ref(null)
const buyPoints = ref(null)
const sellPoints = ref(null)
const route = useRoute()
const router = useRouter()
const reviewStats = ref(null)
const loadingState = ref({
  summary: false,
  marketEnv: false,
  leaderSector: false,
  accountProfile: false,
  buyPoints: false,
  sellPoints: false,
  reviewStats: false,
})

const openPatternAnalysis = (item) => {
  router.replace({
    path: route.path,
    query: {
      ...route.query,
      pattern_ts_code: item.ts_code,
      pattern_stock_name: item.stock_name || item.ts_code,
      pattern_trade_date: getLocalDate(),
    },
  })
}
const refreshVersion = ref(0)

const getActionClass = (action) => {
  if (action?.includes('少') || action?.includes('防守')) return 'text-red'
  if (action?.includes('适度') || action?.includes('积极')) return 'text-green'
  return 'text-yellow'
}

const getEnvTagType = (tag) => {
  if (['强进攻', '进攻', '中性偏强', '情绪修复'].includes(tag)) return 'success'
  if (['中性偏谨慎', '弱中性', '中性'].includes(tag)) return 'warning'
  return 'danger'
}

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

const formatMoney = (value) => {
  if (!value) return '-'
  return (value / 10000).toFixed(2) + '万'
}

const formatPercent = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return `${(num * 100).toFixed(1)}%`
}

const formatSignedPct = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const reviewSnapshotTypeLabel = (value) => {
  if (value === 'buy_available') return '买点-可买'
  if (value === 'buy_observe') return '买点-观察'
  if (value === 'buy_add') return '加仓候选'
  if (value === 'pool_account') return '三池-可参与池'
  if (value === 'pool_market') return '三池-观察池'
  return value || '-'
}

const DASHBOARD_REQUEST_TIMEOUT = 90000
const DASHBOARD_BUY_POINT_LIMIT = 10
const DASHBOARD_CACHE_PREFIX = 'dashboard_snapshot_v2'

const resolveDashboardCacheKey = () => {
  const accountId = authState.account?.id || 'guest'
  return `${DASHBOARD_CACHE_PREFIX}:${accountId}`
}

const refreshing = computed(() => Object.values(loadingState.value).some(Boolean))
const holdingActions = computed(() => {
  const data = sellPoints.value || {}
  return [
    ...(data.sell_positions || []),
    ...(data.reduce_positions || []),
  ]
})
const buyCandidates = computed(() => (buyPoints.value?.available_buy_points || []).slice(0, 5))
const holdingPreview = computed(() => holdingActions.value.slice(0, 5))
const marketEnvProfile = computed(() => marketEnv.value?.market_env_profile || marketEnv.value?.market_env_tag || '-')
const leaderSourceLabel = computed(() => {
  const source = leaderSector.value?.leader_source_type
  if (source === 'theme') return '主线题材'
  if (source === 'industry') return '承接行业'
  const sectorSource = leaderSector.value?.sector?.sector_source_type
  if (sectorSource === 'concept') return '题材焦点'
  if (sectorSource === 'limitup_industry') return '涨停行业'
  return '主线候选'
})
const dashboardMarketHeadline = computed(() => {
  if (!marketEnv.value) return ''
  if (marketEnv.value.market_headline) return marketEnv.value.market_headline
  if (marketEnvProfile.value === '进攻') return '环境允许主动找强，不必过度保守'
  if (marketEnvProfile.value === '防守') return '优先控仓和处理旧仓，等更舒服的确认'
  return '环境分歧明显，今天更重节奏和确认'
})
const sectorNarrative = computed(() => {
  const sector = leaderSector.value?.sector
  if (!sector) return ''
  const change = Number(sector.sector_change_pct || 0)
  const headline = `${leaderSourceLabel.value}：${sector.sector_name}`
  if (change >= 4) return `${headline} 是今天最强的方向之一，适合先从核心辨识度票入手，而不是乱撒网。`
  if (change >= 1) return `${headline} 仍有相对强度，但更适合做核心确认，不适合后排乱追。`
  return `${headline} 还在前排视野里，但强度一般，先看是否继续强化。`
})
const accountNarrative = computed(() => {
  const ratio = Number(accountProfile.value?.total_position_ratio || 0)
  if (!Number.isFinite(ratio)) return ''
  if (ratio >= 0.75) return '仓位已经偏高，今天更该考虑减法和调仓。'
  if (ratio >= 0.45) return '仓位居中，有选择地参与，不需要把每个机会都抓住。'
  return '仓位偏轻，若市场确认转强，账户仍有主动空间。'
})
const todaySequence = computed(() => ([
  {
    step: '01',
    label: '先处理旧仓',
    value: holdingActions.value.length ? `先看 ${holdingActions.value.length} 只持仓` : '旧仓暂时不用动',
    copy: holdingActions.value.length
      ? (summary.value?.focus || '先把该卖、该减的旧仓处理完，再考虑新开仓。')
      : '当前没有明确的卖出/减仓动作，新仓不会被旧风险打断。',
    tone: holdingActions.value.length ? 'risk' : 'clear',
  },
  {
    step: '02',
    label: '再盯主线',
    value: leaderSector.value?.sector?.sector_name || '主线待确认',
    copy: sectorNarrative.value || '先看主线有没有继续强化，再决定今天把精力放在哪个方向。',
    tone: leaderSector.value ? 'focus' : 'clear',
  },
  {
    step: '03',
    label: '最后决定开仓',
    value: summary.value?.account_action_tag || '等待账户结论',
    copy: accountNarrative.value || '先看账户仓位弹性和市场节奏，再决定今天能不能出手。',
    tone: summary.value?.account_action_tag?.includes('可') ? 'clear' : 'focus',
  },
]))
const heroPulseCards = computed(() => [
  {
    label: '待处理旧仓',
    value: `${holdingActions.value.length}`,
    copy: holdingActions.value.length > 0 ? '今天先处理旧仓，不要让新机会盖住旧风险。' : '没有强制减卖信号，旧仓暂时不会占用注意力。',
    tone: holdingActions.value.length > 0 ? 'weak' : 'strong',
  },
  {
    label: '可执行新仓',
    value: `${buyPoints.value?.available_buy_points?.length || 0}`,
    copy: (buyPoints.value?.available_buy_points?.length || 0) > 0 ? '候选是有的，但只盯前排，不撒网。' : '今天没有舒服的新票，等待本身就是纪律。',
    tone: (buyPoints.value?.available_buy_points?.length || 0) > 0 ? 'strong' : 'balanced',
  },
  {
    label: '账户弹性',
    value: accountProfile.value ? formatPercent(accountProfile.value.total_position_ratio) : '-',
    copy: accountNarrative.value || '等待账户数据加载。',
    tone: Number(accountProfile.value?.total_position_ratio || 0) > 0.7 ? 'weak' : Number(accountProfile.value?.total_position_ratio || 0) > 0.4 ? 'balanced' : 'strong',
  },
])
const holdingPanelTitle = computed(() => {
  if (holdingActions.value.length) return `今天先看 ${holdingActions.value.length} 只该动的持仓`
  return '旧仓暂时没有必须先动的地方'
})
const holdingPanelCopy = computed(() => {
  if (holdingActions.value.length) return '先处理最需要减卖的旧仓，再决定新仓还有没有必要看。'
  return '当前旧仓没有强制动作，可以把注意力更多留给主线确认。'
})
const buyPanelTitle = computed(() => {
  if (buyCandidates.value.length) return `再看 ${buyCandidates.value.length} 只可执行候选`
  return '今天没有真正舒服的新仓机会'
})
const buyPanelCopy = computed(() => {
  if (buyCandidates.value.length) return '这些票只代表进入执行名单，不代表都要买，仍要按前排顺序筛。'
  return '没有舒服机会时，不开新仓比勉强出手更重要。'
})
const getBuyActionText = (item) => {
  if (item.buy_signal_tag === '可买') return '确认后出手'
  if (item.buy_signal_tag === '观察') return '先观察'
  return item.buy_signal_tag || '等待确认'
}
const getBuyReasonText = (item) => (
  item.buy_comment
  || item.pool_decision_summary
  || item.execution_proximity_note
  || item.stock_comment
  || '进入执行名单，但仍要看主线强度和触发位是否配合。'
)
const getHoldingActionText = (item) => {
  if (item.sell_signal_tag === '卖出') return '先处理'
  if (item.sell_signal_tag === '减仓') return '先收缩'
  return item.sell_signal_tag || '处理'
}
const getHoldingReasonText = (item) => (
  item.sell_reason
  || item.sell_comment
  || '这只持仓已经进入处理名单，优先级高于新开仓。'
)
const reviewHighlights = computed(() => {
  const stats = reviewStats.value?.bucket_stats || []
  if (!stats.length) return []
  const sortedBy3d = [...stats].sort((a, b) => Number(b.avg_return_3d || 0) - Number(a.avg_return_3d || 0))
  const best = sortedBy3d[0]
  const weakest = sortedBy3d[sortedBy3d.length - 1]
  const topHit = [...stats].sort((a, b) => Number(b.count || 0) - Number(a.count || 0))[0]
  return [
    {
      label: '近期最强模式',
      value: best?.candidate_bucket_tag || '-',
      copy: best ? `近 3 日均值 ${Number(best.avg_return_3d || 0).toFixed(2)}，优先从这类机会里找样本。` : '暂无',
    },
    {
      label: '样本最多',
      value: topHit?.candidate_bucket_tag || '-',
      copy: topHit ? `最近出现 ${topHit.count} 次，适合结合当前市场验证稳定性。` : '暂无',
    },
    {
      label: '近期最弱模式',
      value: weakest?.candidate_bucket_tag || '-',
      copy: weakest ? `近 3 日均值 ${Number(weakest.avg_return_3d || 0).toFixed(2)}，今天少碰这类形态。` : '暂无',
    },
  ]
})

const getTradeDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const setModuleLoading = (key, value) => {
  loadingState.value = {
    ...loadingState.value,
    [key]: value
  }
}

const isAbortedRequest = (error) => {
  const code = String(error?.code || '')
  const message = String(error?.message || '').toLowerCase()
  return (
    code === 'ERR_CANCELED'
    || message.includes('request aborted')
    || message.includes('aborted')
    || message.includes('canceled')
  )
}

const persistDashboardCache = () => {
  if (typeof window === 'undefined') return
  const payload = {
    summary: summary.value,
    marketEnv: marketEnv.value,
    leaderSector: leaderSector.value,
    accountProfile: accountProfile.value,
    buyPoints: buyPoints.value,
    sellPoints: sellPoints.value,
    reviewStats: reviewStats.value,
    updatedAt: Date.now()
  }
  window.sessionStorage.setItem(resolveDashboardCacheKey(), JSON.stringify(payload))
}

const hydrateDashboardCache = () => {
  if (typeof window === 'undefined') return false
  const raw = window.sessionStorage.getItem(resolveDashboardCacheKey())
  if (!raw) return false
  try {
    const payload = JSON.parse(raw)
    summary.value = payload.summary || null
    marketEnv.value = payload.marketEnv || null
    leaderSector.value = payload.leaderSector || null
    accountProfile.value = payload.accountProfile || null
    buyPoints.value = payload.buyPoints || null
    sellPoints.value = payload.sellPoints || null
    reviewStats.value = payload.reviewStats || null
    return true
  } catch (error) {
    window.sessionStorage.removeItem(resolveDashboardCacheKey())
    return false
  }
}

const refreshData = async ({ silent = false, refresh = false } = {}) => {
  const version = refreshVersion.value + 1
  refreshVersion.value = version
  try {
    const tradeDate = getTradeDate()
    const failedModules = []

    const loadModule = async (key, label, loader, assign) => {
      setModuleLoading(key, true)
      try {
        const res = await loader()
        if (refreshVersion.value !== version) return
        assign(res.data.data)
      } catch (error) {
        if (isAbortedRequest(error)) {
          return
        }
        console.error(`${label}加载失败:`, error)
        if (refreshVersion.value === version) {
          failedModules.push(label)
        }
      } finally {
        if (refreshVersion.value === version) {
          setModuleLoading(key, false)
        }
      }
    }

    await Promise.allSettled([
      loadModule(
      'marketEnv',
      '市场环境',
      () => marketApi.getEnv(tradeDate, { timeout: DASHBOARD_REQUEST_TIMEOUT, refresh }),
      (data) => {
        marketEnv.value = data
      }
    ),
      loadModule(
      'summary',
      '执行摘要',
      () => decisionApi.summary(tradeDate, { timeout: DASHBOARD_REQUEST_TIMEOUT }),
      (data) => {
        summary.value = data
      }
    ),
      loadModule(
      'leaderSector',
      '主线板块',
      () => sectorApi.leader(tradeDate, { timeout: DASHBOARD_REQUEST_TIMEOUT }),
      (data) => {
        leaderSector.value = data
      }
    ),
      loadModule(
      'accountProfile',
      '账户概况',
      () => accountApi.profile({ timeout: DASHBOARD_REQUEST_TIMEOUT }),
      (data) => {
        accountProfile.value = data
      }
    ),
      loadModule(
      'buyPoints',
      '可买候选',
      () => decisionApi.buyPoint(tradeDate, DASHBOARD_BUY_POINT_LIMIT, { timeout: DASHBOARD_REQUEST_TIMEOUT }),
      (data) => {
        buyPoints.value = data
      }
    ),
      loadModule(
      'sellPoints',
      '持仓处理',
      () => decisionApi.sellPoint(tradeDate, {
        includeLlm: false,
        timeout: DASHBOARD_REQUEST_TIMEOUT
      }),
      (data) => {
        sellPoints.value = data
      }
    ),
      loadModule(
      'reviewStats',
      '复盘统计',
      () => decisionApi.reviewStats(10, { timeout: DASHBOARD_REQUEST_TIMEOUT, refresh }),
      (data) => {
        reviewStats.value = data
      }
    )])

    if (refreshVersion.value !== version) return

    if ([summary.value, marketEnv.value, leaderSector.value, accountProfile.value, buyPoints.value, sellPoints.value, reviewStats.value].some(Boolean)) {
      persistDashboardCache()
    }

    if (failedModules.length === 7) {
      throw new Error('全部接口加载失败')
    }

    if (failedModules.length && !silent) {
      ElMessage.warning(`部分数据加载失败：${failedModules.join('、')}`)
    } else if (!failedModules.length && !silent) {
      ElMessage.success('数据刷新成功')
    }
  } catch (error) {
    console.error('刷新数据失败:', error)
    if (!silent) {
      ElMessage.error('数据加载失败')
    }
  }
}

onMounted(() => {
  hydrateDashboardCache()
  refreshData({ silent: true })
})
</script>

<style scoped>
.dashboard {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.section-header-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.section-caption {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.03em;
}

.fill-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  width: 100%;
}
.fill-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.fill-skeleton {
  flex: 1;
  width: 100%;
}

.dashboard-hero-card {
  overflow: hidden;
}

.dashboard-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.9fr);
  gap: 18px;
}

.hero-command {
  padding: 24px;
  border-radius: 20px;
  background:
    radial-gradient(circle at top left, rgba(41, 98, 255, 0.16), transparent 40%),
    linear-gradient(160deg, rgba(42, 46, 57, 0.96), rgba(28, 32, 42, 0.96));
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.hero-kicker {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.hero-action {
  margin-top: 12px;
  font-size: clamp(2rem, 4vw, 3.2rem);
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: -0.03em;
}

.hero-action.text-red {
  color: var(--color-up);
}

.hero-action.text-green {
  color: #54d2a4;
}

.hero-action.text-yellow {
  color: #f3c24d;
}

.hero-priority {
  margin-top: 10px;
  color: var(--color-text-pri);
  font-size: 18px;
  line-height: 1.55;
  max-width: 34rem;
}

.hero-tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}

.hero-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-sec);
  font-size: 12px;
}

.hero-chip strong {
  color: var(--color-text-pri);
  font-weight: 600;
}

.hero-sequence {
  display: grid;
  gap: 14px;
}

.sequence-card {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(42, 46, 57, 0.72);
  display: grid;
  gap: 8px;
}

.sequence-card-focus {
  box-shadow: inset 0 0 0 1px rgba(41, 98, 255, 0.14);
}

.sequence-card-risk {
  box-shadow: inset 0 0 0 1px rgba(242, 54, 69, 0.14);
}

.sequence-card-clear {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.14);
}

.sequence-step,
.sequence-label {
  color: var(--color-text-sec);
  font-size: 12px;
}

.sequence-step {
  letter-spacing: 0.08em;
}

.sequence-value {
  color: var(--color-text-pri);
  font-size: 20px;
  font-weight: 700;
  line-height: 1.4;
}

.sequence-copy {
  color: var(--color-text-sec);
  line-height: 1.7;
  font-size: 14px;
}

.hero-pulse {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.pulse-card {
  padding: 18px;
  border-radius: 16px;
  background: rgba(42, 46, 57, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.pulse-card-strong {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.14);
}

.pulse-card-balanced {
  box-shadow: inset 0 0 0 1px rgba(243, 194, 77, 0.14);
}

.pulse-card-weak {
  box-shadow: inset 0 0 0 1px rgba(242, 54, 69, 0.14);
}

.pulse-label {
  color: var(--color-text-sec);
  font-size: 12px;
  margin-bottom: 8px;
}

.pulse-value {
  color: var(--color-text-pri);
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 8px;
}

.pulse-copy {
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}

.dashboard-core-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
  margin-top: 20px;
}

.dashboard-panel {
  min-height: 420px;
}

.market-env {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.market-env-tag-wrap {
  flex-shrink: 0;
  padding: 4px 0 8px;
}
.market-env :deep(.market-env-tag.el-tag) {
  font-size: clamp(1.35rem, 3vw, 2rem);
  font-weight: 700;
  line-height: 1.2;
  height: auto;
  padding: 14px 28px;
  border-radius: 10px;
  letter-spacing: 0.06em;
}

.market-env-headline {
  margin: 4px 0 14px;
  color: var(--color-text-pri);
  font-size: 18px;
  line-height: 1.5;
  font-weight: 600;
}

.market-env-comment {
  flex: 1;
  margin: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.market-env-comment-line {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--color-hover);
  border: 1px solid var(--color-border);
  text-align: left;
}

.market-env-comment-label {
  flex-shrink: 0;
  min-width: 60px;
  color: var(--color-text-sec);
  font-size: 12px;
  line-height: 1.7;
}

.market-env-comment-text {
  color: var(--color-text-pri);
  line-height: 1.6;
  font-size: 14px;
}

.env-detail {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
  padding-top: 10px;
  border-top: 1px solid var(--color-border);
}

.env-detail-item {
  flex: 1;
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--color-text-sec);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.env-detail-item strong {
  color: var(--color-text-pri);
  font-size: 15px;
}

.leader-sector {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 0;
}

.leader-sector-hero {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  padding: 22px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top left, rgba(84, 210, 164, 0.18), transparent 45%),
    linear-gradient(160deg, rgba(42, 46, 57, 0.96), rgba(28, 32, 42, 0.96));
  border: 1px solid rgba(84, 210, 164, 0.12);
}

.leader-sector-name {
  font-size: 28px;
  font-weight: 800;
  line-height: 1.1;
  color: var(--color-text-pri);
}

.leader-sector-change {
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
  color: var(--color-up);
}

.leader-sector-copy {
  margin-top: 18px;
  color: var(--color-text-sec);
  font-size: 14px;
  line-height: 1.7;
}

.account-profile {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 0;
}

.account-topline {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.account-topline-item,
.account-metric-card {
  padding: 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.account-topline-item span,
.account-metric-card span {
  display: block;
  color: var(--color-text-sec);
  font-size: 12px;
  margin-bottom: 8px;
}

.account-topline-item strong,
.account-metric-card strong {
  color: var(--color-text-pri);
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
}

.position-meter {
  margin-top: 18px;
  padding: 18px;
  border-radius: 16px;
  background: rgba(42, 46, 57, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.position-meter-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.position-meter-head span {
  color: var(--color-text-sec);
  font-size: 13px;
}

.position-meter-head strong {
  color: var(--color-text-pri);
  font-size: 18px;
  font-weight: 700;
}

.position-track {
  width: 100%;
  height: 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.position-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, rgba(84, 210, 164, 0.78), rgba(243, 194, 77, 0.8), rgba(242, 54, 69, 0.84));
}

.position-copy {
  margin-top: 12px;
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.65;
}

.account-grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.dashboard-review-card {
  margin-top: 20px;
}

.review-highlight-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.review-highlight-card {
  padding: 16px;
  border-radius: 14px;
  background: rgba(42, 46, 57, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.review-highlight-label {
  color: var(--color-text-sec);
  font-size: 12px;
  margin-bottom: 8px;
}

.review-highlight-value {
  color: var(--color-text-pri);
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 8px;
}

.review-highlight-copy {
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}

.dashboard-execution-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  margin-top: 20px;
}

.execution-panel {
  min-height: 380px;
}

.execution-panel-intro {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 16px;
  margin-bottom: 14px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.execution-panel-intro strong {
  font-size: 16px;
  line-height: 1.5;
}

.execution-panel-intro span {
  color: var(--color-text-sec);
  line-height: 1.6;
  font-size: 13px;
}

.execution-panel-intro-buy {
  background: rgba(84, 210, 164, 0.06);
  border-color: rgba(84, 210, 164, 0.14);
}

.execution-panel-intro-sell {
  background: rgba(242, 54, 69, 0.06);
  border-color: rgba(242, 54, 69, 0.14);
}

.action-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  border-radius: 14px;
  background: rgba(42, 46, 57, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.action-row-sell {
  box-shadow: inset 0 0 0 1px rgba(242, 54, 69, 0.08);
}

.action-main {
  min-width: 0;
}

.action-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.action-name {
  color: var(--color-text-pri);
  font-size: 16px;
  font-weight: 700;
}

.action-code {
  color: var(--color-text-sec);
  font-size: 12px;
}

.action-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.action-reason {
  margin-top: 10px;
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.65;
}

.action-row-actions {
  margin-top: 8px;
}

.action-chip {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-sec);
  font-size: 12px;
}

.action-chip-danger {
  color: var(--color-up);
}

.action-side {
  min-width: 88px;
  text-align: right;
}

.action-side-label {
  color: var(--color-text-sec);
  font-size: 12px;
  margin-bottom: 8px;
}

.action-side-value {
  color: var(--color-text-pri);
  font-size: 14px;
  font-weight: 600;
}

.dashboard-bottom-card .bottom-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.dashboard-bottom-card .bottom-card-body :deep(.el-empty) {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 32px 16px;
}
.dashboard-bottom-card .bottom-card-body :deep(.el-table) {
  flex: 1;
}

@media (max-width: 1280px) {
  .dashboard-hero,
  .dashboard-core-grid,
  .dashboard-execution-grid,
  .hero-pulse,
  .review-highlight-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .dashboard {
    padding: 16px;
  }

  .dashboard-hero,
  .dashboard-core-grid,
  .dashboard-execution-grid,
  .hero-pulse,
  .review-highlight-grid,
  .account-topline,
  .account-grid {
    grid-template-columns: 1fr;
  }

  .hero-command,
  .sequence-card,
  .pulse-card,
  .leader-sector-hero,
  .position-meter,
  .action-row {
    padding: 16px;
  }

  .action-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .action-side {
    text-align: left;
    min-width: 0;
  }

  .env-detail {
    flex-direction: column;
  }
}
</style>
