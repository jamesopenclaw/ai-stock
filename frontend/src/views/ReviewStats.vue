<template>
  <div class="review-view">
    <el-card class="review-shell">
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>复盘统计</span>
            <span class="header-date">最近 {{ limitDays }} 个交易日</span>
          </div>
          <div class="header-actions">
            <el-select v-model="limitDays" size="small" style="width: 120px" @change="loadData">
              <el-option :value="5" label="最近5日" />
              <el-option :value="10" label="最近10日" />
              <el-option :value="20" label="最近20日" />
            </el-select>
            <el-button
              type="warning"
              plain
              @click="loadData({ refresh: true, refreshOutcomes: true, actionLabel: '补算收益' })"
              :loading="outcomeRefreshing"
              :disabled="loading || !hasPendingOutcomes"
            >
              补算收益
            </el-button>
            <el-button @click="loadData({ refresh: true })" :loading="loading">刷新</el-button>
          </div>
        </div>
      </template>

      <el-skeleton v-if="loading && !reviewData" :rows="8" animated />
      <template v-else>
        <el-empty v-if="!reviewData?.bucket_stats?.length" description="暂无复盘快照" />
        <template v-else>
          <div class="status-row">
            <div v-if="reviewData?.stats_mode === 'pool'" class="status-pill status-pill-warn">
              当前先展示三池统计，买点样本会在后续分析后补齐。
            </div>
            <div v-if="reviewPendingTip" class="status-pill status-pill-neutral">
              {{ reviewPendingTip }}
            </div>
          </div>

          <section class="overview-panel">
            <div class="overview-copy">
              <div class="overview-kicker">复盘结论</div>
              <div class="overview-title">{{ headlineTitle }}</div>
              <div class="overview-desc">{{ headlineDesc }}</div>
              <div class="overview-legend">类型 = 来源，分层 = 结构。先看动作，再看证据。</div>
            </div>

            <div class="overview-stats">
              <article v-for="item in overviewStats" :key="item.label" class="stat-card">
                <div class="stat-label">{{ item.label }}</div>
                <div class="stat-value">{{ item.value }}</div>
              </article>
            </div>
          </section>

          <section class="focus-grid">
            <article class="focus-card focus-card-good">
              <div class="focus-kicker">当前优先</div>
              <div class="focus-title">{{ bestSignal?.shortLabel || '暂无明确优先组' }}</div>
              <div class="focus-copy">{{ bestSignalSummary }}</div>
              <div v-if="bestSignal" class="focus-metrics">
                <span>5日均值 {{ formatPctValue(bestSignal.avg_return_5d) }}</span>
                <span>5日胜率 {{ formatPctValue(bestSignal.win_rate_5d, true) }}</span>
                <span>样本 {{ bestSignal.count }}</span>
              </div>
            </article>

            <article class="focus-card focus-card-bad">
              <div class="focus-kicker">当前降权</div>
              <div class="focus-title">{{ weakSignal?.shortLabel || '暂无明确降权组' }}</div>
              <div class="focus-copy">{{ weakSignalSummary }}</div>
              <div v-if="weakSignal" class="focus-metrics">
                <span>5日均值 {{ formatPctValue(weakSignal.avg_return_5d) }}</span>
                <span>5日胜率 {{ formatPctValue(weakSignal.win_rate_5d, true) }}</span>
                <span>样本 {{ weakSignal.count }}</span>
              </div>
            </article>

            <article class="focus-card focus-card-playbook">
              <div class="focus-kicker">明日动作</div>
              <div class="playbook-list">
                <div v-for="item in actionItems" :key="item.label" class="playbook-item">
                  <span class="playbook-label">{{ item.label }}</span>
                  <span class="playbook-text">{{ item.text }}</span>
                </div>
              </div>
            </article>
          </section>

          <section class="shortcut-panel">
            <div class="section-head">
              <div>
                <div class="section-title">来源捷径</div>
                <div class="section-desc">先确认这条结论来自三池、买点还是加仓，再回到源页面处理。</div>
              </div>
            </div>

            <div class="shortcut-grid">
              <article
                v-for="item in sourceGuideCards"
                :key="item.key"
                :class="['shortcut-card', `shortcut-card-${item.tone}`]"
              >
                <div class="shortcut-name">{{ item.name }}</div>
                <div class="shortcut-copy">{{ item.copy }}</div>
                <div class="shortcut-chip-row">
                  <span class="shortcut-chip">{{ item.useFor }}</span>
                  <span class="shortcut-chip">{{ item.hint }}</span>
                </div>
                <el-button size="small" @click="openSourceGroup(item.snapshotType)">
                  {{ item.actionText }}
                </el-button>
              </article>
            </div>
          </section>

          <section class="evidence-panel">
            <div class="section-head">
              <div>
                <div class="section-title">结构证据</div>
                <div class="section-desc">一次只看一组来源，避免把开仓、加仓和三池样本混着读。</div>
              </div>
              <div class="evidence-tip">先看建议，再看样本和 1/3/5 日表现。</div>
            </div>

            <el-tabs v-model="activeEvidenceGroup" class="evidence-tabs">
              <el-tab-pane
                v-for="group in evidenceGroups"
                :key="group.key"
                :label="`${group.tabLabel} · ${group.count}`"
                :name="group.key"
              >
                <div class="group-summary">
                  <span class="group-summary-badge">{{ group.bestLabel }}</span>
                  <span class="group-summary-desc">{{ group.desc }}</span>
                </div>

                <el-table :data="group.rows" style="width: 100%">
                  <el-table-column label="建议" width="92">
                    <template #default="{ row }">
                      <span :class="['table-judgement', `table-judgement-${rowRecommendation(row).tone}`]">
                        {{ rowRecommendation(row).label }}
                      </span>
                    </template>
                  </el-table-column>

                  <el-table-column label="结构" min-width="280">
                    <template #default="{ row }">
                      <div class="structure-cell">
                        <div class="structure-main">
                          <strong>{{ row.snapshot_type_label }}</strong>
                          <span class="structure-divider">/</span>
                          <span>{{ row.candidate_bucket_tag || '未分层' }}</span>
                        </div>
                        <div class="structure-hint">{{ bucketHint(row.candidate_bucket_tag) }}</div>
                        <div v-if="row.add_position_decision || row.add_position_scene" class="structure-tags">
                          <span v-if="row.add_position_decision" class="structure-tag">{{ row.add_position_decision }}</span>
                          <span v-if="row.add_position_scene" class="structure-tag">{{ row.add_position_scene }}</span>
                        </div>
                      </div>
                    </template>
                  </el-table-column>

                  <el-table-column label="样本" width="120">
                    <template #default="{ row }">
                      <div class="sample-cell">
                        <strong>{{ row.count }}</strong>
                        <span>已结算 {{ resolvedCount(row) }}</span>
                      </div>
                    </template>
                  </el-table-column>

                  <el-table-column label="收益" min-width="190">
                    <template #default="{ row }">
                      <div class="metric-stack">
                        <div v-for="item in metricItems(row, 'return')" :key="`${row.shortLabel}-${item.label}-return`" class="metric-line">
                          <span>{{ item.label }}</span>
                          <strong>{{ item.value }}</strong>
                        </div>
                      </div>
                    </template>
                  </el-table-column>

                  <el-table-column label="胜率" min-width="190">
                    <template #default="{ row }">
                      <div class="metric-stack">
                        <div v-for="item in metricItems(row, 'win')" :key="`${row.shortLabel}-${item.label}-win`" class="metric-line">
                          <span>{{ item.label }}</span>
                          <strong>{{ item.value }}</strong>
                        </div>
                      </div>
                    </template>
                  </el-table-column>

                  <el-table-column label="查看来源" width="110" fixed="right">
                    <template #default="{ row }">
                      <el-button link type="primary" size="small" @click="openSourcePage(row)">去源页面</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
            </el-tabs>
          </section>
        </template>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { decisionApi } from '../api'

const loading = ref(false)
const outcomeRefreshing = ref(false)
const limitDays = ref(10)
const reviewData = ref(null)
const activeEvidenceGroup = ref('open')
const REVIEW_STATS_TIMEOUT = 90000
const router = useRouter()

const SNAPSHOT_TYPE_LABELS = {
  buy_available: '买点-可买',
  buy_observe: '买点-观察',
  buy_add: '加仓候选',
  pool_account: '三池-可参与池',
  pool_market: '三池-观察池'
}

const sourceGuideCards = [
  {
    key: 'pool_market',
    snapshotType: 'pool_market',
    name: '三池观察池',
    copy: '先缩小范围，不直接执行。',
    useFor: '先盯方向',
    hint: '不替代买点',
    actionText: '查看三池',
    tone: 'market'
  },
  {
    key: 'pool_account',
    snapshotType: 'pool_account',
    name: '三池可参与池',
    copy: '账户允许参与，但还没到执行结论。',
    useFor: '看账户准入',
    hint: '不等于立刻买',
    actionText: '查看三池',
    tone: 'account'
  },
  {
    key: 'buy_observe',
    snapshotType: 'buy_observe',
    name: '买点观察',
    copy: '结构可跟踪，确认条件还不够。',
    useFor: '继续盯盘',
    hint: '先等确认',
    actionText: '查看买点',
    tone: 'watch'
  },
  {
    key: 'buy_available',
    snapshotType: 'buy_available',
    name: '买点可买',
    copy: '已经接近执行区，适合比较优先级。',
    useFor: '决定先做谁',
    hint: '仍看触发价',
    actionText: '查看买点',
    tone: 'buy'
  },
  {
    key: 'buy_add',
    snapshotType: 'buy_add',
    name: '加仓候选',
    copy: '只回答已有底仓后值不值得继续扩。',
    useFor: '单看加仓质量',
    hint: '不和开仓混读',
    actionText: '查看持仓',
    tone: 'account'
  }
]

const BUCKET_HINTS = {
  强势确认: '偏强结构，优先看确认质量。',
  趋势回踩: '更适合等回踩承接后再做。',
  异动预备: '先列入预备名单，继续等放量。',
  观察补充: '辅助观察，优先级通常更低。',
  未分层: '暂无稳定结构标签。'
}

const snapshotTypeLabel = (value, addDecision = '') => {
  if (value === 'buy_add') {
    return addDecision ? `加仓-${addDecision}` : SNAPSHOT_TYPE_LABELS.buy_add
  }
  return SNAPSHOT_TYPE_LABELS[value] || value || '-'
}

const rowLabel = (row) => `${snapshotTypeLabel(row.snapshot_type, row.add_position_decision)} / ${row.candidate_bucket_tag || '未分层'}`
const bucketHint = (value) => BUCKET_HINTS[value || '未分层'] || '同类结构对比用的标签。'

const formatPctValue = (value, appendPercent = false) => {
  const num = Number(value || 0)
  return `${num.toFixed(2)}${appendPercent ? '%' : ''}`
}

const metricItems = (row, type) => {
  const fields = [
    { label: '1日', resolved: 'resolved_1d_count', value: type === 'win' ? 'win_rate_1d' : 'avg_return_1d', suffix: type === 'win' },
    { label: '3日', resolved: 'resolved_3d_count', value: type === 'win' ? 'win_rate_3d' : 'avg_return_3d', suffix: type === 'win' },
    { label: '5日', resolved: 'resolved_5d_count', value: type === 'win' ? 'win_rate_5d' : 'avg_return_5d', suffix: type === 'win' }
  ]

  return fields.map((item) => ({
    label: item.label,
    value: Number(row[item.resolved] || 0) > 0 ? formatPctValue(row[item.value], item.suffix) : '--'
  }))
}

const resolvedCount = (row) => Number(row.resolved_5d_count || row.resolved_3d_count || row.resolved_1d_count || 0)

const rankedRows = (rows) => (
  rows
    .map((row) => ({
      ...row,
      snapshot_type_label: snapshotTypeLabel(row.snapshot_type, row.add_position_decision),
      shortLabel: rowLabel(row),
      resolved_weight: resolvedCount(row),
      qualityScore:
        Number(row.avg_return_5d || 0) * 0.6 +
        Number(row.win_rate_5d || 0) * 0.04 +
        Number(row.avg_return_3d || 0) * 0.25 +
        Number(row.win_rate_3d || 0) * 0.015 +
        Number(row.count || 0) * 0.03
    }))
    .sort((a, b) => Number(b.qualityScore || 0) - Number(a.qualityScore || 0))
)

const displayRows = computed(() => rankedRows(reviewData.value?.bucket_stats || []))

const actionableRows = computed(() => (
  displayRows.value.filter((row) => row.resolved_weight > 0 && Number(row.count || 0) >= 2)
))

const openRows = computed(() => displayRows.value.filter((row) => row.snapshot_type === 'buy_available' || row.snapshot_type === 'buy_observe'))
const addRows = computed(() => displayRows.value.filter((row) => row.snapshot_type === 'buy_add'))
const poolRows = computed(() => displayRows.value.filter((row) => String(row.snapshot_type || '').startsWith('pool_')))

const summarizeGroupBest = (rows, fallback) => (rows.length ? rows[0].shortLabel : fallback)

const evidenceGroups = computed(() => {
  const groups = []
  if (openRows.value.length) {
    groups.push({
      key: 'open',
      tabLabel: '开仓',
      title: '开仓证据',
      desc: '只看买点里的可买和观察，判断第一次出手该优先谁。',
      count: openRows.value.length,
      bestLabel: `当前最强：${summarizeGroupBest(openRows.value, '暂无')}`,
      rows: openRows.value
    })
  }
  if (addRows.value.length) {
    groups.push({
      key: 'add',
      tabLabel: '加仓',
      title: '加仓证据',
      desc: '只看已有底仓后的扩仓质量，不和开仓信号混排。',
      count: addRows.value.length,
      bestLabel: `当前最强：${summarizeGroupBest(addRows.value, '暂无')}`,
      rows: addRows.value
    })
  }
  if (poolRows.value.length) {
    groups.push({
      key: 'pool',
      tabLabel: '三池',
      title: '三池证据',
      desc: '只看观察池和可参与池，判断缩小范围这一步有没有价值。',
      count: poolRows.value.length,
      bestLabel: `当前最强：${summarizeGroupBest(poolRows.value, '暂无')}`,
      rows: poolRows.value
    })
  }
  return groups
})

watchEffect(() => {
  if (!evidenceGroups.value.length) return
  if (!evidenceGroups.value.some((group) => group.key === activeEvidenceGroup.value)) {
    activeEvidenceGroup.value = evidenceGroups.value[0].key
  }
})

const bestSignal = computed(() => actionableRows.value[0] || null)
const weakSignal = computed(() => {
  const candidates = [...actionableRows.value].sort((a, b) => Number(a.qualityScore || 0) - Number(b.qualityScore || 0))
  return candidates[0] || null
})
const watchSignal = computed(() => actionableRows.value.find((row) => row.snapshot_type === 'buy_observe' || row.snapshot_type === 'pool_market') || null)

const headlineTitle = computed(() => {
  if (bestSignal.value && weakSignal.value) {
    return `${bestSignal.value.shortLabel} 优先，${weakSignal.value.shortLabel} 降权`
  }
  if (bestSignal.value) return `当前优先看 ${bestSignal.value.shortLabel}`
  return '当前样本还在积累，先按原规则执行'
})

const headlineDesc = computed(() => {
  if (!actionableRows.value.length) {
    return '先积累更多已结算样本，再用这页去调结构优先级。'
  }
  return '这页只回答哪类结构最近更值得信，不直接替代盘中的触发确认。'
})

const overviewStats = computed(() => ([
  { label: '覆盖交易日', value: reviewData.value?.trade_dates?.length || 0 },
  { label: '快照总数', value: reviewData.value?.snapshot_count || 0 },
  { label: '有效结构', value: actionableRows.value.length },
  { label: '待补 5 日', value: reviewData.value?.pending_5d_count || 0 }
]))

const bestSignalSummary = computed(() => {
  if (!bestSignal.value) return '当前没有形成足够稳定的优先组。'
  return '同等条件下先给这类结构更高关注度，再回到触发价和失效位做确认。'
})

const weakSignalSummary = computed(() => {
  if (!weakSignal.value) return '当前没有形成明确需要降权的结构。'
  return '这类结构短期性价比偏弱，除非盘中特别强，否则不要主动提优先级。'
})

const actionItems = computed(() => ([
  {
    label: '优先看',
    text: bestSignal.value ? bestSignal.value.shortLabel : '维持原规则'
  },
  {
    label: '先观察',
    text: watchSignal.value ? watchSignal.value.shortLabel : '观察池继续只做候选'
  },
  {
    label: '暂少做',
    text: weakSignal.value ? weakSignal.value.shortLabel : '没有明显全面回避组'
  }
]))

const rowRecommendation = (row) => {
  if (bestSignal.value?.shortLabel === row.shortLabel) return { label: '优先看', tone: 'do' }
  if (weakSignal.value?.shortLabel === row.shortLabel) return { label: '少做', tone: 'avoid' }
  if (String(row.snapshot_type || '').startsWith('pool_') || row.snapshot_type === 'buy_observe') {
    return { label: '观察', tone: 'watch' }
  }
  return { label: '对比', tone: 'neutral' }
}

const reviewPendingTip = computed(() => {
  const pending1d = Number(reviewData.value?.pending_1d_count || 0)
  const pending3d = Number(reviewData.value?.pending_3d_count || 0)
  const pending5d = Number(reviewData.value?.pending_5d_count || 0)
  if (!pending1d && !pending3d && !pending5d) return ''
  return `待补收益：1日 ${pending1d} 条，3日 ${pending3d} 条，5日 ${pending5d} 条。`
})

const hasPendingOutcomes = computed(() => {
  return Number(reviewData.value?.pending_1d_count || 0) > 0
    || Number(reviewData.value?.pending_3d_count || 0) > 0
    || Number(reviewData.value?.pending_5d_count || 0) > 0
})

const loadData = async ({ refresh = false, refreshOutcomes = false, actionLabel = '' } = {}) => {
  loading.value = true
  if (refreshOutcomes) {
    outcomeRefreshing.value = true
  }
  try {
    const res = await decisionApi.reviewStats(limitDays.value, {
      timeout: REVIEW_STATS_TIMEOUT,
      refresh,
      refreshOutcomes
    })
    reviewData.value = res.data.data
    if (refreshOutcomes) {
      const refreshedCount = Number(reviewData.value?.refreshed_outcome_count || 0)
      if (refreshedCount > 0) {
        ElMessage.success(`${actionLabel || '补算收益'}完成，本次更新 ${refreshedCount} 条快照`)
      } else if (hasPendingOutcomes.value) {
        ElMessage.info(`${actionLabel || '补算收益'}已执行，当前暂无新增可补结果`)
      } else {
        ElMessage.success(`${actionLabel || '补算收益'}完成，当前历史收益已补齐`)
      }
    }
  } catch (error) {
    ElMessage.error(refreshOutcomes ? '补算收益失败' : '加载复盘统计失败')
  } finally {
    loading.value = false
    outcomeRefreshing.value = false
  }
}

const openSourcePage = (row) => {
  const snapshotType = String(row?.snapshot_type || '')
  const targetPath = snapshotType === 'buy_add' ? '/sell' : snapshotType.startsWith('buy_') ? '/buy' : '/pools'
  const query = {}
  if (row?.candidate_bucket_tag) {
    query.review_bucket = row.candidate_bucket_tag
  }
  if (row?.snapshot_type) {
    query.review_source = row.snapshot_type
  }
  router.push({ path: targetPath, query })
}

const openSourceGroup = (snapshotType) => {
  openSourcePage({ snapshot_type: snapshotType })
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.review-shell {
  overflow: hidden;
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

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.header-date {
  font-size: 13px;
  color: var(--color-text-sec);
}

.status-row {
  display: grid;
  gap: 10px;
  margin-bottom: 16px;
}

.status-pill {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
}

.status-pill-warn {
  background: rgba(255, 196, 64, 0.10);
  border: 1px solid rgba(255, 196, 64, 0.20);
  color: var(--color-text-main);
}

.status-pill-neutral {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--color-text-sec);
}

.overview-panel {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 18px;
  margin-bottom: 18px;
}

.overview-copy {
  display: grid;
  gap: 10px;
  padding: 24px;
  border-radius: 20px;
  background:
    radial-gradient(circle at top right, rgba(255, 208, 107, 0.18), transparent 34%),
    radial-gradient(circle at bottom left, rgba(255, 129, 88, 0.12), transparent 30%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.06));
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.overview-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.overview-title {
  font-size: 30px;
  line-height: 1.25;
  font-weight: 800;
  color: var(--color-text-pri);
}

.overview-desc {
  color: var(--color-text-main);
  line-height: 1.65;
  max-width: 48ch;
}

.overview-legend {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(17, 24, 39, 0.26);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--color-text-sec);
  font-size: 12px;
}

.overview-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.stat-card {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid var(--color-border);
  background: var(--color-hover);
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.stat-value {
  margin-top: 8px;
  font-size: 28px;
  line-height: 1.1;
  font-weight: 800;
  color: var(--color-text-pri);
}

.focus-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.focus-card {
  display: grid;
  gap: 10px;
  padding: 18px;
  border-radius: 16px;
  border: 1px solid var(--color-border);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.05));
}

.focus-card-good {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.12);
}

.focus-card-bad {
  box-shadow: inset 0 0 0 1px rgba(255, 120, 120, 0.12);
}

.focus-card-playbook {
  box-shadow: inset 0 0 0 1px rgba(255, 208, 107, 0.16);
}

.focus-kicker {
  font-size: 12px;
  letter-spacing: 0.06em;
  color: var(--color-text-sec);
}

.focus-title {
  font-size: 20px;
  line-height: 1.35;
  font-weight: 800;
  color: var(--color-text-pri);
}

.focus-copy {
  color: var(--color-text-main);
  line-height: 1.6;
}

.focus-metrics {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--color-text-sec);
  font-size: 12px;
}

.playbook-list {
  display: grid;
  gap: 10px;
}

.playbook-item {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
}

.playbook-label {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.playbook-text {
  color: var(--color-text-pri);
  line-height: 1.45;
  font-weight: 700;
}

.shortcut-panel,
.evidence-panel {
  margin-bottom: 18px;
  padding: 18px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.04));
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.section-title {
  font-size: 16px;
  font-weight: 800;
  color: var(--color-text-pri);
}

.section-desc {
  margin-top: 4px;
  color: var(--color-text-sec);
  font-size: 13px;
}

.shortcut-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.shortcut-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid var(--color-border);
  background: rgba(255, 255, 255, 0.03);
}

.shortcut-card-market {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.10);
}

.shortcut-card-account {
  box-shadow: inset 0 0 0 1px rgba(88, 176, 255, 0.12);
}

.shortcut-card-watch {
  box-shadow: inset 0 0 0 1px rgba(255, 196, 64, 0.10);
}

.shortcut-card-buy {
  box-shadow: inset 0 0 0 1px rgba(255, 120, 120, 0.10);
}

.shortcut-name {
  font-size: 17px;
  line-height: 1.35;
  font-weight: 800;
  color: var(--color-text-pri);
}

.shortcut-copy {
  color: var(--color-text-main);
  font-size: 13px;
  line-height: 1.55;
}

.shortcut-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.shortcut-chip {
  padding: 5px 9px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-sec);
  font-size: 11px;
}

.evidence-tip {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-sec);
  font-size: 12px;
}

.evidence-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}

.group-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}

.group-summary-badge {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 208, 107, 0.14);
  color: var(--color-text-pri);
  font-size: 12px;
  font-weight: 700;
}

.group-summary-desc {
  color: var(--color-text-sec);
  font-size: 13px;
}

.table-judgement {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 52px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.table-judgement-do {
  color: #76efc2;
  background: rgba(84, 210, 164, 0.12);
}

.table-judgement-watch {
  color: #ffd277;
  background: rgba(255, 196, 64, 0.12);
}

.table-judgement-avoid {
  color: #ff9b9b;
  background: rgba(255, 120, 120, 0.12);
}

.table-judgement-neutral {
  color: var(--color-text-sec);
  background: rgba(255, 255, 255, 0.06);
}

.structure-cell {
  display: grid;
  gap: 6px;
}

.structure-main {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: var(--color-text-pri);
}

.structure-divider {
  color: var(--color-text-sec);
}

.structure-hint {
  color: var(--color-text-sec);
  font-size: 12px;
  line-height: 1.5;
}

.structure-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.structure-tag {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-sec);
  font-size: 11px;
}

.sample-cell {
  display: grid;
  gap: 4px;
}

.sample-cell strong {
  color: var(--color-text-pri);
}

.sample-cell span {
  color: var(--color-text-sec);
  font-size: 12px;
}

.metric-stack {
  display: grid;
  gap: 6px;
}

.metric-line {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  font-size: 12px;
}

.metric-line span {
  color: var(--color-text-sec);
}

.metric-line strong {
  color: var(--color-text-pri);
}

@media (max-width: 1280px) {
  .overview-panel,
  .focus-grid,
  .shortcut-grid {
    grid-template-columns: 1fr;
  }

  .overview-title {
    font-size: 26px;
  }
}

@media (max-width: 768px) {
  .overview-stats {
    grid-template-columns: 1fr 1fr;
  }

  .card-header,
  .card-header-title,
  .header-actions {
    align-items: stretch;
  }

  .header-actions {
    width: 100%;
  }
}
</style>
