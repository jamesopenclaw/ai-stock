<template>
  <div class="sectors-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>板块扫描结果</span>
          <div class="header-meta">
            <span class="trade-date">请求日 {{ scanData.trade_date || '-' }}</span>
            <span v-if="scanData.resolved_trade_date && scanData.resolved_trade_date !== scanData.trade_date" class="trade-date">
              实际扫描日 {{ scanData.resolved_trade_date }}
            </span>
          </div>
          <el-button @click="loadData({ refresh: true })" :loading="loading">刷新</el-button>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="12" animated />
      <template v-else>
      <div class="scan-hero" v-if="scanData.total_sectors">
        <div class="scan-hero-main">
          <div class="scan-kicker">今天先看什么</div>
          <div class="scan-hero-title">
            <span>{{ actionHeadline }}</span>
            <el-tag :type="actionTagType(primaryLeaderSector?.sector_action_hint)">{{ primaryLeaderSector?.sector_action_hint || '只观察' }}</el-tag>
          </div>
          <div class="scan-hero-copy">{{ actionCopy }}</div>
          <div class="scan-hero-chips">
            <el-tag type="danger">主线 {{ scanData.mainline_sectors?.length ?? 0 }}</el-tag>
            <el-tag type="warning">次主线 {{ scanData.sub_mainline_sectors?.length ?? 0 }}</el-tag>
            <el-tag>跟风 {{ scanData.follow_sectors?.length ?? 0 }}</el-tag>
            <el-tag type="info">杂毛 {{ scanData.trash_sectors?.length ?? 0 }}</el-tag>
            <el-tag :type="modeTagType">{{ modeTagLabel }}</el-tag>
            <el-tag v-if="scanData.threshold_profile === 'relaxed'" type="warning">放宽阈值</el-tag>
            <span class="total-text">共 {{ scanData.total_sectors }} 个板块</span>
          </div>
          <div class="scan-hero-actions">
            <el-button type="primary" @click="goToPage('/pools', primaryLeaderSector)">去三池分类</el-button>
            <el-button @click="goToPage('/buy', primaryLeaderSector)">去买点分析</el-button>
          </div>
        </div>
        <div class="scan-hero-side">
          <div class="hero-side-card">
            <div class="hero-side-label">市场环境</div>
            <div class="hero-side-value">{{ marketEnv?.market_env_tag || '未知' }}</div>
            <div class="hero-side-copy">{{ marketEnvTitle }}</div>
          </div>
        <div class="hero-side-card">
          <div class="hero-side-label">主线题材</div>
          <div class="hero-side-value">{{ themeLeaderSector?.sector_name || '暂无明确题材主线' }}</div>
          <div class="hero-side-copy">{{ themeLeaderSummary }}</div>
          <el-button
            v-if="themeLeaderSector && !leaderLoading && !leaderLoaded"
            type="primary"
            link
            size="small"
            @click="loadLeaderData()"
          >
            加载风向标
          </el-button>
          <el-button
            v-else-if="themeLeaderSector && leaderLoading"
            type="primary"
            link
            size="small"
            loading
          >
            加载中
          </el-button>
        </div>
        <div class="hero-side-card">
          <div class="hero-side-label">承接行业</div>
          <div class="hero-side-value">{{ industryLeaderSector?.sector_name || '暂无明确承接行业' }}</div>
          <div class="hero-side-copy">{{ industryLeaderSummary }}</div>
          <el-button
            v-if="industryLeaderSector && !leaderLoading && !leaderLoaded"
            type="primary"
            link
            size="small"
            @click="loadLeaderData()"
          >
            加载风向标
          </el-button>
          <el-button
            v-else-if="industryLeaderSector && leaderLoading"
            type="primary"
            link
            size="small"
            loading
          >
            加载中
          </el-button>
        </div>
      </div>
    </div>
      <el-alert
        v-if="sectorModeAlertVisible"
        :title="sectorModeAlertTitle"
        :description="scanData.concept_data_message || ''"
        :type="sectorModeAlertType"
        :closable="false"
        show-icon
        style="margin-bottom: 16px;"
      />

      <div v-if="scanData.total_sectors" class="scan-metrics">
        <div v-for="item in summaryCards" :key="item.label" class="metric-tile">
          <div class="metric-tile-label">{{ item.label }}</div>
          <div class="metric-tile-value">{{ item.value }}</div>
          <div class="metric-tile-copy">{{ item.copy }}</div>
        </div>
      </div>

      <div v-if="hasHotBoards" class="hot-boards-panel">
        <div class="hot-boards-head">
          <div>
            <div class="hot-boards-title">新浪热榜</div>
            <div class="hot-boards-desc">补一眼盘中最热的板块、行业和概念，作为外部热度参考，不替代你的板块扫描结论。</div>
          </div>
          <div class="hot-boards-meta">{{ hotBoardsMeta }}</div>
        </div>
        <div class="hot-boards-grid">
          <section v-for="group in hotBoardGroups" :key="group.key" class="hot-board-card">
            <div class="hot-board-card-head">
              <div>
                <div class="hot-board-card-title">{{ group.label }}</div>
                <div class="hot-board-card-copy">{{ group.copy }}</div>
              </div>
            </div>
            <div v-if="group.rows.length" class="hot-board-list">
              <button
                v-for="item in group.rows"
                :key="`${group.key}-${item.sector_id || item.sector_name}`"
                type="button"
                class="hot-board-row"
                @click="goToPage('/buy', item.sector_name)"
              >
                <div class="hot-board-row-main">
                  <div class="hot-board-row-name">{{ item.sector_name }}</div>
                  <div class="hot-board-row-meta">
                    <span>{{ item.leader_stock_name || '暂无领涨股' }}</span>
                    <span v-if="item.stock_count">成分 {{ item.stock_count }}</span>
                  </div>
                </div>
                <div class="hot-board-row-side">
                  <strong :class="item.sector_change_pct > 0 ? 'text-red' : 'text-green'">
                    {{ item.sector_change_pct?.toFixed(2) }}%
                  </strong>
                  <span>{{ formatHotBoardTime(item.quote_time) }}</span>
                </div>
              </button>
            </div>
            <div v-else class="hot-board-empty">当前未拿到这类热榜。</div>
          </section>
        </div>
      </div>

      <div v-if="focusRows.length" class="focus-board">
        <div class="focus-board-head">
          <div>
            <div class="focus-board-title">双主线视图</div>
            <div class="focus-board-desc">先区分题材主线和承接行业，再决定要不要去三池和买点页细看。</div>
          </div>
        </div>
        <div class="focus-board-grid">
          <article v-for="row in focusRows" :key="`focus-${row.sector_name}-${row.sector_source_type}`" class="focus-card">
            <div class="focus-card-top">
              <div>
                <div class="focus-card-title">{{ row.sector_name }}</div>
                <div class="focus-card-meta">{{ focusCardMeta(row) }}</div>
              </div>
              <el-tag size="small" :type="actionTagType(row.sector_action_hint)">{{ row.sector_action_hint || '-' }}</el-tag>
            </div>
            <div class="focus-card-bottom">
              <span>综合分 {{ row.sector_score }}</span>
              <span :class="row.sector_change_pct > 0 ? 'text-red' : 'text-green'">{{ row.sector_change_pct?.toFixed(2) }}%</span>
              <span>{{ row.sector_tradeability_tag || '-' }}</span>
            </div>
          </article>
        </div>
      </div>

      <el-tabs v-model="activeTab">
        <el-tab-pane v-for="pane in sectorPanes" :key="pane.name" :name="pane.name">
          <template #label>
            <span>{{ pane.label }} <em class="tab-count">{{ pane.count }}</em></span>
          </template>
          <el-empty v-if="!pane.rows.length" :description="pane.empty" />
          <div v-else class="sector-card-grid">
            <article v-for="row in pane.rows" :key="`${pane.name}-${row.sector_name}`" class="sector-card">
              <div class="sector-card-head">
                <div>
                  <div class="sector-card-title">{{ row.sector_name }}</div>
                  <div class="sector-card-meta">
                    <span>{{ sourceTagLabel(row.sector_source_type) }}</span>
                    <span>{{ row.sector_mainline_tag || '观察' }}</span>
                  </div>
                </div>
                <div class="sector-card-badges">
                  <el-tag size="small" :type="tierTagType(row.sector_tier)">{{ row.sector_tier || '-' }}类</el-tag>
                  <el-tag size="small" :type="actionTagType(row.sector_action_hint)">{{ row.sector_action_hint || '-' }}</el-tag>
                </div>
              </div>

              <div class="sector-score-strip">
                <div class="score-item">
                  <span class="score-label">涨跌幅</span>
                  <strong :class="row.sector_change_pct > 0 ? 'text-red' : 'text-green'">
                    {{ row.sector_change_pct?.toFixed(2) }}%
                  </strong>
                </div>
                <div class="score-item">
                  <span class="score-label">综合分</span>
                  <strong>{{ row.sector_score }}</strong>
                </div>
                <div class="score-item">
                  <span class="score-label">交易性</span>
                  <strong>{{ row.sector_tradeability_tag || '-' }}</strong>
                </div>
              </div>

              <div class="sector-dimension-grid" v-if="row.sector_dimension_scores">
                <span>联动 {{ row.sector_dimension_scores.linkage_score }}</span>
                <span>资金 {{ row.sector_dimension_scores.capital_score }}</span>
                <span>持续 {{ row.sector_dimension_scores.continuity_score }}</span>
                <span>抗分化 {{ row.sector_dimension_scores.resilience_score }}</span>
                <span>交易 {{ row.sector_dimension_scores.tradeability_score }}</span>
              </div>

              <div class="sector-card-copy">
                <div class="sector-copy-title">一句话结论</div>
                <div class="sector-copy-text">{{ row.sector_summary_reason || row.sector_comment || '暂无结论' }}</div>
              </div>

              <div class="sector-card-copy">
                <div class="sector-copy-title">下一步怎么盯</div>
                <div class="sector-copy-text">{{ sectorActionCopy(row) }}</div>
              </div>

              <div v-if="row.sector_falsification" class="sector-card-copy">
                <div class="sector-copy-title">什么情况下放弃</div>
                <div class="sector-copy-text">{{ row.sector_falsification }}</div>
              </div>

              <div class="reason-tags">
                <el-tag
                  v-for="tag in (row.sector_reason_tags || []).slice(0, 4)"
                  :key="tag"
                  size="small"
                  effect="plain"
                >
                  {{ tag }}
                </el-tag>
              </div>

              <div v-if="leaderStocksForSector(row).length" class="sector-leader-strip">
                <span class="sector-copy-title">风向标个股</span>
                <div class="sector-leader-list">
                  <button
                    v-for="stock in leaderStocksForSector(row)"
                    :key="`${row.sector_name}-${row.sector_source_type}-${stock.ts_code}`"
                    class="sector-leader-chip"
                    type="button"
                    @click="openCheckup(stock)"
                  >
                    {{ stock.stock_name }}
                    <strong :class="stock.change_pct > 0 ? 'text-red' : 'text-green'">
                      {{ stock.change_pct?.toFixed?.(2) ?? stock.change_pct }}%
                    </strong>
                  </button>
                </div>
              </div>

              <div class="sector-card-actions">
                <el-button type="primary" link size="small" @click="openTopStocks(row)">查看板块 Top10</el-button>
                <el-button type="primary" link size="small" @click="goToPage('/pools', row)">去三池看这个方向</el-button>
                <el-button type="primary" link size="small" @click="goToPage('/buy', row)">去买点找执行位</el-button>
              </div>
            </article>
          </div>
        </el-tab-pane>

        <el-tab-pane label="全部板块" name="all">
          <el-empty v-if="!allSectors.length" description="暂无板块数据" />
          <el-table v-else :data="allSectors" style="width: 100%" max-height="600">
            <el-table-column type="index" label="排名" width="60" />
            <el-table-column prop="sector_name" label="板块" width="140" />
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="sourceTagType(row.sector_source_type)">
                  {{ sourceTagLabel(row.sector_source_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="平均涨跌幅" width="110">
              <template #default="{ row }">
                <span :class="row.sector_change_pct > 0 ? 'text-red' : 'text-green'">
                  {{ row.sector_change_pct?.toFixed(2) }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="sector_mainline_tag" label="标签" width="90">
              <template #default="{ row }">
                <span :class="mainlineClass(row.sector_mainline_tag)">{{ row.sector_mainline_tag }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="sector_score" label="评分" width="80" />
            <el-table-column prop="sector_tier" label="分级" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="tierTagType(row.sector_tier)">{{ row.sector_tier || '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="sector_action_hint" label="执行" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="actionTagType(row.sector_action_hint)">{{ row.sector_action_hint || '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="sector_tradeability_tag" label="交易性" width="90" />
            <el-table-column label="五维摘要" min-width="190">
              <template #default="{ row }">
                <span class="dim-summary">{{ fiveDimSummary(row) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="原因" min-width="240">
              <template #default="{ row }">
                <div class="reason-tags">
                  <el-tag
                    v-for="tag in (row.sector_reason_tags || []).slice(0, 4)"
                    :key="tag"
                    size="small"
                    effect="plain"
                  >
                    {{ tag }}
                  </el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="sector_comment" label="简评" />
            <el-table-column prop="sector_summary_reason" label="主线结论" min-width="180" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
      </template>
    </el-card>
  </div>
  <StockCheckupDrawer
    v-model="checkupVisible"
    :ts-code="checkupStock.tsCode"
    :stock-name="checkupStock.stockName"
    :default-target="checkupStock.defaultTarget"
    :trade-date="scanData.trade_date || getLocalDate()"
  />
  <SectorTopStocksDrawer
    v-model="topStocksVisible"
    :trade-date="scanData.trade_date || getLocalDate()"
    :sector="activeTopSector"
    @checkup="openCheckup"
  />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { sectorApi, marketApi } from '../api'
import { ElMessage } from 'element-plus'
import StockCheckupDrawer from '../components/StockCheckupDrawer.vue'
import SectorTopStocksDrawer from '../components/SectorTopStocksDrawer.vue'
import { formatLocalTime } from '../utils/datetime'

const SECTORS_REQUEST_TIMEOUT = 90000
const loading = ref(false)
const leaderLoading = ref(false)
const leaderLoaded = ref(false)
const activeTab = ref('mainline')
const marketEnv = ref(null)
const leaderData = ref(null)
const hotBoards = ref({
  trade_date: '',
  resolved_trade_date: '',
  data_source: '',
  leader_boards: [],
  industry_boards: [],
  concept_boards: [],
})
const router = useRouter()
const checkupVisible = ref(false)
const checkupStock = ref({ tsCode: '', stockName: '', defaultTarget: '观察型' })
const topStocksVisible = ref(false)
const activeTopSector = ref(null)
const loadVersion = ref(0)

const createDefaultScanData = () => ({
  trade_date: '',
  resolved_trade_date: '',
  sector_data_mode: '',
  concept_data_status: '',
  concept_data_message: '',
  threshold_profile: '',
  theme_leaders: [],
  industry_leaders: [],
  mainline_sectors: [],
  sub_mainline_sectors: [],
  follow_sectors: [],
  trash_sectors: [],
  total_sectors: 0
})
const scanData = ref(createDefaultScanData())

const mainlineClass = (tag) => {
  if (tag === '主线') return 'text-red'
  if (tag === '次主线') return 'text-yellow'
  return ''
}

const marketEnvTagType = computed(() => {
  const tag = marketEnv.value?.market_env_tag
  if (tag === '进攻') return 'success'
  if (tag === '中性') return 'warning'
  return 'danger'
})

const sourceTagType = (sourceType) => {
  if (sourceType === 'concept') return 'danger'
  if (sourceType === 'limitup_industry') return 'warning'
  return 'info'
}

const sourceTagLabel = (sourceType) => {
  if (sourceType === 'concept') return '题材'
  if (sourceType === 'limitup_industry') return '涨停行业'
  return '行业'
}

const allSectors = computed(() => {
  const all = [
    ...(scanData.value.mainline_sectors || []),
    ...(scanData.value.sub_mainline_sectors || []),
    ...(scanData.value.follow_sectors || []),
    ...(scanData.value.trash_sectors || []),
  ]
  return all.sort((a, b) => b.sector_change_pct - a.sector_change_pct)
})

const focusRows = computed(() => (
  [
    ...(scanData.value.theme_leaders || []).slice(0, 2),
    ...(scanData.value.industry_leaders || []).slice(0, 2),
  ].slice(0, 4)
))

const hotBoardGroups = computed(() => ([
  {
    key: 'leader',
    label: '领涨板块',
    copy: '盘中最强的综合热度方向',
    rows: hotBoards.value.leader_boards || [],
  },
  {
    key: 'industry',
    label: '热门行业',
    copy: '更偏行业逻辑的强势分支',
    rows: hotBoards.value.industry_boards || [],
  },
  {
    key: 'concept',
    label: '热门概念',
    copy: '更偏题材情绪的热度排行',
    rows: hotBoards.value.concept_boards || [],
  },
]))

const hasHotBoards = computed(() => hotBoardGroups.value.some((group) => group.rows.length))

const hotBoardsMeta = computed(() => {
  const quoteTime = [
    ...(hotBoards.value.leader_boards || []),
    ...(hotBoards.value.industry_boards || []),
    ...(hotBoards.value.concept_boards || []),
  ].map((item) => item.quote_time).filter(Boolean).sort().pop()
  if (!quoteTime) return '外部热榜实时参考'
  return `新浪实时热榜 · ${formatHotBoardTime(quoteTime)}`
})

const summaryCards = computed(() => ([
  {
    label: '板块粗分',
    value: `${scanData.value.mainline_sectors?.length || 0}/${scanData.value.sub_mainline_sectors?.length || 0}/${scanData.value.follow_sectors?.length || 0}`,
    copy: `主线 / 次主线 / 跟风，${thresholdTagLabel.value}`
  },
  {
    label: '主线题材',
    value: themeLeaderSector.value?.sector_name || '暂无',
    copy: themeLeaderSector.value?.sector_summary_reason || themeLeaderSector.value?.sector_comment || '今天没有特别清晰的题材主线'
  },
  {
    label: '承接行业',
    value: industryLeaderSector.value?.sector_name || '暂无',
    copy: industryLeaderSector.value?.sector_summary_reason || industryLeaderSector.value?.sector_comment || '行业扩散还不够明确'
  },
  {
    label: '执行提示',
    value: primaryLeaderSector.value?.sector_action_hint || '只观察',
    copy: leaderFlowSummary.value
  },
]))

const tierCounts = computed(() => ({
  A: allSectors.value.filter((row) => row.sector_tier === 'A').length,
  B: allSectors.value.filter((row) => row.sector_tier === 'B').length,
  C: allSectors.value.filter((row) => row.sector_tier === 'C').length,
}))

const themeLeaderSector = computed(() => (
  leaderData.value?.theme_sector || scanData.value.theme_leaders?.[0] || null
))

const industryLeaderSector = computed(() => (
  leaderData.value?.industry_sector || scanData.value.industry_leaders?.[0] || null
))

const primaryLeaderSector = computed(() => (
  themeLeaderSector.value
  || industryLeaderSector.value
  || leaderData.value?.sector
  || scanData.value.mainline_sectors?.[0]
  || scanData.value.sub_mainline_sectors?.[0]
  || null
))

const modeTagLabel = computed(() => {
  const mode = scanData.value.sector_data_mode
  if (mode === 'hybrid') return '题材主线+行业承接'
  if (mode === 'limitup_industry_hybrid') return '涨停行业承接'
  if (mode === 'industry_only') return '行业承接口径'
  if (mode === 'realtime_hot_sector') return '盘中热度参考'
  if (mode === 'mock') return '模拟口径'
  if (mode === 'empty') return '空结果'
  return '扫描口径'
})

const modeTagType = computed(() => {
  const mode = scanData.value.sector_data_mode
  if (mode === 'hybrid') return 'success'
  if (mode === 'limitup_industry_hybrid') return 'warning'
  if (mode === 'industry_only') return 'warning'
  return 'info'
})

const thresholdTagLabel = computed(() => {
  const profile = scanData.value.threshold_profile
  if (profile === 'attack') return '进攻阈值'
  if (profile === 'defensive') return '防守阈值'
  if (profile === 'relaxed') return '放宽阈值'
  return '标准阈值'
})

const marketEnvTitle = computed(() => {
  if (!marketEnv.value) return '未加载'
  return `${marketEnv.value.market_env_tag}环境，综合分 ${Number(marketEnv.value.overall_score || 0).toFixed(1)}`
})

const sectorGroupingSummary = computed(() => (
  `A类 ${tierCounts.value.A} 个，B类 ${tierCounts.value.B} 个，C类 ${tierCounts.value.C} 个`
))

const themeLeaderSummary = computed(() => {
  const leaderStocks = leaderData.value?.theme_leader_stocks || []
  if (leaderLoading.value) return '风向标加载中'
  if (!leaderLoaded.value && themeLeaderSector.value) return '按需加载题材风向标'
  if (!themeLeaderSector.value) return '今日无明确题材主线'
  if (!leaderStocks.length) return themeLeaderSector.value?.sector_summary_reason || '题材方向已识别，暂未补齐风向标'
  return `风向标 ${leaderStocks.map((item) => item.stock_name).join(' / ')}`
})

const industryLeaderSummary = computed(() => {
  const leaderStocks = leaderData.value?.industry_leader_stocks || []
  if (leaderLoading.value) return '风向标加载中'
  if (!leaderLoaded.value && industryLeaderSector.value) return '按需加载行业风向标'
  if (!industryLeaderSector.value) return '今日无明确承接行业'
  if (!leaderStocks.length) return industryLeaderSector.value?.sector_summary_reason || '行业方向已识别，暂未补齐风向标'
  return `风向标 ${leaderStocks.map((item) => item.stock_name).join(' / ')}`
})

const leaderFlowSummary = computed(() => {
  if (themeLeaderSector.value && industryLeaderSector.value) {
    return `先盯 ${themeLeaderSector.value.sector_name} 的情绪强度，再看 ${industryLeaderSector.value.sector_name} 是否继续承接扩散。`
  }
  const sector = primaryLeaderSector.value
  if (!sector) return '暂无可执行主线'
  return sector.sector_summary_reason || sector.sector_comment || '暂无说明'
})

const leaderStocksBySector = computed(() => {
  const mapping = {}
  if (themeLeaderSector.value && (leaderData.value?.theme_leader_stocks || []).length) {
    mapping[sectorKey(themeLeaderSector.value)] = leaderData.value.theme_leader_stocks
  }
  if (industryLeaderSector.value && (leaderData.value?.industry_leader_stocks || []).length) {
    mapping[sectorKey(industryLeaderSector.value)] = leaderData.value.industry_leader_stocks
  }
  return mapping
})

const actionHeadline = computed(() => {
  if (themeLeaderSector.value && industryLeaderSector.value) {
    return `${themeLeaderSector.value.sector_name} 是主线题材，${industryLeaderSector.value.sector_name} 负责承接扩散`
  }
  if (themeLeaderSector.value) return `${themeLeaderSector.value.sector_name} 是当前最值得优先跟踪的主线题材`
  if (industryLeaderSector.value) return `${industryLeaderSector.value.sector_name} 是当前最清晰的承接行业`
  return '今天没有明确双主线，先看强度和承接'
})

const actionCopy = computed(() => {
  if (!themeLeaderSector.value && !industryLeaderSector.value) {
    return `${sectorGroupingSummary.value}。当前更适合保留弹性，先看市场环境和龙头反馈，不要过早押单一方向。`
  }
  if (themeLeaderSector.value && industryLeaderSector.value) {
    return `${themeLeaderSector.value.sector_summary_reason || themeLeaderSector.value.sector_comment || '题材方向更强'}。同时观察 ${industryLeaderSector.value.sector_name} 是否继续扩散，确认不是只有前排情绪在表演。`
  }
  return `${primaryLeaderSector.value.sector_summary_reason || primaryLeaderSector.value.sector_comment || '该方向当前更强'}。先盯龙头和中军是否继续联动，再决定是否从观察转执行。`
})

const sectorModeAlertVisible = computed(() => (
  scanData.value.sector_data_mode === 'industry_only' ||
  scanData.value.sector_data_mode === 'limitup_industry_hybrid'
))

const sectorModeAlertType = computed(() => (
  scanData.value.sector_data_mode === 'limitup_industry_hybrid' ? 'info' : 'warning'
))

const sectorModeAlertTitle = computed(() => {
  if (scanData.value.sector_data_mode === 'limitup_industry_hybrid') {
    return '题材聚合缺失，当前以涨停行业和行业均值识别承接方向；题材主线会单独留空，不再混成统一主线。'
  }
  const status = scanData.value.concept_data_status
  if (status === 'missing_theme') {
    return '涨停列表已返回当日数据，但未提供 theme 字段，当前只保留行业承接视图，不再把行业直接解释成题材主线。'
  }
  if (status === 'empty') {
    return '当日涨停列表为空，当前结果按行业均值扫描，并已自动切换到行业承接口径。'
  }
  if (status === 'missing_pct_chg') {
    return '涨停列表缺少涨跌幅字段，当前结果按行业均值扫描，并已自动切换到行业承接口径。'
  }
  if (status === 'no_token') {
    return '未配置 Tushare Token，当前结果按行业均值扫描，并已自动切换到行业承接口径。'
  }
  if (status === 'error') {
    return '题材聚合调用异常，当前结果按行业均值扫描，并已自动切换到行业承接口径。'
  }
  return '当天题材聚合未生成结果，当前结果按行业均值扫描，并已自动切换到行业承接口径。'
})

const sectorPanes = computed(() => ([
  {
    name: 'mainline',
    label: '主线候选',
    rows: scanData.value.mainline_sectors || [],
    count: scanData.value.mainline_sectors?.length || 0,
    empty: '今日无主线板块（市场偏弱）'
  },
  {
    name: 'sub',
    label: '次主线',
    rows: scanData.value.sub_mainline_sectors || [],
    count: scanData.value.sub_mainline_sectors?.length || 0,
    empty: '今日无次主线板块'
  },
  {
    name: 'follow',
    label: '跟风板块',
    rows: scanData.value.follow_sectors || [],
    count: scanData.value.follow_sectors?.length || 0,
    empty: '今日无跟风板块'
  },
]))

const tierTagType = (tier) => {
  if (tier === 'A') return 'danger'
  if (tier === 'B') return 'warning'
  return 'info'
}

const actionTagType = (action) => {
  if (action === '可执行') return 'success'
  if (action === '只观察') return 'warning'
  return 'info'
}

const fiveDimSummary = (row) => {
  const dim = row?.sector_dimension_scores
  if (!dim) return '-'
  return `联${dim.linkage_score} 资${dim.capital_score} 持${dim.continuity_score} 抗${dim.resilience_score} 交${dim.tradeability_score}`
}

const sectorActionCopy = (row) => {
  if (row.sector_action_hint === '可执行') {
    return '先盯龙头和中军是否继续共振，确认分时承接后，再把这个方向往三池和买点页继续下钻。'
  }
  if (row.sector_action_hint === '只观察') {
    return '先把它当风向，不急着直接执行，重点看板块联动是否继续扩大。'
  }
  return '先记录这个方向，但不要占用太多注意力。'
}

const formatHotBoardTime = (quoteTime) => {
  const text = String(quoteTime || '').trim()
  if (!text) return '未更新'
  const timePart = formatLocalTime(text)
  if (timePart && timePart !== '-') {
    return `更新 ${timePart.slice(0, 5)}`
  }
  return text
}

const sectorKey = (sector) => `${sector?.sector_name || ''}::${sector?.sector_source_type || ''}`

const leaderStocksForSector = (sector) => leaderStocksBySector.value[sectorKey(sector)] || []

const focusCardMeta = (row) => `${sourceTagLabel(row.sector_source_type)} · ${row.sector_summary_reason || row.sector_comment || '暂无结论'}`

const goToPage = (path, sector = null) => {
  if (typeof sector === 'string' && sector) {
    router.push({ path, query: { focus_sector: sector } })
    return
  }
  if (sector?.sector_name) {
    router.push({
      path,
      query: {
        focus_sector: sector.sector_name,
        focus_sector_source_type: sector.sector_source_type || '',
      }
    })
    return
  }
  router.push(path)
}

const openCheckup = (stock) => {
  checkupStock.value = {
    tsCode: stock.ts_code,
    stockName: stock.stock_name || stock.ts_code,
    defaultTarget: '观察型'
  }
  checkupVisible.value = true
}

const openTopStocks = (sector) => {
  activeTopSector.value = sector
  topStocksVisible.value = true
}

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
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

const applyScanData = (data) => {
  scanData.value = {
    ...createDefaultScanData(),
    ...(data || {})
  }
  if (!scanData.value.mainline_sectors?.length && !scanData.value.sub_mainline_sectors?.length) {
    activeTab.value = 'all'
  }
}

const loadSupportingData = async (tradeDate, version, options = {}) => {
  const failedModules = []
  const [marketRes, hotRes] = await Promise.allSettled([
    marketApi.getEnv(tradeDate, { timeout: SECTORS_REQUEST_TIMEOUT }),
    sectorApi.hot(tradeDate, 6, { timeout: SECTORS_REQUEST_TIMEOUT, refresh: Boolean(options.refresh) }),
  ])

  if (loadVersion.value !== version) {
    return
  }

  if (marketRes.status === 'fulfilled') {
    marketEnv.value = marketRes.value.data?.data || null
  } else if (!isAbortedRequest(marketRes.reason)) {
    failedModules.push('市场环境')
  }

  if (hotRes.status === 'fulfilled') {
    hotBoards.value = {
      trade_date: '',
      resolved_trade_date: '',
      data_source: '',
      leader_boards: [],
      industry_boards: [],
      concept_boards: [],
      ...(hotRes.value.data?.data || {})
    }
  } else if (!isAbortedRequest(hotRes.reason)) {
    failedModules.push('新浪热榜')
  }

  if (failedModules.length && !options.silent) {
    ElMessage.warning(`部分数据加载失败：${failedModules.join('、')}`)
  }
}

const loadLeaderData = async (options = {}) => {
  if ((!themeLeaderSector.value && !industryLeaderSector.value) || leaderLoading.value) {
    return
  }
  leaderLoading.value = true
  try {
    const tradeDate = scanData.value.resolved_trade_date || scanData.value.trade_date || getLocalDate()
    const res = await sectorApi.leader(tradeDate, {
      refresh: false,
      timeout: SECTORS_REQUEST_TIMEOUT,
      ...options
    })
    leaderData.value = res.data?.data || null
    leaderLoaded.value = true
  } catch (error) {
    if (!isAbortedRequest(error)) {
      ElMessage.warning('风向标加载失败')
    }
  } finally {
    leaderLoading.value = false
  }
}

const loadData = async (options = {}) => {
  const version = loadVersion.value + 1
  loadVersion.value = version
  const { silent = false, ...requestOptions } = options
  loading.value = true
  marketEnv.value = null
  leaderData.value = null
  hotBoards.value = {
    trade_date: '',
    resolved_trade_date: '',
    data_source: '',
    leader_boards: [],
    industry_boards: [],
    concept_boards: [],
  }
  leaderLoaded.value = false
  leaderLoading.value = false
  try {
    const tradeDate = getLocalDate()
    const scanRes = await sectorApi.scan(tradeDate, {
      ...requestOptions,
      timeout: SECTORS_REQUEST_TIMEOUT
    })
    if (loadVersion.value !== version) {
      return
    }
    applyScanData(scanRes.data?.data)
    const auxTradeDate = scanData.value.resolved_trade_date || scanData.value.trade_date || tradeDate
    loadSupportingData(auxTradeDate, version, { ...requestOptions, silent })
  } catch (error) {
    if (loadVersion.value !== version || isAbortedRequest(error)) {
      return
    }
    applyScanData(null)
    if (!silent) {
      ElMessage.error('加载失败')
    }
  } finally {
    if (loadVersion.value === version) {
      loading.value = false
    }
  }
}

onMounted(() => {
  loadData({ silent: true })
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-meta {
  display: flex;
  gap: 12px;
  align-items: center;
}
.trade-date {
  color: var(--color-text-sec);
  font-size: 13px;
}
.scan-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(280px, 1fr);
  gap: 16px;
  margin-bottom: 16px;
  padding: 20px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(255, 196, 64, 0.12), transparent 32%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.04));
  border: 1px solid rgba(255, 255, 255, 0.06);
}
.scan-kicker {
  font-size: 12px;
  color: var(--color-text-sec);
  margin-bottom: 10px;
}
.scan-hero-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 1.2rem;
  font-weight: 700;
  margin-bottom: 10px;
}
.scan-hero-copy {
  color: var(--color-text-sec);
  line-height: 1.7;
  margin-bottom: 14px;
}
.scan-hero-chips {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.scan-hero-actions {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}
.scan-hero-side {
  display: grid;
  gap: 12px;
}
.hero-side-card {
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--color-hover);
  border: 1px solid var(--color-border);
}
.hero-side-label {
  color: var(--color-text-sec);
  font-size: 12px;
  margin-bottom: 8px;
}
.hero-side-value {
  font-size: 1.05rem;
  font-weight: 700;
  margin-bottom: 6px;
}
.hero-side-copy {
  color: var(--color-text-sec);
  line-height: 1.6;
  font-size: 13px;
}
.total-text {
  color: var(--color-text-sec);
  font-size: 13px;
}
.scan-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.metric-tile {
  background: var(--color-hover);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: var(--shadow-card);
}
.metric-tile-label {
  color: var(--color-text-sec);
  font-size: 12px;
  margin-bottom: 8px;
}
.metric-tile-value {
  font-size: 1.05rem;
  font-weight: 700;
  margin-bottom: 8px;
}
.metric-tile-copy {
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}
.focus-board {
  margin-bottom: 16px;
  padding: 18px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(255,255,255,0.02), rgba(255,255,255,0.04));
  border: 1px solid rgba(255,255,255,0.06);
}
.focus-board-head {
  margin-bottom: 12px;
}
.focus-board-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 6px;
}
.focus-board-desc {
  color: var(--color-text-sec);
  font-size: 13px;
}
.focus-board-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.focus-card {
  padding: 14px;
  border-radius: 12px;
  background: var(--color-hover);
  border: 1px solid var(--color-border);
}
.focus-card-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.focus-card-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 6px;
}
.focus-card-meta {
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}
.focus-card-bottom {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--color-text-sec);
  font-size: 12px;
}
.hot-boards-panel {
  margin-bottom: 16px;
  padding: 18px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top left, rgba(61, 119, 255, 0.12), transparent 32%),
    linear-gradient(135deg, rgba(255,255,255,0.02), rgba(255,255,255,0.04));
  border: 1px solid rgba(255,255,255,0.06);
}
.hot-boards-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
}
.hot-boards-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 6px;
}
.hot-boards-desc,
.hot-boards-meta {
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}
.hot-boards-meta {
  white-space: nowrap;
}
.hot-boards-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.hot-board-card {
  padding: 14px;
  border-radius: 14px;
  background: var(--color-hover);
  border: 1px solid var(--color-border);
  display: grid;
  gap: 12px;
}
.hot-board-card-title {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 4px;
}
.hot-board-card-copy,
.hot-board-empty,
.hot-board-row-meta,
.hot-board-row-side span {
  color: var(--color-text-sec);
  font-size: 12px;
}
.hot-board-list {
  display: grid;
  gap: 8px;
}
.hot-board-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.05);
  background: rgba(255,255,255,0.02);
  color: inherit;
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease, background 0.2s ease;
}
.hot-board-row:hover {
  border-color: rgba(61, 119, 255, 0.28);
  background: rgba(61, 119, 255, 0.06);
  transform: translateY(-1px);
}
.hot-board-row-main,
.hot-board-row-side {
  display: grid;
  gap: 4px;
}
.hot-board-row-name {
  font-weight: 700;
}
.hot-board-row-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.hot-board-row-side {
  justify-items: end;
  text-align: right;
}
.sector-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.sector-card {
  background: var(--color-hover);
  border: 1px solid var(--color-border);
  border-radius: 14px;
  padding: 16px;
  display: grid;
  gap: 14px;
}
.sector-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.sector-card-title {
  font-size: 1.02rem;
  font-weight: 700;
  margin-bottom: 6px;
}
.sector-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--color-text-sec);
  font-size: 12px;
}
.sector-card-badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.sector-score-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.score-item {
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.04);
}
.score-label {
  display: block;
  color: var(--color-text-sec);
  font-size: 12px;
  margin-bottom: 6px;
}
.sector-dimension-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: var(--color-text-pri);
  font-size: 12px;
}
.sector-card-copy {
  display: grid;
  gap: 8px;
}
.sector-copy-title {
  font-size: 12px;
  color: var(--color-text-sec);
}
.sector-copy-text {
  line-height: 1.7;
}
.sector-leader-strip {
  display: grid;
  gap: 8px;
}
.sector-leader-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.sector-leader-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  font-size: 12px;
  color: var(--color-text-pri);
  cursor: pointer;
}
.sector-leader-chip:hover {
  border-color: rgba(255,255,255,0.14);
  background: rgba(255,255,255,0.05);
}
.sector-card-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.reason-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.dim-summary {
  color: var(--color-text-sec);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .scan-hero,
  .scan-metrics,
  .hot-boards-grid,
  .sector-card-grid,
  .focus-board-grid {
    grid-template-columns: 1fr;
  }

  .hot-boards-head {
    flex-direction: column;
  }

  .hot-boards-meta {
    white-space: normal;
  }
}
</style>
