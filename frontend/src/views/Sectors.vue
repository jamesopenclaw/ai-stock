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
            <el-button type="primary" @click="goToPage('/pools', primaryLeaderSector?.sector_name)">去三池分类</el-button>
            <el-button @click="goToPage('/buy', primaryLeaderSector?.sector_name)">去买点分析</el-button>
          </div>
        </div>
        <div class="scan-hero-side">
          <div class="hero-side-card">
            <div class="hero-side-label">市场环境</div>
            <div class="hero-side-value">{{ marketEnv?.market_env_tag || '未知' }}</div>
            <div class="hero-side-copy">{{ marketEnvTitle }}</div>
          </div>
          <div class="hero-side-card">
            <div class="hero-side-label">风向板块</div>
            <div class="hero-side-value">{{ primaryLeaderSector?.sector_name || '暂无' }}</div>
            <div class="hero-side-copy">{{ leaderStockSummary }}</div>
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

      <div v-if="focusRows.length" class="focus-board">
        <div class="focus-board-head">
          <div>
            <div class="focus-board-title">今日焦点板块</div>
            <div class="focus-board-desc">先把最值得盯的方向排出来，再决定要不要去三池和买点页细看。</div>
          </div>
        </div>
        <div class="focus-board-grid">
          <article v-for="row in focusRows" :key="`focus-${row.sector_name}`" class="focus-card">
            <div class="focus-card-top">
              <div>
                <div class="focus-card-title">{{ row.sector_name }}</div>
                <div class="focus-card-meta">{{ row.sector_summary_reason || row.sector_comment || '暂无结论' }}</div>
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

              <div v-if="leaderStocksBySector[row.sector_name]?.length" class="sector-leader-strip">
                <span class="sector-copy-title">风向标个股</span>
                <div class="sector-leader-list">
                  <button
                    v-for="stock in leaderStocksBySector[row.sector_name]"
                    :key="`${row.sector_name}-${stock.ts_code}`"
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
                <el-button type="primary" link size="small" @click="goToPage('/pools', row.sector_name)">去三池看这个方向</el-button>
                <el-button type="primary" link size="small" @click="goToPage('/buy', row.sector_name)">去买点找执行位</el-button>
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
    :trade-date="scanData.resolved_trade_date || scanData.trade_date"
  />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { sectorApi, marketApi } from '../api'
import { ElMessage } from 'element-plus'
import StockCheckupDrawer from '../components/StockCheckupDrawer.vue'

const loading = ref(false)
const activeTab = ref('mainline')
const marketEnv = ref(null)
const leaderData = ref(null)
const router = useRouter()
const checkupVisible = ref(false)
const checkupStock = ref({ tsCode: '', stockName: '', defaultTarget: '观察型' })
const scanData = ref({
  trade_date: '',
  resolved_trade_date: '',
  sector_data_mode: '',
  concept_data_status: '',
  concept_data_message: '',
  threshold_profile: '',
  mainline_sectors: [],
  sub_mainline_sectors: [],
  follow_sectors: [],
  trash_sectors: [],
  total_sectors: 0
})

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
    ...(scanData.value.mainline_sectors || []).slice(0, 2),
    ...(scanData.value.sub_mainline_sectors || []).slice(0, 2),
  ].slice(0, 4)
))

const summaryCards = computed(() => ([
  {
    label: '板块粗分',
    value: `${scanData.value.mainline_sectors?.length || 0}/${scanData.value.sub_mainline_sectors?.length || 0}/${scanData.value.follow_sectors?.length || 0}`,
    copy: `主线 / 次主线 / 跟风，${thresholdTagLabel.value}`
  },
  {
    label: '主线结论',
    value: primaryLeaderSector.value?.sector_name || '暂无',
    copy: primaryLeaderSector.value?.sector_summary_reason || primaryLeaderSector.value?.sector_comment || '今天没有特别清晰的主线'
  },
  {
    label: '风向标',
    value: leaderData.value?.leader_stocks?.[0]?.stock_name || '暂无',
    copy: leaderStockSummary.value
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

const primaryLeaderSector = computed(() => {
  return leaderData.value?.sector || scanData.value.mainline_sectors?.[0] || scanData.value.sub_mainline_sectors?.[0] || null
})

const modeTagLabel = computed(() => {
  const mode = scanData.value.sector_data_mode
  if (mode === 'hybrid') return '题材+行业'
  if (mode === 'limitup_industry_hybrid') return '涨停行业+行业'
  if (mode === 'industry_only') return '行业口径'
  if (mode === 'mock') return '模拟口径'
  if (mode === 'empty') return '空结果'
  return '板块口径'
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

const leaderStockSummary = computed(() => {
  const leaderStocks = leaderData.value?.leader_stocks || []
  if (!leaderStocks.length) return '暂无风向标'
  return `风向标 ${leaderStocks.map((item) => item.stock_name).join(' / ')}`
})

const leaderFlowSummary = computed(() => {
  const sector = primaryLeaderSector.value
  if (!sector) return '暂无可执行主线'
  return sector.sector_summary_reason || sector.sector_comment || '暂无说明'
})

const leaderStocksBySector = computed(() => {
  const sectorName = primaryLeaderSector.value?.sector_name
  const stocks = leaderData.value?.leader_stocks || []
  if (!sectorName || !stocks.length) return {}
  return {
    [sectorName]: stocks
  }
})

const actionHeadline = computed(() => {
  if (!primaryLeaderSector.value) return '今天没有明确主线，先看强度和承接'
  return `${primaryLeaderSector.value.sector_name} 是当前最值得优先跟踪的方向`
})

const actionCopy = computed(() => {
  if (!primaryLeaderSector.value) {
    return `${sectorGroupingSummary.value}。当前更适合保留弹性，先看市场环境和龙头反馈，不要过早押单一方向。`
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
    return '涨停列表未提供 theme 字段，当前已改为按涨停行业聚合，并补充行业均值扫描结果。'
  }
  const status = scanData.value.concept_data_status
  if (status === 'missing_theme') {
    return '涨停列表已返回当日数据，但未提供 theme 字段，当前已退回行业口径并自动放宽阈值。'
  }
  if (status === 'empty') {
    return '当日涨停列表为空，当前结果按行业均值扫描，并已自动切换到放宽阈值。'
  }
  if (status === 'missing_pct_chg') {
    return '涨停列表缺少涨跌幅字段，当前结果按行业均值扫描，并已自动切换到放宽阈值。'
  }
  if (status === 'no_token') {
    return '未配置 Tushare Token，当前结果按行业均值扫描，并已自动切换到放宽阈值。'
  }
  if (status === 'error') {
    return '题材聚合调用异常，当前结果按行业均值扫描，并已自动切换到放宽阈值。'
  }
  return '当天题材聚合未生成结果，当前结果按行业均值扫描，并已自动切换到放宽阈值。'
})

const sectorPanes = computed(() => ([
  {
    name: 'mainline',
    label: '主线板块',
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

const goToPage = (path, sectorName = '') => {
  if (sectorName) {
    router.push({ path, query: { focus_sector: sectorName } })
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

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const loadData = async (options = {}) => {
  loading.value = true
  try {
    const tradeDate = getLocalDate()
    const [scanRes, marketRes, leaderRes] = await Promise.all([
      sectorApi.scan(tradeDate, options),
      marketApi.getEnv(tradeDate),
      sectorApi.leader(tradeDate, options)
    ])
    scanData.value = scanRes.data.data
    marketEnv.value = marketRes.data.data
    leaderData.value = leaderRes.data.data
    // 弱市时主线/次主线为空，自动切到全部行业 tab
    if (!scanData.value.mainline_sectors?.length && !scanData.value.sub_mainline_sectors?.length) {
      activeTab.value = 'all'
    }
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
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
  .sector-card-grid,
  .focus-board-grid {
    grid-template-columns: 1fr;
  }
}
</style>
