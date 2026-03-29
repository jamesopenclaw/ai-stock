<template>
  <div class="review-view">
    <el-card>
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
            <el-button @click="loadData" :loading="loading">刷新</el-button>
          </div>
        </div>
      </template>

      <el-skeleton v-if="loading && !reviewData" :rows="8" animated />
      <template v-else>
        <el-empty v-if="!reviewData?.bucket_stats?.length" description="暂无复盘快照" />
        <template v-else>
          <div v-if="reviewData?.stats_mode === 'pool'" class="mode-tip">
            当前展示的是三池快照统计；打开买点页或跑完整决策分析后，会逐步补齐买点复盘数据。
          </div>
          <div v-if="reviewPendingTip" class="mode-tip">
            {{ reviewPendingTip }}
          </div>

          <div class="summary-strip">
            <div class="summary-item">
              <div class="label">覆盖交易日</div>
              <div class="value">{{ reviewData.trade_dates?.length || 0 }}</div>
            </div>
            <div class="summary-item">
              <div class="label">快照总数</div>
              <div class="value">{{ reviewData.snapshot_count || 0 }}</div>
            </div>
            <div class="summary-item">
              <div class="label">当前最强</div>
              <div class="value value-compact">{{ bestSignal ? bestSignal.shortLabel : '-' }}</div>
            </div>
            <div class="summary-item">
              <div class="label">当前最弱</div>
              <div class="value value-compact">{{ weakSignal ? weakSignal.shortLabel : '-' }}</div>
            </div>
          </div>

          <div class="conclusion-grid">
            <section class="conclusion-card conclusion-card-strong">
              <div class="conclusion-kicker">最近最有效</div>
              <div class="conclusion-title">{{ bestSignal?.shortLabel || '暂无结论' }}</div>
              <div class="conclusion-copy">{{ bestSignalSummary }}</div>
              <div v-if="bestSignal" class="conclusion-metrics">
                <span>5日均值 {{ formatPctValue(bestSignal.avg_return_5d) }}</span>
                <span>5日胜率 {{ formatPctValue(bestSignal.win_rate_5d, true) }}</span>
                <span>样本 {{ bestSignal.count }}</span>
              </div>
            </section>

            <section class="conclusion-card conclusion-card-weak">
              <div class="conclusion-kicker">最近最弱</div>
              <div class="conclusion-title">{{ weakSignal?.shortLabel || '暂无结论' }}</div>
              <div class="conclusion-copy">{{ weakSignalSummary }}</div>
              <div v-if="weakSignal" class="conclusion-metrics">
                <span>5日均值 {{ formatPctValue(weakSignal.avg_return_5d) }}</span>
                <span>5日胜率 {{ formatPctValue(weakSignal.win_rate_5d, true) }}</span>
                <span>样本 {{ weakSignal.count }}</span>
              </div>
            </section>
          </div>

          <div class="action-board">
            <div class="action-board-title">明天怎么用这份复盘</div>
            <div class="action-board-grid">
              <div class="action-card action-card-do">
                <div class="action-label">优先看</div>
                <div class="action-text">{{ nextActionDo }}</div>
              </div>
              <div class="action-card action-card-watch">
                <div class="action-label">先观察</div>
                <div class="action-text">{{ nextActionWatch }}</div>
              </div>
              <div class="action-card action-card-avoid">
                <div class="action-label">暂时少做</div>
                <div class="action-text">{{ nextActionAvoid }}</div>
              </div>
            </div>
          </div>

          <div class="evidence-head">
            <div class="evidence-title">统计证据</div>
            <div class="evidence-desc">上面是结论，这里是支撑这些结论的原始统计。</div>
          </div>

          <el-table :data="displayRows" style="width: 100%">
            <el-table-column label="类型" width="100">
              <template #default="{ row }">
                {{ row.snapshot_type_label }}
              </template>
            </el-table-column>
            <el-table-column prop="candidate_bucket_tag" label="分层" width="120" />
            <el-table-column prop="count" label="出现次数" width="90" />
            <el-table-column prop="avg_return_1d" label="1日均值" width="90" />
            <el-table-column prop="win_rate_1d" label="1日胜率" width="90" />
            <el-table-column prop="avg_return_3d" label="3日均值" width="90" />
            <el-table-column prop="win_rate_3d" label="3日胜率" width="90" />
            <el-table-column prop="avg_return_5d" label="5日均值" width="90" />
            <el-table-column prop="win_rate_5d" label="5日胜率" width="90" />
          </el-table>
        </template>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { decisionApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const limitDays = ref(10)
const reviewData = ref(null)
const REVIEW_STATS_TIMEOUT = 90000

const SNAPSHOT_TYPE_LABELS = {
  buy_available: '可买',
  buy_observe: '观察',
  pool_account: '可参与池',
  pool_market: '观察池'
}

const snapshotTypeLabel = (value) => SNAPSHOT_TYPE_LABELS[value] || value || '-'
const rowLabel = (row) => `${snapshotTypeLabel(row.snapshot_type)} / ${row.candidate_bucket_tag || '未分层'}`

const formatPctValue = (value, appendPercent = false) => {
  const num = Number(value || 0)
  return `${num.toFixed(2)}${appendPercent ? '%' : ''}`
}

const displayRows = computed(() => (
  (reviewData.value?.bucket_stats || []).map((row) => ({
    ...row,
    snapshot_type_label: snapshotTypeLabel(row.snapshot_type),
    shortLabel: rowLabel(row),
    resolved_weight: Number(row.resolved_5d_count || row.resolved_3d_count || row.resolved_1d_count || 0),
    qualityScore:
      Number(row.avg_return_5d || 0) * 0.6 +
      Number(row.win_rate_5d || 0) * 0.04 +
      Number(row.avg_return_3d || 0) * 0.25 +
      Number(row.win_rate_3d || 0) * 0.015 +
      Number(row.count || 0) * 0.03
  }))
))

const actionableRows = computed(() => (
  displayRows.value
    .filter((row) => row.resolved_weight > 0 && Number(row.count || 0) >= 2)
    .sort((a, b) => Number(b.qualityScore || 0) - Number(a.qualityScore || 0))
))

const bestSignal = computed(() => actionableRows.value[0] || null)
const weakSignal = computed(() => {
  const candidates = [...actionableRows.value]
    .sort((a, b) => Number(a.qualityScore || 0) - Number(b.qualityScore || 0))
  return candidates[0] || null
})

const bestSignalSummary = computed(() => {
  if (!bestSignal.value) return '当前样本还不够，暂时无法得出稳定结论。'
  return `${bestSignal.value.shortLabel} 最近表现最好，说明这类信号在最近 ${reviewData.value?.trade_dates?.length || 0} 个交易日里更值得优先信任。`
})

const weakSignalSummary = computed(() => {
  if (!weakSignal.value) return '当前样本还不够，暂时无法得出稳定结论。'
  return `${weakSignal.value.shortLabel} 最近性价比较弱，说明这类信号短期内更容易跑输预期，应该降权处理。`
})

const nextActionDo = computed(() => {
  if (!bestSignal.value) return '先按原有规则做，不额外放大任何一类信号。'
  return `优先看 ${bestSignal.value.shortLabel}，同等条件下先给这类信号更高关注度。`
})

const nextActionWatch = computed(() => {
  const watchRow = actionableRows.value.find((row) => row.snapshot_type === 'buy_observe' || row.snapshot_type === 'pool_market')
  if (!watchRow) return '观察池和趋势池继续只当候选名单，不直接当执行票。'
  return `${watchRow.shortLabel} 更适合先盯盘和等确认，不要把“能观察”直接当成“能下手”。`
})

const nextActionAvoid = computed(() => {
  if (!weakSignal.value) return '没有明显需要全面回避的类型，但仍要控制节奏。'
  return `${weakSignal.value.shortLabel} 暂时少做，除非盘中确认特别强，否则不要主动提高仓位和优先级。`
})

const reviewPendingTip = computed(() => {
  const pending1d = Number(reviewData.value?.pending_1d_count || 0)
  const pending3d = Number(reviewData.value?.pending_3d_count || 0)
  const pending5d = Number(reviewData.value?.pending_5d_count || 0)
  if (!pending1d && !pending3d && !pending5d) return ''
  const breakdown = `当前待补：1日 ${pending1d} 条，3日 ${pending3d} 条，5日 ${pending5d} 条`
  if (reviewData.value?.refresh_in_progress) {
    return `历史收益正在后台补齐中，${breakdown}。刷新后会逐步显示真实均值和胜率。`
  }
  return `${breakdown}，因此部分均值和胜率暂时不完整。`
})

const loadData = async () => {
  loading.value = true
  try {
    const res = await decisionApi.reviewStats(limitDays.value, { timeout: REVIEW_STATS_TIMEOUT })
    reviewData.value = res.data.data
  } catch (error) {
    ElMessage.error('加载复盘统计失败')
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
}

.header-date {
  font-size: 13px;
  color: var(--color-text-sec);
}

.summary-strip {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

.mode-tip {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 196, 64, 0.08);
  border: 1px solid rgba(255, 196, 64, 0.16);
  color: var(--color-text-main);
  font-size: 13px;
}

.summary-item {
  background: var(--color-hover);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 12px 16px;
  min-width: 140px;
}

.summary-item .label {
  color: var(--color-text-sec);
  font-size: 13px;
}

.summary-item .value {
  color: var(--color-text-pri);
  font-size: 22px;
  font-weight: 700;
  margin-top: 6px;
}

.value-compact {
  font-size: 16px;
  line-height: 1.35;
}

.conclusion-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 18px;
}

.conclusion-card {
  padding: 18px;
  border-radius: 14px;
  border: 1px solid var(--color-border);
  background: var(--color-hover);
}

.conclusion-card-strong {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.08);
}

.conclusion-card-weak {
  box-shadow: inset 0 0 0 1px rgba(255, 120, 120, 0.08);
}

.conclusion-kicker {
  color: var(--color-text-sec);
  font-size: 12px;
  margin-bottom: 10px;
}

.conclusion-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-pri);
  margin-bottom: 10px;
}

.conclusion-copy {
  color: var(--color-text-main);
  line-height: 1.7;
}

.conclusion-metrics {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
  color: var(--color-text-sec);
  font-size: 13px;
}

.action-board {
  margin-bottom: 20px;
  padding: 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(255,255,255,0.02), rgba(255,255,255,0.04));
  border: 1px solid rgba(255,255,255,0.06);
}

.action-board-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 12px;
}

.action-board-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.action-card {
  padding: 14px;
  border-radius: 12px;
  border: 1px solid var(--color-border);
  background: rgba(255,255,255,0.02);
}

.action-card-do {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.08);
}

.action-card-watch {
  box-shadow: inset 0 0 0 1px rgba(255, 196, 64, 0.08);
}

.action-card-avoid {
  box-shadow: inset 0 0 0 1px rgba(255, 120, 120, 0.08);
}

.action-label {
  font-size: 12px;
  color: var(--color-text-sec);
  margin-bottom: 8px;
}

.action-text {
  color: var(--color-text-main);
  line-height: 1.7;
}

.evidence-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.evidence-title {
  font-size: 16px;
  font-weight: 700;
}

.evidence-desc {
  font-size: 13px;
  color: var(--color-text-sec);
}

@media (max-width: 960px) {
  .conclusion-grid,
  .action-board-grid {
    grid-template-columns: 1fr;
  }

  .summary-strip {
    flex-wrap: wrap;
  }
}
</style>
