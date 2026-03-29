<template>
  <div class="task-runs-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>任务调度</span>
            <span class="header-desc">查看最近任务运行记录、失败原因和返回结果，也可以手动触发重跑。</span>
          </div>
          <div class="header-actions">
            <el-switch v-model="autoRefresh" inline-prompt active-text="自动刷新" inactive-text="手动" />
            <el-button @click="loadData" :loading="loading">刷新</el-button>
          </div>
        </div>
      </template>

      <div class="overview-grid">
        <div class="overview-card">
          <span class="overview-label">最近任务</span>
          <strong class="overview-value">{{ tasks.length }}</strong>
          <span class="overview-tip">按时间倒序展示最新运行</span>
        </div>
        <div class="overview-card">
          <span class="overview-label">执行中</span>
          <strong class="overview-value info-text">{{ runningCount }}</strong>
          <span class="overview-tip">`queued / running / retrying` 都算进行中</span>
        </div>
        <div class="overview-card">
          <span class="overview-label">失败次数</span>
          <strong class="overview-value danger-text">{{ failedCount }}</strong>
          <span class="overview-tip">优先查看失败详情和最后一次错误</span>
        </div>
        <div class="overview-card">
          <span class="overview-label">最近成功</span>
          <strong class="overview-value success-text">{{ latestSuccessMode }}</strong>
          <span class="overview-tip">{{ latestSuccessTime }}</span>
        </div>
      </div>

      <div class="trigger-panel">
        <div class="trigger-copy">
          <div class="trigger-title">手动触发任务</div>
          <div class="trigger-desc">默认同一天同模式只保留一个正在执行或已成功的任务。需要重跑时打开“强制重跑”。</div>
        </div>
        <div class="trigger-controls">
          <el-date-picker
            v-model="selectedTradeDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择交易日"
          />
          <el-switch v-model="forceTrigger" inline-prompt active-text="强制重跑" inactive-text="幂等" />
          <el-button
            v-for="mode in modeOptions"
            :key="mode.value"
            type="primary"
            plain
            :loading="triggeringMode === mode.value"
            @click="triggerTask(mode.value)"
          >
            {{ mode.label }}
          </el-button>
        </div>
      </div>

      <el-empty v-if="!loading && !tasks.length" description="暂无任务运行记录" />
      <el-table v-else :data="tasks" style="width: 100%" v-loading="loading">
        <el-table-column prop="created_at" label="创建时间" min-width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="mode" label="模式" min-width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="modeTagType(row.mode)">{{ modeLabel(row.mode) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trade_date" label="交易日" min-width="120" />
        <el-table-column prop="status" label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="attempt_count" label="重试" min-width="90">
          <template #default="{ row }">
            {{ row.attempt_count }}/{{ row.max_attempts }}
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时" min-width="100">
          <template #default="{ row }">
            {{ formatDuration(row.duration_ms) }}
          </template>
        </el-table-column>
        <el-table-column prop="trigger_source" label="来源" min-width="100" />
        <el-table-column prop="last_error" label="最近错误" min-width="320" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.last_error || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="180" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openTaskDetail(row)">
                {{ expandedTaskId === row.id ? '收起' : '详情' }}
              </el-button>
              <el-button link type="warning" @click="triggerTask(row.mode, row.trade_date, true)">重跑</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <section v-if="selectedTask" class="inline-detail-wrap">
        <div class="inline-detail-head">
          <div>
            <div class="inline-detail-title">任务详情</div>
            <div class="inline-detail-desc">当前展开任务：{{ selectedTask.id }}</div>
          </div>
          <el-button link type="primary" @click="collapseTaskDetail">收起</el-button>
        </div>

        <div class="detail-grid">
          <div class="detail-item"><span>任务 ID</span><strong>{{ selectedTask.id }}</strong></div>
          <div class="detail-item"><span>模式</span><strong>{{ modeLabel(selectedTask.mode) }}</strong></div>
          <div class="detail-item"><span>交易日</span><strong>{{ selectedTask.trade_date }}</strong></div>
          <div class="detail-item"><span>状态</span><strong>{{ statusLabel(selectedTask.status) }}</strong></div>
          <div class="detail-item"><span>重试</span><strong>{{ selectedTask.attempt_count }}/{{ selectedTask.max_attempts }}</strong></div>
          <div class="detail-item"><span>耗时</span><strong>{{ formatDuration(selectedTask.duration_ms) }}</strong></div>
          <div class="detail-item"><span>开始时间</span><strong>{{ formatTime(selectedTask.started_at) }}</strong></div>
          <div class="detail-item"><span>结束时间</span><strong>{{ formatTime(selectedTask.finished_at) }}</strong></div>
        </div>

        <div v-if="selectedTaskSummary.length" class="result-summary-grid">
          <div v-for="item in selectedTaskSummary" :key="item.label" class="result-summary-card">
            <span class="result-summary-label">{{ item.label }}</span>
            <strong class="result-summary-value">{{ item.value }}</strong>
            <span class="result-summary-tip">{{ item.tip }}</span>
          </div>
        </div>

        <div v-if="selectedTask.last_error" class="detail-section detail-section-error">
          <div class="detail-title">错误详情</div>
          <pre class="detail-pre">{{ selectedTask.last_error }}</pre>
        </div>

        <div v-if="selectedTask.result" class="detail-section">
          <div class="detail-title">返回结果</div>
          <pre class="detail-pre">{{ formatJson(selectedTask.result) }}</pre>
        </div>
      </section>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { taskApi } from '../api'

const loading = ref(false)
const triggeringMode = ref('')
const tasks = ref([])
const selectedTradeDate = ref(dayjs().format('YYYY-MM-DD'))
const autoRefresh = ref(true)
const forceTrigger = ref(false)
const expandedTaskId = ref('')
const selectedTask = ref(null)
let refreshTimer = null
let detailRefreshTimer = null

const modeOptions = [
  { value: 'daily', label: '完整流程' },
  { value: 'sync', label: '仅同步' },
  { value: 'analyze', label: '仅分析' },
  { value: 'notify', label: '仅推送' },
]

const runningStatuses = new Set(['queued', 'running', 'retrying'])
const runningCount = computed(() => tasks.value.filter((item) => runningStatuses.has(item.status)).length)
const failedCount = computed(() => tasks.value.filter((item) => item.status === 'failed').length)
const latestSuccessTask = computed(() => tasks.value.find((item) => item.status === 'success') || null)
const latestSuccessMode = computed(() => latestSuccessTask.value ? modeLabel(latestSuccessTask.value.mode) : '暂无')
const latestSuccessTime = computed(() => latestSuccessTask.value ? formatTime(latestSuccessTask.value.finished_at || latestSuccessTask.value.updated_at) : '等待下一次成功执行')
const selectedTaskSummary = computed(() => buildTaskSummary(selectedTask.value))

const modeLabel = (mode) => {
  if (mode === 'daily') return '完整流程'
  if (mode === 'sync') return '仅同步'
  if (mode === 'analyze') return '仅分析'
  if (mode === 'notify') return '仅推送'
  return mode || '-'
}

const statusLabel = (status) => {
  if (status === 'queued') return '排队中'
  if (status === 'running') return '执行中'
  if (status === 'retrying') return '重试中'
  if (status === 'success') return '成功'
  if (status === 'failed') return '失败'
  return status || '-'
}

const modeTagType = (mode) => {
  if (mode === 'daily') return 'primary'
  if (mode === 'sync') return 'info'
  if (mode === 'analyze') return 'success'
  if (mode === 'notify') return 'warning'
  return 'info'
}

const statusTagType = (status) => {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'retrying') return 'warning'
  if (status === 'running') return 'primary'
  return 'info'
}

const formatDuration = (value) => `${Number(value || 0).toFixed(0)} ms`
const formatTime = (value) => value ? String(value).replace('T', ' ').slice(0, 19) : '-'
const formatJson = (value) => JSON.stringify(value, null, 2)

const buildTaskSummary = (task) => {
  if (task?.result_summary) {
    const summary = task.result_summary
    return [
      {
        label: '交易动作',
        value: summary.today_action || summary.pipeline || '-',
        tip: summary.priority_action || '本次任务的最高优先级动作',
      },
      {
        label: '市场环境',
        value: summary.market_env_tag || '-',
        tip: summary.market_comment || '用于判断今天进攻还是防守',
      },
      {
        label: '可买数量',
        value: String(summary.available_buy_count ?? 0),
        tip: '结果里真正进入可买名单的标的数',
      },
      {
        label: '持仓处理',
        value: String(summary.sell_signal_count ?? 0),
        tip: '卖出和减仓信号合计数量',
      },
      {
        label: '候选池规模',
        value: String(summary.candidate_pool_count ?? 0),
        tip: '观察池、趋势池、账户池三者合计',
      },
    ].filter((item) => item.value !== '-')
  }

  if (!task?.result) return []
  const result = task.result
  const report = result.report || {}
  const summary = report.summary || {}
  const buyAnalysis = report.buy_analysis || {}
  const stockPools = report.stock_pools || {}
  const sellAnalysis = report.sell_analysis || {}

  return [
    {
      label: '交易动作',
      value: summary.today_action || result.pipeline || '-',
      tip: summary.priority_action || '本次任务的最高优先级动作',
    },
    {
      label: '市场环境',
      value: report.market_env?.market_env_tag || '-',
      tip: report.market_env?.market_comment || '用于判断今天进攻还是防守',
    },
    {
      label: '可买数量',
      value: String((buyAnalysis.available_buy_points || []).length),
      tip: '结果里真正进入可买名单的标的数',
    },
    {
      label: '持仓处理',
      value: String(((sellAnalysis.sell_positions || []).length + (sellAnalysis.reduce_positions || []).length)),
      tip: '卖出和减仓信号合计数量',
    },
    {
      label: '候选池规模',
      value: String(
        Number(stockPools.market_watch_count || 0) +
        Number(stockPools.trend_recognition_count || 0) +
        Number(stockPools.account_executable_count || 0)
      ),
      tip: '观察池、趋势池、账户池三者合计',
    },
  ].filter((item) => item.value !== '-')
}

const syncSelectedTask = async (taskId) => {
  try {
    const res = await taskApi.status({ task_id: taskId })
    if (res.data.task) {
      selectedTask.value = res.data.task
    }
  } catch (error) {
    ElMessage.error('加载任务详情失败')
  }
}

const openTaskDetail = async (task) => {
  if (expandedTaskId.value === task.id) {
    collapseTaskDetail()
    return
  }
  expandedTaskId.value = task.id
  selectedTask.value = task
  await syncSelectedTask(task.id)
}

const collapseTaskDetail = () => {
  expandedTaskId.value = ''
  selectedTask.value = null
  clearDetailRefresh()
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await taskApi.status({ limit: 20 })
    tasks.value = res.data.tasks || []
  } catch (error) {
    ElMessage.error('加载任务运行记录失败')
  } finally {
    loading.value = false
  }
}

const triggerTask = async (mode, tradeDate = selectedTradeDate.value, force = forceTrigger.value) => {
  triggeringMode.value = mode
  try {
    const res = await taskApi.trigger({
      mode,
      trade_date: tradeDate,
      force,
    })
    if (res.data.status === 'started') {
      ElMessage.success(res.data.message)
    } else {
      ElMessage.warning(res.data.message)
    }
    await loadData()
  } catch (error) {
    ElMessage.error('触发任务失败')
  } finally {
    triggeringMode.value = ''
  }
}

const startAutoRefresh = () => {
  clearAutoRefresh()
  refreshTimer = window.setInterval(() => {
    loadData()
  }, 15000)
}

const clearAutoRefresh = () => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const startDetailRefresh = () => {
  clearDetailRefresh()
  if (!selectedTask.value || !runningStatuses.has(selectedTask.value.status)) return
  detailRefreshTimer = window.setInterval(() => {
    if (selectedTask.value?.id) {
      syncSelectedTask(selectedTask.value.id)
    }
  }, 4000)
}

const clearDetailRefresh = () => {
  if (detailRefreshTimer) {
    window.clearInterval(detailRefreshTimer)
    detailRefreshTimer = null
  }
}

watch(autoRefresh, (enabled) => {
  if (enabled) startAutoRefresh()
  else clearAutoRefresh()
})

watch(
  () => [expandedTaskId.value, selectedTask.value?.status],
  () => {
    if (expandedTaskId.value) {
      startDetailRefresh()
    } else {
      clearDetailRefresh()
    }
  }
)

onMounted(() => {
  loadData()
  startAutoRefresh()
})

onBeforeUnmount(() => {
  clearAutoRefresh()
  clearDetailRefresh()
})

defineExpose({
  openTaskDetail,
  syncSelectedTask,
  collapseTaskDetail,
})
</script>

<style scoped>
.task-runs-view {
  min-height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.card-header-title {
  display: grid;
  gap: 4px;
}

.header-desc {
  color: var(--color-text-sec);
  font-size: 13px;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 18px;
}

.overview-card,
.trigger-panel {
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
}

.overview-card {
  display: grid;
  gap: 8px;
  padding: 16px;
}

.overview-label,
.overview-tip {
  color: var(--color-text-sec);
  font-size: 13px;
}

.overview-value {
  font-size: 1.8rem;
  line-height: 1;
}

.success-text {
  color: #44d19f;
}

.danger-text {
  color: #ff6b6b;
}

.info-text {
  color: #73b7ff;
}

.trigger-panel {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 18px;
  margin-bottom: 18px;
}

.trigger-copy {
  display: grid;
  gap: 6px;
  max-width: 420px;
}

.trigger-title {
  font-size: 15px;
  font-weight: 600;
}

.trigger-desc {
  color: var(--color-text-sec);
  line-height: 1.5;
}

.trigger-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
}

.table-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.inline-detail-wrap {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.inline-detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.inline-detail-title {
  font-size: 16px;
  font-weight: 600;
}

.inline-detail-desc {
  color: var(--color-text-sec);
  font-size: 13px;
  margin-top: 4px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.detail-item {
  display: grid;
  gap: 6px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}

.detail-item span {
  color: var(--color-text-sec);
  font-size: 12px;
}

.detail-section {
  margin-top: 16px;
}

.result-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.result-summary-card {
  display: grid;
  gap: 6px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}

.result-summary-label,
.result-summary-tip {
  color: var(--color-text-sec);
  font-size: 12px;
}

.result-summary-value {
  font-size: 1.2rem;
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
}

.detail-pre {
  margin: 0;
  padding: 14px;
  border-radius: 12px;
  background: #11151f;
  border: 1px solid rgba(255, 255, 255, 0.06);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
  color: var(--color-text-pri);
}

.detail-section-error .detail-pre {
  border-color: rgba(255, 107, 107, 0.3);
}

@media (max-width: 1100px) {
  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trigger-panel {
    flex-direction: column;
  }

  .trigger-controls {
    justify-content: flex-start;
  }
}

@media (max-width: 720px) {
  .card-header {
    flex-direction: column;
  }

  .overview-grid,
  .detail-grid,
  .result-summary-grid {
    grid-template-columns: 1fr;
  }

  .inline-detail-head {
    flex-direction: column;
  }
}
</style>
