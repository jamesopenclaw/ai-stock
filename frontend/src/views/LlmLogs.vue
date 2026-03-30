<template>
  <div class="llm-logs-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>LLM 调用记录</span>
            <span class="header-desc">查看解释增强请求是否成功、失败原因、调用耗时和每日 token 消耗变化。</span>
          </div>
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </template>

      <div class="overview-grid">
        <div class="overview-card">
          <span class="overview-label">最近记录</span>
          <strong class="overview-value">{{ logs.length }}</strong>
          <span class="overview-tip">按时间倒序展示</span>
        </div>
        <div class="overview-card">
          <span class="overview-label">成功次数</span>
          <strong class="overview-value success-text">{{ successCount }}</strong>
          <span class="overview-tip">解释增强真正生效的调用</span>
        </div>
        <div class="overview-card">
          <span class="overview-label">失败次数</span>
          <strong class="overview-value warning-text">{{ failureCount }}</strong>
          <span class="overview-tip">可直接定位超时或接口错误</span>
        </div>
        <div class="overview-card">
          <span class="overview-label">近 {{ trendDays }} 天估算 Token</span>
          <strong class="overview-value info-text">{{ formatToken(trendSummary.total_tokens_estimated) }}</strong>
          <span class="overview-tip">基于请求/返回长度估算，用于观察每日波动</span>
        </div>
      </div>

      <section class="trend-panel">
        <div class="trend-header">
          <div class="trend-header-copy">
            <div class="trend-title">每日 Token 消耗柱状图</div>
            <div class="trend-desc">
              按调用日期汇总请求与返回体量，默认展示最近 {{ trendDays }} 天。当前为估算值，计算规则：{{ trendRuleLabel }}。
            </div>
          </div>
          <div class="trend-actions">
            <span class="trend-range-label">统计范围</span>
            <el-select v-model="trendDays" style="width: 120px" @change="loadData">
              <el-option label="最近 7 天" :value="7" />
              <el-option label="最近 14 天" :value="14" />
              <el-option label="最近 30 天" :value="30" />
            </el-select>
          </div>
        </div>

        <div class="trend-summary-grid">
          <div class="trend-summary-card">
            <span class="trend-summary-label">总消耗</span>
            <strong class="trend-summary-value">{{ formatToken(trendSummary.total_tokens_estimated) }}</strong>
            <span class="trend-summary-tip">{{ trendDateRangeLabel }}</span>
          </div>
          <div class="trend-summary-card">
            <span class="trend-summary-label">请求 / 返回</span>
            <strong class="trend-summary-value">
              {{ formatToken(trendSummary.request_tokens_estimated) }} / {{ formatToken(trendSummary.response_tokens_estimated) }}
            </strong>
            <span class="trend-summary-tip">拆开看是为了判断输入过长还是输出膨胀</span>
          </div>
          <div class="trend-summary-card">
            <span class="trend-summary-label">期间调用</span>
            <strong class="trend-summary-value">{{ trendSummary.total_calls }}</strong>
            <span class="trend-summary-tip">成功率 {{ formatRate(trendSummary.success_rate) }}</span>
          </div>
        </div>

        <div v-if="dailyStats.length" class="token-chart-panel">
          <div class="token-chart-legend">
            <span class="legend-item"><i class="legend-dot legend-dot-request"></i>请求估算</span>
            <span class="legend-item"><i class="legend-dot legend-dot-response"></i>返回估算</span>
          </div>
          <div class="token-chart">
            <div class="chart-axis">
              <span>{{ compactToken(chartMaxValue) }}</span>
              <span>{{ compactToken(chartMidValue) }}</span>
              <span>0</span>
            </div>
            <div class="chart-grid">
              <div
                v-for="item in dailyStats"
                :key="item.date"
                class="chart-day"
              >
                <span class="chart-total">{{ compactToken(item.total_tokens_estimated) }}</span>
                <div
                  class="chart-column-shell"
                  :title="buildDailyTooltip(item)"
                >
                  <div class="chart-column">
                    <div
                      class="chart-bar chart-bar-response"
                      :style="{ height: barHeight(item.response_tokens_estimated) }"
                    ></div>
                    <div
                      class="chart-bar chart-bar-request"
                      :style="{ height: barHeight(item.request_tokens_estimated) }"
                    ></div>
                  </div>
                </div>
                <span class="chart-label">{{ shortDateLabel(item.date) }}</span>
                <span class="chart-meta">{{ item.call_count }} 次</span>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="trend-empty">
          当前筛选条件下暂无可展示的调用趋势
        </div>
      </section>

      <div class="filters">
        <el-select v-model="filters.scene" clearable placeholder="调用场景" style="width: 180px">
          <el-option label="三池分类" value="stock_pools" />
          <el-option label="卖点分析" value="sell_points" />
          <el-option label="个股体检" value="stock_checkup" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="调用状态" style="width: 180px">
          <el-option label="成功" value="success" />
          <el-option label="超时" value="timeout" />
          <el-option label="HTTP错误" value="http_error" />
          <el-option label="请求失败" value="request_error" />
          <el-option label="解析失败" value="parse_error" />
          <el-option label="校验失败" value="validation_error" />
          <el-option label="未启用" value="disabled" />
        </el-select>
        <el-select v-model="filters.success" clearable placeholder="结果" style="width: 140px">
          <el-option label="成功" :value="true" />
          <el-option label="失败" :value="false" />
        </el-select>
        <el-input-number v-model="filters.limit" :min="20" :max="500" :step="20" />
        <el-button type="primary" @click="loadData" :loading="loading">查询</el-button>
      </div>

      <el-empty v-if="!loading && !logs.length" description="暂无 LLM 调用记录" />
      <el-table v-else :data="logs" style="width: 100%" v-loading="loading">
        <el-table-column prop="created_at" label="时间" min-width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="scene" label="场景" min-width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="sceneTagType(row.scene)">{{ sceneLabel(row.scene) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="供应商" min-width="120" />
        <el-table-column prop="model" label="模型" min-width="180" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status, row.success)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="latency_ms" label="耗时" min-width="100">
          <template #default="{ row }">
            {{ formatLatency(row.latency_ms) }}
          </template>
        </el-table-column>
        <el-table-column prop="request_chars" label="请求长度" min-width="110" />
        <el-table-column prop="response_chars" label="返回长度" min-width="110" />
        <el-table-column prop="trade_date" label="交易日" min-width="110" />
        <el-table-column prop="message" label="说明" min-width="320" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '../api'

const loading = ref(false)
const logs = ref([])
const trendDays = ref(7)
const dailyStats = ref([])
const trendSummaryRaw = ref({
  total_calls: 0,
  success_calls: 0,
  failure_calls: 0,
  success_rate: 0,
  request_tokens_estimated: 0,
  response_tokens_estimated: 0,
  total_tokens_estimated: 0
})
const trendMeta = ref({
  start_date: '',
  end_date: '',
  token_estimate_rule: 'ceil(chars / 4)'
})
const filters = reactive({
  scene: '',
  status: '',
  success: null,
  limit: 100
})

const successCount = computed(() => logs.value.filter((item) => item.success).length)
const failureCount = computed(() => logs.value.filter((item) => !item.success).length)
const trendSummary = computed(() => trendSummaryRaw.value)
const trendRuleLabel = computed(() => trendMeta.value.token_estimate_rule || 'ceil(chars / 4)')
const trendDateRangeLabel = computed(() => {
  if (!trendMeta.value.start_date || !trendMeta.value.end_date) {
    return '最近调用周期'
  }
  return `${trendMeta.value.start_date} 至 ${trendMeta.value.end_date}`
})
const chartMaxValue = computed(() => {
  const maxValue = Math.max(...dailyStats.value.map((item) => item.total_tokens_estimated || 0), 0)
  return maxValue > 0 ? maxValue : 1
})
const chartMidValue = computed(() => Math.round(chartMaxValue.value / 2))

const sceneLabel = (scene) => {
  if (scene === 'stock_pools') return '三池分类'
  if (scene === 'sell_points') return '卖点分析'
  if (scene === 'stock_checkup') return '个股体检'
  return scene || '-'
}

const sceneTagType = (scene) => {
  if (scene === 'stock_pools') return 'primary'
  if (scene === 'sell_points') return 'warning'
  if (scene === 'stock_checkup') return 'success'
  return 'info'
}

const statusTagType = (status, success) => {
  if (success || status === 'success') return 'success'
  if (status === 'timeout') return 'warning'
  if (status === 'disabled') return 'info'
  return 'danger'
}

const formatLatency = (value) => `${Number(value || 0).toFixed(0)} ms`
const formatTime = (value) => String(value || '').replace('T', ' ').slice(0, 19)
const formatRate = (value) => `${Number(value || 0).toFixed(2)}%`
const formatToken = (value) => Number(value || 0).toLocaleString('zh-CN')
const compactToken = (value) => {
  const numeric = Number(value || 0)
  if (numeric >= 1000000) return `${(numeric / 1000000).toFixed(1)}M`
  if (numeric >= 1000) return `${(numeric / 1000).toFixed(1)}k`
  return String(Math.round(numeric))
}
const shortDateLabel = (value) => String(value || '').slice(5)
const barHeight = (value) => `${(Number(value || 0) / chartMaxValue.value) * 100}%`
const buildDailyTooltip = (item) => {
  const date = item.date || '-'
  const total = formatToken(item.total_tokens_estimated)
  const request = formatToken(item.request_tokens_estimated)
  const response = formatToken(item.response_tokens_estimated)
  const calls = item.call_count || 0
  const success = item.success_count || 0
  const failure = item.failure_count || 0
  return `${date}\n总估算: ${total}\n请求: ${request}\n返回: ${response}\n调用: ${calls} 次\n成功: ${success} / 失败: ${failure}`
}

const buildQueryParams = () => ({
  scene: filters.scene || undefined,
  status: filters.status || undefined,
  success: filters.success === null ? undefined : filters.success
})

const loadData = async () => {
  loading.value = true
  try {
    const baseParams = buildQueryParams()
    const [logsRes, statsRes] = await Promise.all([
      systemApi.llmLogs({
        limit: filters.limit,
        ...baseParams
      }),
      systemApi.llmLogsDailyStats({
        days: trendDays.value,
        ...baseParams
      })
    ])
    logs.value = logsRes.data.data?.logs || []
    dailyStats.value = statsRes.data.data?.daily || []
    trendSummaryRaw.value = statsRes.data.data?.summary || trendSummaryRaw.value
    trendMeta.value = {
      start_date: statsRes.data.data?.start_date || '',
      end_date: statsRes.data.data?.end_date || '',
      token_estimate_rule: statsRes.data.data?.token_estimate_rule || 'ceil(chars / 4)'
    }
  } catch (error) {
    ElMessage.error('加载 LLM 调用记录失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.llm-logs-view {
  min-height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 18px;
}

.overview-card {
  display: grid;
  gap: 8px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
}

.overview-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.overview-value {
  font-size: 1.8rem;
  line-height: 1;
}

.overview-tip {
  color: var(--color-text-sec);
  font-size: 13px;
}

.info-text {
  color: #78a9ff;
}

.success-text {
  color: #44d19f;
}

.warning-text {
  color: #f3c24d;
}

.trend-panel {
  margin-bottom: 18px;
  padding: 18px;
  border-radius: 18px;
  border: 1px solid rgba(120, 169, 255, 0.12);
  background:
    radial-gradient(circle at top left, rgba(120, 169, 255, 0.12), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.015));
}

.trend-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.trend-header-copy {
  display: grid;
  gap: 6px;
}

.trend-title {
  font-size: 16px;
  font-weight: 600;
}

.trend-desc {
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}

.trend-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.trend-range-label {
  color: var(--color-text-sec);
  font-size: 13px;
  white-space: nowrap;
}

.trend-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.trend-summary-card {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.42);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.trend-summary-label {
  color: var(--color-text-sec);
  font-size: 12px;
}

.trend-summary-value {
  font-size: 1.25rem;
  line-height: 1.2;
}

.trend-summary-tip {
  color: var(--color-text-sec);
  font-size: 12px;
}

.token-chart-panel {
  display: grid;
  gap: 12px;
}

.token-chart-legend {
  display: flex;
  align-items: center;
  gap: 16px;
  color: var(--color-text-sec);
  font-size: 12px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.legend-dot-request {
  background: #78a9ff;
}

.legend-dot-response {
  background: #44d19f;
}

.token-chart {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 14px;
  min-height: 280px;
}

.chart-axis {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  padding: 10px 0 28px;
  color: var(--color-text-sec);
  font-size: 12px;
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(56px, 1fr));
  gap: 12px;
  align-items: end;
  min-height: 280px;
  padding: 8px 0 0;
  background-image: linear-gradient(
    to top,
    rgba(255, 255, 255, 0.08) 1px,
    transparent 1px
  );
  background-size: 100% 33.333%;
}

.chart-day {
  display: grid;
  gap: 8px;
  justify-items: center;
}

.chart-total {
  color: var(--color-text-sec);
  font-size: 12px;
}

.chart-column-shell {
  display: flex;
  align-items: flex-end;
  width: 100%;
  max-width: 44px;
  height: 180px;
  padding: 6px;
  border-radius: 14px 14px 10px 10px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.02));
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.chart-column {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 10px;
}

.chart-bar {
  min-height: 0;
  transition: height 0.2s ease;
}

.chart-bar-request {
  background: linear-gradient(180deg, rgba(120, 169, 255, 0.98), rgba(70, 110, 212, 0.92));
}

.chart-bar-response {
  background: linear-gradient(180deg, rgba(68, 209, 159, 0.98), rgba(38, 148, 112, 0.92));
}

.chart-label,
.chart-meta {
  color: var(--color-text-sec);
  font-size: 12px;
}

.trend-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  border-radius: 16px;
  border: 1px dashed rgba(255, 255, 255, 0.1);
  color: var(--color-text-sec);
  font-size: 13px;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 18px;
}

@media (max-width: 1100px) {
  .overview-grid,
  .trend-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trend-header {
    flex-direction: column;
  }

  .trend-actions {
    width: 100%;
    justify-content: flex-start;
  }
}

@media (max-width: 768px) {
  .overview-grid,
  .trend-summary-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .token-chart {
    grid-template-columns: 1fr;
  }

  .chart-axis {
    display: none;
  }

  .chart-grid {
    overflow-x: auto;
    grid-auto-columns: 56px;
    grid-auto-flow: column;
    padding-bottom: 4px;
  }
}
</style>
