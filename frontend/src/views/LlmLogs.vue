<template>
  <div class="llm-logs-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>LLM 调用记录</span>
            <span class="header-desc">查看解释增强请求是否成功、失败原因和调用耗时。</span>
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
      </div>

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
const filters = reactive({
  scene: '',
  status: '',
  success: null,
  limit: 100
})

const successCount = computed(() => logs.value.filter((item) => item.success).length)
const failureCount = computed(() => logs.value.filter((item) => !item.success).length)

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

const loadData = async () => {
  loading.value = true
  try {
    const res = await systemApi.llmLogs({
      limit: filters.limit,
      scene: filters.scene || undefined,
      status: filters.status || undefined,
      success: filters.success === null ? undefined : filters.success
    })
    logs.value = res.data.data?.logs || []
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
  grid-template-columns: repeat(3, minmax(0, 1fr));
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

.success-text {
  color: #44d19f;
}

.warning-text {
  color: #f3c24d;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 18px;
}
</style>
