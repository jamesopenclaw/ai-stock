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
        <el-tag v-if="scanData.sector_data_mode === 'industry_only'" type="warning">行业口径</el-tag>
        <el-tag v-else-if="scanData.sector_data_mode === 'hybrid'" type="success">题材+行业</el-tag>
        <el-tag v-if="scanData.threshold_profile === 'relaxed'" type="warning">放宽阈值</el-tag>
        <span class="total-text">共 {{ scanData.total_sectors }} 个行业</span>
      </div>
      <el-alert
        v-if="scanData.sector_data_mode === 'industry_only'"
        title="当天题材聚合不可用，当前结果按行业均值扫描，并已自动切换到放宽阈值。"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px;"
      />

      <el-tabs v-model="activeTab">
        <el-tab-pane label="主线板块" name="mainline">
          <el-empty v-if="!scanData.mainline_sectors?.length" description="今日无主线板块（市场偏弱）" />
          <el-table v-else :data="scanData.mainline_sectors" style="width: 100%">
            <el-table-column prop="sector_name" label="板块名称" width="140" />
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.sector_source_type === 'concept' ? 'danger' : 'info'">
                  {{ row.sector_source_type === 'concept' ? '题材' : '行业' }}
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
            <el-table-column prop="sector_continuity_tag" label="持续性" width="100" />
            <el-table-column prop="sector_tradeability_tag" label="交易性" width="90" />
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
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="次主线" name="sub">
          <el-empty v-if="!scanData.sub_mainline_sectors?.length" description="今日无次主线板块" />
          <el-table v-else :data="scanData.sub_mainline_sectors" style="width: 100%">
            <el-table-column prop="sector_name" label="板块名称" width="140" />
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.sector_source_type === 'concept' ? 'danger' : 'info'">
                  {{ row.sector_source_type === 'concept' ? '题材' : '行业' }}
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
            <el-table-column prop="sector_tradeability_tag" label="交易性" width="90" />
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
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="跟风板块" name="follow">
          <el-empty v-if="!scanData.follow_sectors?.length" description="今日无跟风板块" />
          <el-table v-else :data="scanData.follow_sectors" style="width: 100%">
            <el-table-column prop="sector_name" label="板块名称" width="140" />
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.sector_source_type === 'concept' ? 'danger' : 'info'">
                  {{ row.sector_source_type === 'concept' ? '题材' : '行业' }}
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
            <el-table-column prop="sector_tradeability_tag" label="交易性" width="90" />
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
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="全部行业" name="all">
          <el-empty v-if="!allSectors.length" description="暂无行业数据" />
          <el-table v-else :data="allSectors" style="width: 100%" max-height="600">
            <el-table-column type="index" label="排名" width="60" />
            <el-table-column prop="sector_name" label="板块" width="140" />
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.sector_source_type === 'concept' ? 'danger' : 'info'">
                  {{ row.sector_source_type === 'concept' ? '题材' : '行业' }}
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
            <el-table-column prop="sector_tradeability_tag" label="交易性" width="90" />
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
          </el-table>
        </el-tab-pane>
      </el-tabs>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { sectorApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const activeTab = ref('mainline')
const scanData = ref({
  trade_date: '',
  resolved_trade_date: '',
  sector_data_mode: '',
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

const allSectors = computed(() => {
  const all = [
    ...(scanData.value.mainline_sectors || []),
    ...(scanData.value.sub_mainline_sectors || []),
    ...(scanData.value.follow_sectors || []),
    ...(scanData.value.trash_sectors || []),
  ]
  return all.sort((a, b) => b.sector_change_pct - a.sector_change_pct)
})

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
    const res = await sectorApi.scan(tradeDate)
    scanData.value = res.data.data
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
}
.total-text {
  color: var(--color-text-sec);
  font-size: 13px;
}
.reason-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
