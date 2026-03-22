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
          <div class="summary-strip">
            <div class="summary-item">
              <div class="label">覆盖交易日</div>
              <div class="value">{{ reviewData.trade_dates?.length || 0 }}</div>
            </div>
            <div class="summary-item">
              <div class="label">快照总数</div>
              <div class="value">{{ reviewData.snapshot_count || 0 }}</div>
            </div>
          </div>

          <el-table :data="reviewData.bucket_stats" style="width: 100%">
            <el-table-column prop="snapshot_type" label="类型" width="100" />
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
import { ref, onMounted } from 'vue'
import { decisionApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const limitDays = ref(10)
const reviewData = ref(null)

const loadData = async () => {
  loading.value = true
  try {
    const res = await decisionApi.reviewStats(limitDays.value)
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
</style>
