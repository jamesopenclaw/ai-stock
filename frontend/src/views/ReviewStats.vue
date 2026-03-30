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
            <el-button @click="loadData({ refresh: true })" :loading="loading">刷新</el-button>
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

          <section class="review-hero">
            <div class="hero-main">
              <div class="hero-copy">
                <div class="hero-kicker">过去 {{ limitDays }} 个交易日的复盘结论</div>
                <div class="hero-title">先记住最有效和最弱的结构，再决定明天把注意力放在哪。</div>
                <div class="hero-desc">这页不是告诉你“哪只股票要买”，而是告诉你“哪类结构最近更值得信、哪类结构该降权”。</div>
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
            </div>

            <aside class="hero-side">
              <div class="summary-grid">
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
            </aside>
          </section>

          <section class="radar-board">
            <div class="radar-board-title">这轮结构优先级</div>
            <div class="radar-grid">
              <div class="radar-panel radar-panel-do">
                <div class="radar-label">优先样本</div>
                <div class="radar-list">
                  <article v-for="row in priorityRows" :key="`best-${row.shortLabel}`" class="radar-item">
                    <strong>{{ row.shortLabel }}</strong>
                    <span>5日均值 {{ formatPctValue(row.avg_return_5d) }} · 胜率 {{ formatPctValue(row.win_rate_5d, true) }}</span>
                  </article>
                </div>
              </div>
              <div class="radar-panel radar-panel-avoid">
                <div class="radar-label">降权样本</div>
                <div class="radar-list">
                  <article v-for="row in cautionRows" :key="`weak-${row.shortLabel}`" class="radar-item">
                    <strong>{{ row.shortLabel }}</strong>
                    <span>5日均值 {{ formatPctValue(row.avg_return_5d) }} · 胜率 {{ formatPctValue(row.win_rate_5d, true) }}</span>
                  </article>
                </div>
              </div>
            </div>
          </section>

          <div class="source-guide">
            <div class="source-guide-head">
              <div>
                <div class="source-guide-title">这些类型到底来自哪里</div>
                <div class="source-guide-desc">先看来源，再看分层。三池负责缩小范围，买点负责判断能不能下手。</div>
              </div>
            </div>
            <div class="source-guide-grid">
              <article
                v-for="item in sourceGuideCards"
                :key="item.key"
                :class="['source-guide-card', `source-guide-card-${item.tone}`]"
              >
                <div class="source-guide-kicker">{{ item.kicker }}</div>
                <div class="source-guide-name">{{ item.name }}</div>
                <div class="source-guide-copy">{{ item.copy }}</div>
                <div class="source-guide-chip-row">
                  <span class="source-guide-chip">{{ item.useFor }}</span>
                  <span class="source-guide-chip">{{ item.hint }}</span>
                </div>
                <div class="source-guide-actions">
                  <el-button size="small" @click="openSourceGroup(item.snapshotType)">{{ item.actionText }}</el-button>
                </div>
              </article>
            </div>
          </div>

          <div class="evidence-head">
            <div>
              <div class="evidence-title">统计证据</div>
              <div class="evidence-desc">每一行都表示“某个来源里的某种结构”，再看它后续 1/3/5 日的表现。</div>
            </div>
            <div class="evidence-tip">类型看来源，分层看结构。先有三池/买点，后有复盘统计。</div>
          </div>

          <el-table :data="displayRows" style="width: 100%">
            <el-table-column label="建议" width="96">
              <template #default="{ row }">
                <span :class="['table-judgement', `table-judgement-${rowRecommendation(row).tone}`]">
                  {{ rowRecommendation(row).label }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="类型" width="150">
              <template #default="{ row }">
                {{ row.snapshot_type_label }}
              </template>
            </el-table-column>
            <el-table-column label="分层" min-width="220">
              <template #default="{ row }">
                <div class="bucket-cell">
                  <div class="bucket-name">{{ row.candidate_bucket_tag || '未分层' }}</div>
                  <div class="bucket-copy">{{ bucketHint(row.candidate_bucket_tag) }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="count" label="出现次数" width="90" />
            <el-table-column label="1日均值" width="90">
              <template #default="{ row }">
                {{ formatPctValue(row.avg_return_1d) }}
              </template>
            </el-table-column>
            <el-table-column label="1日胜率" width="90">
              <template #default="{ row }">
                {{ formatPctValue(row.win_rate_1d, true) }}
              </template>
            </el-table-column>
            <el-table-column label="3日均值" width="90">
              <template #default="{ row }">
                {{ formatPctValue(row.avg_return_3d) }}
              </template>
            </el-table-column>
            <el-table-column label="3日胜率" width="90">
              <template #default="{ row }">
                {{ formatPctValue(row.win_rate_3d, true) }}
              </template>
            </el-table-column>
            <el-table-column label="5日均值" width="90">
              <template #default="{ row }">
                {{ formatPctValue(row.avg_return_5d) }}
              </template>
            </el-table-column>
            <el-table-column label="5日胜率" width="90">
              <template #default="{ row }">
                {{ formatPctValue(row.win_rate_5d, true) }}
              </template>
            </el-table-column>
            <el-table-column label="查看来源" width="120" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openSourcePage(row)">去源页面</el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { decisionApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const limitDays = ref(10)
const reviewData = ref(null)
const REVIEW_STATS_TIMEOUT = 90000
const router = useRouter()

const SNAPSHOT_TYPE_LABELS = {
  buy_available: '买点-可买',
  buy_observe: '买点-观察',
  pool_account: '三池-可参与池',
  pool_market: '三池-观察池'
}

const snapshotTypeLabel = (value) => SNAPSHOT_TYPE_LABELS[value] || value || '-'
const rowLabel = (row) => `${snapshotTypeLabel(row.snapshot_type)} / ${row.candidate_bucket_tag || '未分层'}`

const BUCKET_HINTS = {
  强势确认: '已经偏强，重点看放量确认和站稳，不适合无脑追高。',
  趋势回踩: '结构还在，重点看回踩承接和再次转强，适合等舒服位置。',
  异动预备: '刚开始异动，先当预备名单，等量价继续确认再升级。',
  观察补充: '只是补充观察样本，优先级通常低于主分层。',
  未分层: '暂时没有稳定结构标签，更多作为辅助样本参考。'
}

const bucketHint = (value) => BUCKET_HINTS[value || '未分层'] || '这是一类候选结构标签，复盘用它来比较同类信号最近的表现。'

const sourceGuideCards = computed(() => ([
  {
    key: 'pool_market',
    snapshotType: 'pool_market',
    kicker: '三池来源',
    name: '三池-观察池',
    copy: '代表当天最强但还不能直接执行的观察名单，任务是先缩小盯盘范围。',
    useFor: '用来看方向和样本',
    hint: '不替代买点确认',
    actionText: '查看三池观察池',
    tone: 'market'
  },
  {
    key: 'pool_account',
    snapshotType: 'pool_account',
    kicker: '三池来源',
    name: '三池-可参与池',
    copy: '代表已经通过账户准入的候选，但是否出手还要回到买点页看触发和失效。',
    useFor: '用来看账户是否允许',
    hint: '能参与不等于立刻买',
    actionText: '查看三池可参与池',
    tone: 'account'
  },
  {
    key: 'buy_observe',
    snapshotType: 'buy_observe',
    kicker: '买点来源',
    name: '买点-观察',
    copy: '代表结构值得继续盯，但确认条件还没到齐，适合等盘中验证后再升级。',
    useFor: '用来看需要继续跟踪的结构',
    hint: '先等确认，不抢先手',
    actionText: '查看买点观察区',
    tone: 'watch'
  },
  {
    key: 'buy_available',
    snapshotType: 'buy_available',
    kicker: '买点来源',
    name: '买点-可买',
    copy: '代表已经接近执行区，复盘统计最适合用来比较这类结构最近究竟值不值得优先做。',
    useFor: '用来看哪些结构更值得先做',
    hint: '仍需触发价和失效位',
    actionText: '查看买点可买区',
    tone: 'buy'
  }
]))

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
    .sort((a, b) => Number(b.qualityScore || 0) - Number(a.qualityScore || 0))
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

const priorityRows = computed(() => actionableRows.value.slice(0, 3))
const cautionRows = computed(() => [...actionableRows.value].slice(-2).reverse())

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
  const breakdown = `当前待补：1日 ${pending1d} 条，3日 ${pending3d} 条，5日 ${pending5d} 条`
  if (reviewData.value?.refresh_in_progress) {
    return `历史收益正在后台补齐中，${breakdown}。刷新后会逐步显示真实均值和胜率。`
  }
  return `${breakdown}，因此部分均值和胜率暂时不完整。`
})

const loadData = async ({ refresh = false } = {}) => {
  loading.value = true
  try {
    const res = await decisionApi.reviewStats(limitDays.value, { timeout: REVIEW_STATS_TIMEOUT, refresh })
    reviewData.value = res.data.data
  } catch (error) {
    ElMessage.error('加载复盘统计失败')
  } finally {
    loading.value = false
  }
}

const openSourcePage = (row) => {
  const targetPath = String(row?.snapshot_type || '').startsWith('buy_') ? '/buy' : '/pools'
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

.mode-tip {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 196, 64, 0.08);
  border: 1px solid rgba(255, 196, 64, 0.16);
  color: var(--color-text-main);
  font-size: 13px;
}

.review-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(340px, 0.85fr);
  gap: 18px;
  margin-bottom: 18px;
}

.hero-main,
.hero-side {
  display: grid;
  gap: 16px;
}

.hero-copy {
  display: grid;
  gap: 8px;
  padding: 22px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(84, 210, 164, 0.10), transparent 36%),
    linear-gradient(135deg, rgba(255,255,255,0.025), rgba(255,255,255,0.04));
  border: 1px solid rgba(255,255,255,0.06);
}

.hero-kicker {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-title {
  font-size: 28px;
  line-height: 1.3;
  font-weight: 800;
  color: var(--color-text-pri);
}

.hero-desc {
  color: var(--color-text-main);
  line-height: 1.7;
  max-width: 72ch;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.summary-item {
  background: var(--color-hover);
  border: 1px solid var(--color-border);
  border-radius: 14px;
  padding: 14px 16px;
  min-width: 0;
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

.radar-board {
  margin-bottom: 20px;
  padding: 18px;
  border-radius: 16px;
  border: 1px solid rgba(255,255,255,0.06);
  background: linear-gradient(135deg, rgba(255,255,255,0.02), rgba(255,255,255,0.035));
}

.radar-board-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 12px;
}

.radar-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.radar-panel {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.05);
  background: rgba(255,255,255,0.02);
}

.radar-panel-do {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.08);
}

.radar-panel-avoid {
  box-shadow: inset 0 0 0 1px rgba(255, 120, 120, 0.08);
}

.radar-label {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.06em;
}

.radar-list {
  display: grid;
  gap: 10px;
}

.radar-item {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.05);
}

.radar-item strong {
  color: var(--color-text-pri);
}

.radar-item span {
  color: var(--color-text-sec);
  font-size: 13px;
}

.source-guide {
  margin-bottom: 20px;
}

.source-guide-head {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 12px;
  margin-bottom: 12px;
}

.source-guide-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-pri);
}

.source-guide-desc {
  margin-top: 6px;
  font-size: 13px;
  color: var(--color-text-sec);
}

.source-guide-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.source-guide-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 14px;
  border: 1px solid var(--color-border);
  background: linear-gradient(135deg, rgba(255,255,255,0.02), rgba(255,255,255,0.04));
}

.source-guide-card-market {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.08);
}

.source-guide-card-account {
  box-shadow: inset 0 0 0 1px rgba(88, 176, 255, 0.10);
}

.source-guide-card-watch {
  box-shadow: inset 0 0 0 1px rgba(255, 196, 64, 0.08);
}

.source-guide-card-buy {
  box-shadow: inset 0 0 0 1px rgba(255, 120, 120, 0.08);
}

.source-guide-kicker {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.06em;
}

.source-guide-name {
  font-size: 20px;
  font-weight: 800;
  color: var(--color-text-pri);
  line-height: 1.25;
}

.source-guide-copy {
  color: var(--color-text-main);
  line-height: 1.7;
}

.source-guide-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.source-guide-chip {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--color-text-sec);
  font-size: 12px;
}

.source-guide-actions {
  display: flex;
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
  background: rgba(255,255,255,0.06);
}

@media (max-width: 1200px) {
  .review-hero,
  .conclusion-grid,
  .action-board-grid,
  .radar-grid,
  .source-guide-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .hero-title {
    font-size: 24px;
  }
}

.evidence-tip {
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--color-text-sec);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.bucket-cell {
  display: grid;
  gap: 4px;
}

.bucket-name {
  color: var(--color-text-pri);
  font-weight: 700;
}

.bucket-copy {
  color: var(--color-text-sec);
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 960px) {
  .conclusion-grid,
  .source-guide-grid,
  .action-board-grid {
    grid-template-columns: 1fr;
  }

  .summary-strip {
    flex-wrap: wrap;
  }
}
</style>
