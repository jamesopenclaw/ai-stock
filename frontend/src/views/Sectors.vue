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
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="12" animated />
      <template v-else>
      <div class="summary-bar" v-if="scanData.total_sectors">
        <el-tag type="danger">主线 {{ scanData.mainline_sectors?.length ?? 0 }}</el-tag>
        <el-tag type="warning">次主线 {{ scanData.sub_mainline_sectors?.length ?? 0 }}</el-tag>
        <el-tag>跟风 {{ scanData.follow_sectors?.length ?? 0 }}</el-tag>
        <el-tag type="info">杂毛 {{ scanData.trash_sectors?.length ?? 0 }}</el-tag>
        <el-tag :type="modeTagType">{{ modeTagLabel }}</el-tag>
        <el-tag v-if="scanData.threshold_profile === 'relaxed'" type="warning">放宽阈值</el-tag>
        <span class="total-text">共 {{ scanData.total_sectors }} 个板块</span>
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

      <div v-if="scanData.total_sectors" class="flow-panel">
        <div class="flow-card">
          <div class="flow-label">Step 1 市场环境</div>
          <div class="flow-title">
            <el-tag :type="marketEnvTagType">{{ marketEnv?.market_env_tag || '未知' }}</el-tag>
            <span>{{ marketEnvTitle }}</span>
          </div>
          <div class="flow-desc">{{ marketEnv?.market_comment || '暂无市场环境说明' }}</div>
        </div>

        <div class="flow-card">
          <div class="flow-label">Step 2 板块粗分</div>
          <div class="flow-title">
            <el-tag :type="modeTagType">{{ modeTagLabel }}</el-tag>
            <span>{{ thresholdTagLabel }}</span>
          </div>
          <div class="flow-desc">{{ sectorGroupingSummary }}</div>
        </div>

        <div class="flow-card">
          <div class="flow-label">Step 3-4 主线结论</div>
          <div class="flow-title">
            <el-tag :type="tierTagType(primaryLeaderSector?.sector_tier)">{{ primaryLeaderSector?.sector_tier || '-' }}类</el-tag>
            <span>{{ primaryLeaderSector?.sector_name || '无明确主线' }}</span>
          </div>
          <div class="flow-desc">{{ primaryLeaderSector?.sector_summary_reason || primaryLeaderSector?.sector_comment || '暂无主线总结' }}</div>
          <div v-if="primaryLeaderSector?.sector_dimension_scores" class="dimension-grid">
            <span>联动 {{ primaryLeaderSector.sector_dimension_scores.linkage_score }}</span>
            <span>资金 {{ primaryLeaderSector.sector_dimension_scores.capital_score }}</span>
            <span>持续 {{ primaryLeaderSector.sector_dimension_scores.continuity_score }}</span>
            <span>抗分化 {{ primaryLeaderSector.sector_dimension_scores.resilience_score }}</span>
            <span>交易 {{ primaryLeaderSector.sector_dimension_scores.tradeability_score }}</span>
          </div>
        </div>

        <div class="flow-card">
          <div class="flow-label">Step 5 风向标与执行</div>
          <div class="flow-title">
            <el-tag :type="actionTagType(primaryLeaderSector?.sector_action_hint)">{{ primaryLeaderSector?.sector_action_hint || '只观察' }}</el-tag>
            <span>{{ leaderStockSummary }}</span>
          </div>
          <div class="flow-desc">{{ leaderFlowSummary }}</div>
          <div v-if="leaderData?.leader_stocks?.length" class="leader-stocks">
            <el-tag
              v-for="stock in leaderData.leader_stocks"
              :key="stock.ts_code"
              size="small"
              effect="plain"
              type="danger"
            >
              {{ stock.stock_name }} {{ stock.change_pct?.toFixed?.(2) ?? stock.change_pct }}%
            </el-tag>
          </div>
        </div>
      </div>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="主线板块" name="mainline">
          <el-empty v-if="!scanData.mainline_sectors?.length" description="今日无主线板块（市场偏弱）" />
          <el-table v-else :data="scanData.mainline_sectors" style="width: 100%">
            <el-table-column prop="sector_name" label="板块名称" width="140" />
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="sourceTagType(row.sector_source_type)">
                  {{ sourceTagLabel(row.sector_source_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="涨跌幅" width="100">
              <template #default="{ row }">
                <span :class="row.sector_change_pct > 0 ? 'text-red' : 'text-green'">
                  {{ row.sector_change_pct?.toFixed(2) }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="sector_mainline_tag" label="主线标签" width="90">
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
            <el-table-column prop="sector_continuity_tag" label="持续性" width="100" />
            <el-table-column prop="sector_tradeability_tag" label="交易性" width="90" />
            <el-table-column label="五维摘要" min-width="190">
              <template #default="{ row }">
                <span class="dim-summary">{{ fiveDimSummary(row) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="原因" min-width="220">
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

        <el-tab-pane label="次主线" name="sub">
          <el-empty v-if="!scanData.sub_mainline_sectors?.length" description="今日无次主线板块" />
          <el-table v-else :data="scanData.sub_mainline_sectors" style="width: 100%">
            <el-table-column prop="sector_name" label="板块名称" width="140" />
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="sourceTagType(row.sector_source_type)">
                  {{ sourceTagLabel(row.sector_source_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="涨跌幅" width="100">
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
            <el-table-column label="原因" min-width="220">
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

        <el-tab-pane label="跟风板块" name="follow">
          <el-empty v-if="!scanData.follow_sectors?.length" description="今日无跟风板块" />
          <el-table v-else :data="scanData.follow_sectors" style="width: 100%">
            <el-table-column prop="sector_name" label="板块名称" width="140" />
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="sourceTagType(row.sector_source_type)">
                  {{ sourceTagLabel(row.sector_source_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="涨跌幅" width="100">
              <template #default="{ row }">
                <span :class="row.sector_change_pct > 0 ? 'text-red' : 'text-green'">
                  {{ row.sector_change_pct?.toFixed(2) }}%
                </span>
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
            <el-table-column label="原因" min-width="220">
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
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { sectorApi, marketApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const activeTab = ref('mainline')
const marketEnv = ref(null)
const leaderData = ref(null)
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

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const loadData = async () => {
  loading.value = true
  try {
    const tradeDate = getLocalDate()
    const [scanRes, marketRes, leaderRes] = await Promise.all([
      sectorApi.scan(tradeDate),
      marketApi.getEnv(tradeDate),
      sectorApi.leader(tradeDate)
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
.summary-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.total-text {
  color: var(--color-text-sec);
  font-size: 13px;
}
.flow-panel {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.flow-card {
  background: var(--color-hover);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 14px 16px;
  box-shadow: var(--shadow-card);
}
.flow-label {
  color: var(--color-text-sec);
  font-size: 12px;
  margin-bottom: 8px;
}
.flow-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
}
.flow-desc {
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}
.dimension-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 10px;
  color: var(--color-text-pri);
  font-size: 12px;
}
.leader-stocks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
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
</style>
