<template>
  <div class="review-view">
    <el-card class="review-shell">
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>明日复盘决策</span>
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

          <section class="hero-panel">
            <div class="hero-copy">
              <div class="overview-kicker">明日结论</div>
              <div class="hero-title">{{ headlineTitle }}</div>
              <div class="hero-desc">{{ headlineDesc }}</div>
              <div class="hero-chip-row">
                <span :class="['hero-chip', `hero-chip-${confidenceMeta.tone}`]">
                  结论置信度：{{ confidenceMeta.label }}
                </span>
                <span class="hero-chip hero-chip-muted">{{ sortBasisText }}</span>
              </div>
            </div>

            <div class="hero-stats">
              <div class="overview-stats">
                <article v-for="item in overviewStats" :key="item.label" class="stat-card">
                  <div class="stat-label">{{ item.label }}</div>
                  <div class="stat-value">{{ item.value }}</div>
                </article>
              </div>
              <div class="stats-footnote">{{ overviewStatsFootnote }}</div>
            </div>
          </section>

          <section class="decision-grid">
            <article class="decision-card">
              <div class="section-mini">明日动作</div>
              <div class="decision-list">
                <div v-for="item in decisionItems" :key="item.label" class="decision-item">
                  <div class="decision-label">{{ item.label }}</div>
                  <div class="decision-text">{{ item.text }}</div>
                  <div class="decision-note">{{ item.note }}</div>
                </div>
              </div>
            </article>

            <article class="decision-card">
              <div class="section-mini">判断依据</div>
              <div class="signal-stack">
                <div class="signal-brief signal-brief-good">
                  <div class="signal-label">优先结构</div>
                  <div class="signal-title">{{ bestSignal?.shortLabel || '暂无明确优先组' }}</div>
                  <div class="signal-copy">{{ bestSignalSummary }}</div>
                  <div v-if="bestSignal" class="signal-metrics">
                    <span>样本 {{ bestSignal.count }}</span>
                    <span>已结算 {{ resolvedCount(bestSignal) }}</span>
                    <span>5日胜率 {{ formatPctValue(bestSignal.win_rate_5d, true) }}</span>
                  </div>
                </div>

                <div class="signal-brief signal-brief-bad">
                  <div class="signal-label">谨慎结构</div>
                  <div class="signal-title">{{ weakSignal?.shortLabel || '暂无明确谨慎组' }}</div>
                  <div class="signal-copy">{{ weakSignalSummary }}</div>
                  <div v-if="weakSignal" class="signal-metrics">
                    <span>样本 {{ weakSignal.count }}</span>
                    <span>已结算 {{ resolvedCount(weakSignal) }}</span>
                    <span>5日胜率 {{ formatPctValue(weakSignal.win_rate_5d, true) }}</span>
                  </div>
                </div>
              </div>
            </article>

            <article class="decision-card">
              <div class="section-mini">数据完整性</div>
              <div class="integrity-main">{{ integrityTitle }}</div>
              <div class="integrity-copy">{{ integrityDesc }}</div>
              <div class="integrity-list">
                <div v-for="item in integrityItems" :key="item.label" class="integrity-item">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </div>
              </div>
            </article>
          </section>

          <section class="compare-panel">
            <div class="section-head">
              <div>
                <div class="section-title">为什么是这个结论</div>
                <div class="section-desc">推荐不是只看收益均值，更看样本厚度、已结算比例和稳定性。</div>
              </div>
            </div>

            <el-table :data="compareRows" style="width: 100%">
              <el-table-column label="建议" width="96">
                <template #default="{ row }">
                  <span :class="['table-judgement', `table-judgement-${rowRecommendation(row).tone}`]">
                    {{ rowRecommendation(row).label }}
                  </span>
                </template>
              </el-table-column>

              <el-table-column label="结构" min-width="260">
                <template #default="{ row }">
                  <div class="structure-cell">
                    <div class="structure-main">
                      <strong>{{ row.snapshot_type_label }}</strong>
                      <span class="structure-divider">/</span>
                      <span>{{ row.candidate_bucket_tag || '未分层' }}</span>
                    </div>
                    <div class="structure-hint">{{ bucketHint(row.candidate_bucket_tag) }}</div>
                  </div>
                </template>
              </el-table-column>

              <el-table-column label="样本" width="100" prop="count" />

              <el-table-column label="已结算" width="100">
                <template #default="{ row }">
                  <span class="resolved-text">{{ resolvedCount(row) }}</span>
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

              <el-table-column label="稳定性" width="92">
                <template #default="{ row }">
                  <span :class="['stability-badge', `stability-badge-${stabilityMeta(row).tone}`]">
                    {{ stabilityMeta(row).label }}
                  </span>
                </template>
              </el-table-column>

              <el-table-column label="结论说明" min-width="280">
                <template #default="{ row }">
                  <div class="summary-copy">{{ rowReason(row) }}</div>
                </template>
              </el-table-column>
            </el-table>
          </section>

          <section class="evidence-panel">
            <div class="section-head">
              <div>
                <div class="section-title">结构证据</div>
                <div class="section-desc">证据层只按来源分组，避免把开仓、加仓和三池样本混着读。</div>
              </div>
              <div class="evidence-tip">先看首页结论，再回看来源和样本细节。</div>
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

          <section class="shortcut-panel">
            <div class="section-head">
              <div>
                <div class="section-title">相关来源</div>
                <div class="section-desc">首页先给结论，只有需要回到原始池子核对时，再从这里跳转。</div>
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
const sortBasisText = '排序依据：样本量 > 已结算比例 > 5日胜率 > 近期收益'
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

const resolvedCount = (row) => Number(row?.resolved_5d_count || row?.resolved_3d_count || row?.resolved_1d_count || 0)

const stabilityMeta = (row) => {
  const resolved = Number(row?.resolved_5d_count || 0)
  const winRate = Number(row?.win_rate_5d || 0)
  if (resolved >= 20 && winRate >= 80) return { label: '高', tone: 'high' }
  if (resolved >= 8 && winRate >= 60) return { label: '中', tone: 'mid' }
  if (resolved > 0) return { label: '低', tone: 'low' }
  return { label: '待补', tone: 'pending' }
}

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
  const candidates = actionableRows.value.filter((row) => row.shortLabel !== bestSignal.value?.shortLabel)
  if (!candidates.length) return null
  return [...candidates].sort((a, b) => Number(a.qualityScore || 0) - Number(b.qualityScore || 0))[0]
})

const watchSignal = computed(() => (
  displayRows.value.find((row) => (
    row.shortLabel !== bestSignal.value?.shortLabel
      && row.shortLabel !== weakSignal.value?.shortLabel
      && (
        row.snapshot_type === 'buy_available'
        || row.snapshot_type === 'buy_observe'
        || String(row.snapshot_type || '').startsWith('pool_')
      )
  )) || null
))

const totalResolved5d = computed(() => (
  displayRows.value.reduce((sum, row) => sum + Number(row.resolved_5d_count || 0), 0)
))

const pending5dCount = computed(() => Number(reviewData.value?.pending_5d_count || 0))

const resolvedCoverage = computed(() => {
  const resolved = totalResolved5d.value
  const pending = pending5dCount.value
  const total = resolved + pending
  return total > 0 ? resolved / total : 1
})

const resolvedCoverageText = computed(() => `${(resolvedCoverage.value * 100).toFixed(0)}%`)

const confidenceMeta = computed(() => {
  if (!bestSignal.value) {
    return {
      label: '低',
      tone: 'low',
      copy: '当前已结算样本偏少，先沿用原有规则，避免把小样本差异当成硬结论。'
    }
  }
  const bestResolved = resolvedCount(bestSignal.value)
  const qualityGap = actionableRows.value[1]
    ? Number(bestSignal.value.qualityScore || 0) - Number(actionableRows.value[1].qualityScore || 0)
    : Number(bestSignal.value.qualityScore || 0)

  if (bestResolved >= 20 && resolvedCoverage.value >= 0.55 && qualityGap >= 0.8) {
    return {
      label: '高',
      tone: 'high',
      copy: '已结算样本足够厚，优先结构和其他结构已经拉开明显差距，可作为强排序依据。'
    }
  }
  if (bestResolved >= 10 && resolvedCoverage.value >= 0.25) {
    return {
      label: '中',
      tone: 'mid',
      copy: '当前已有可用差异，但待补收益仍不少，更适合拿来排优先级，不适合下过硬结论。'
    }
  }
  return {
    label: '低',
    tone: 'low',
    copy: '优先结构已经出现，但成熟样本还不够厚，建议只做轻度排序参考。'
  }
})

const headlineTitle = computed(() => {
  if (bestSignal.value && weakSignal.value) {
    return `优先看：${bestSignal.value.shortLabel}；谨慎做：${weakSignal.value.shortLabel}`
  }
  if (bestSignal.value) return `优先看：${bestSignal.value.shortLabel}`
  return '当前样本仍在积累，先按原规则执行'
})

const headlineDesc = computed(() => {
  if (!actionableRows.value.length) {
    return '这页只在已结算样本足够时帮助排序，当前先继续积累样本，不直接替代盘中判断。'
  }
  return '这页只回答明天先看什么结构、谨慎什么结构，不替代盘中的触发确认和失效判断。'
})

const overviewStats = computed(() => ([
  { label: '观察交易日', value: reviewData.value?.trade_dates?.length || 0 },
  { label: '候选快照', value: reviewData.value?.snapshot_count || 0 },
  { label: '有效结构', value: actionableRows.value.length },
  { label: '已结算 / 待补', value: `${totalResolved5d.value} / ${pending5dCount.value}` }
]))

const overviewStatsFootnote = computed(() => '说明：待补收益按 1/3/5 日窗口统计，与快照总数不是同一统计口径。')

const bestSignalSummary = computed(() => {
  if (!bestSignal.value) return '当前没有形成足够稳定的优先组。'
  return '样本更厚，近期表现更稳，适合作为明日优先消耗注意力的结构。'
})

const weakSignalSummary = computed(() => {
  if (!weakSignal.value) return '当前没有形成明确需要主动降权的结构。'
  return '收益均值未必差，但适用环境更窄，盘中确认要求更高，不宜主动提优先级。'
})

const decisionItems = computed(() => ([
  {
    label: '优先看',
    text: bestSignal.value ? bestSignal.value.shortLabel : '维持原规则',
    note: bestSignal.value
      ? (bestSignal.value.candidate_bucket_tag === '强势确认'
        ? '早盘若继续表现强度，再进入重点确认；未到触发位前不抢先手。'
        : '先给更高关注度，再回到触发价和失效位做确认。')
      : '当前没有形成稳定优先组。'
  },
  {
    label: '继续观察',
    text: watchSignal.value ? watchSignal.value.shortLabel : '暂无明确观察候选',
    note: watchSignal.value
      ? (String(watchSignal.value.snapshot_type || '').startsWith('pool_')
        ? '更适合缩小候选范围，不直接替代执行判断。'
        : '先跟踪，不抢先手，等确认条件补齐后再升级。')
      : '没有额外需要单列观察的结构。'
  },
  {
    label: '谨慎做',
    text: weakSignal.value ? weakSignal.value.shortLabel : '暂无明确谨慎组',
    note: weakSignal.value
      ? (weakSignal.value.candidate_bucket_tag === '趋势回踩'
        ? '除非盘中走出明显转强，否则不主动提升优先级。'
        : '短期性价比偏弱，只有在盘中特别强时才考虑升级。')
      : '当前没有形成必须主动降权的结构。'
  }
]))

const integrityTitle = computed(() => `5日窗口已结算 ${totalResolved5d.value} 条，待补 ${pending5dCount.value} 条`)

const integrityDesc = computed(() => confidenceMeta.value.copy)

const integrityItems = computed(() => ([
  { label: '已结算占比', value: resolvedCoverageText.value },
  { label: '有效结构数', value: actionableRows.value.length },
  { label: '候选快照', value: reviewData.value?.snapshot_count || 0 }
]))

const compareRows = computed(() => {
  if (actionableRows.value.length) return actionableRows.value
  return displayRows.value.slice(0, 5)
})

const rowReason = (row) => {
  if (bestSignal.value?.shortLabel === row.shortLabel) {
    return '样本更厚，近期表现更稳，适合作为明日优先消耗注意力的结构。'
  }
  if (weakSignal.value?.shortLabel === row.shortLabel) {
    return '收益均值不差，但适用环境更窄，需等盘中更强确认，不宜主动提优先级。'
  }
  if (Number(row.resolved_5d_count || 0) <= 0) {
    return '5日窗口仍在补数，当前不作为首页主判断依据。'
  }
  if (String(row.snapshot_type || '').startsWith('pool_')) {
    return '更适合缩小候选范围，不直接替代执行判断。'
  }
  if (row.snapshot_type === 'buy_observe') {
    return '结构可跟踪，但确认条件还不够，适合继续观察。'
  }
  return '已进入对比池，可结合盘中强弱决定是否升级。'
}

const rowRecommendation = (row) => {
  if (bestSignal.value?.shortLabel === row.shortLabel) return { label: '优先看', tone: 'do' }
  if (weakSignal.value?.shortLabel === row.shortLabel) return { label: '谨慎做', tone: 'avoid' }
  if (Number(row.resolved_5d_count || 0) <= 0) return { label: '继续观察', tone: 'watch' }
  if (String(row.snapshot_type || '').startsWith('pool_') || row.snapshot_type === 'buy_observe') {
    return { label: '先观察', tone: 'watch' }
  }
  return { label: '对比看', tone: 'neutral' }
}

const reviewPendingTip = computed(() => {
  const pending1d = Number(reviewData.value?.pending_1d_count || 0)
  const pending3d = Number(reviewData.value?.pending_3d_count || 0)
  const pending5d = pending5dCount.value
  if (!pending1d && !pending3d && !pending5d) return ''
  return `数据完整性：1日待补 ${pending1d} 条，3日待补 ${pending3d} 条，5日待补 ${pending5d} 条，结论仍可能随补数变化。`
})

const hasPendingOutcomes = computed(() => {
  return Number(reviewData.value?.pending_1d_count || 0) > 0
    || Number(reviewData.value?.pending_3d_count || 0) > 0
    || pending5dCount.value > 0
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

.hero-panel {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 18px;
  margin-bottom: 18px;
}

.hero-copy,
.decision-card,
.compare-panel,
.shortcut-panel,
.evidence-panel {
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.04));
}

.hero-copy {
  display: grid;
  gap: 12px;
  padding: 24px;
  background:
    radial-gradient(circle at top right, rgba(255, 208, 107, 0.18), transparent 34%),
    radial-gradient(circle at bottom left, rgba(255, 129, 88, 0.12), transparent 30%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.06));
}

.overview-kicker,
.section-mini,
.decision-label,
.signal-label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.hero-title {
  font-size: 30px;
  line-height: 1.3;
  font-weight: 800;
  color: var(--color-text-pri);
}

.hero-desc {
  max-width: 48ch;
  color: var(--color-text-main);
  line-height: 1.65;
}

.hero-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-chip {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.hero-chip-high {
  background: rgba(84, 210, 164, 0.12);
  color: #76efc2;
}

.hero-chip-mid {
  background: rgba(255, 196, 64, 0.12);
  color: #ffd277;
}

.hero-chip-low {
  background: rgba(255, 120, 120, 0.12);
  color: #ff9b9b;
}

.hero-chip-muted {
  background: rgba(17, 24, 39, 0.26);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--color-text-sec);
  font-weight: 500;
}

.hero-stats {
  display: grid;
  gap: 12px;
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

.stats-footnote {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--color-text-sec);
  font-size: 12px;
  line-height: 1.6;
}

.decision-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.decision-card {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.decision-list,
.signal-stack,
.integrity-list {
  display: grid;
  gap: 12px;
}

.decision-item,
.signal-brief,
.integrity-item {
  padding: 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
}

.decision-text,
.signal-title,
.integrity-main {
  margin-top: 6px;
  font-size: 20px;
  line-height: 1.35;
  font-weight: 800;
  color: var(--color-text-pri);
}

.decision-note,
.signal-copy,
.integrity-copy,
.summary-copy {
  margin-top: 6px;
  color: var(--color-text-main);
  line-height: 1.6;
}

.signal-brief-good {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.12);
}

.signal-brief-bad {
  box-shadow: inset 0 0 0 1px rgba(255, 120, 120, 0.12);
}

.signal-metrics {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
  color: var(--color-text-sec);
  font-size: 12px;
}

.integrity-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.integrity-item span {
  color: var(--color-text-sec);
  font-size: 13px;
}

.integrity-item strong,
.resolved-text {
  color: var(--color-text-pri);
  font-weight: 800;
}

.compare-panel,
.shortcut-panel,
.evidence-panel {
  margin-bottom: 18px;
  padding: 18px;
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

.shortcut-chip-row,
.structure-tags,
.group-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.shortcut-chip,
.structure-tag,
.group-summary-badge,
.evidence-tip,
.stability-badge {
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 11px;
}

.shortcut-chip,
.structure-tag,
.evidence-tip {
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-sec);
}

.evidence-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}

.group-summary {
  align-items: center;
  margin-bottom: 12px;
}

.group-summary-badge {
  background: rgba(255, 208, 107, 0.14);
  color: var(--color-text-pri);
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

.stability-badge-high {
  background: rgba(84, 210, 164, 0.12);
  color: #76efc2;
}

.stability-badge-mid {
  background: rgba(255, 196, 64, 0.12);
  color: #ffd277;
}

.stability-badge-low {
  background: rgba(255, 120, 120, 0.12);
  color: #ff9b9b;
}

.stability-badge-pending {
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-text-sec);
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
  .hero-panel,
  .decision-grid,
  .shortcut-grid {
    grid-template-columns: 1fr;
  }

  .hero-title {
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

  .decision-text,
  .signal-title,
  .integrity-main {
    font-size: 18px;
  }
}
</style>
