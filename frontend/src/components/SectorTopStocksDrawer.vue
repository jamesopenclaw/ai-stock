<template>
  <el-drawer
    :model-value="modelValue"
    size="56%"
    class="sector-top-stocks-drawer"
    :destroy-on-close="false"
    @close="handleClose"
  >
    <template #header>
      <div class="drawer-header">
        <div>
          <div class="drawer-title">{{ currentSector?.sector_name || '板块 Top10' }}</div>
          <div class="drawer-meta">
            <span v-if="displayTradeDate">交易日 {{ displayTradeDate }}</span>
            <span v-if="data?.resolved_trade_date && data.resolved_trade_date !== displayTradeDate">
              实际扫描日 {{ data.resolved_trade_date }}
            </span>
            <span>{{ sourceLabel }}</span>
          </div>
        </div>
        <div class="drawer-actions">
          <el-radio-group v-model="sortBy" size="small">
            <el-radio-button label="default">综合</el-radio-button>
            <el-radio-button label="change_pct">涨幅</el-radio-button>
            <el-radio-button label="amount">成交额</el-radio-button>
            <el-radio-button label="turnover_rate">换手</el-radio-button>
          </el-radio-group>
          <el-button @click="loadData()" :loading="loading">刷新</el-button>
        </div>
      </div>
    </template>

    <div class="drawer-body">
      <el-empty v-if="!currentSector" description="请选择板块后再查看 Top10" />
      <el-skeleton v-else-if="loading" :rows="12" animated />
      <el-empty v-else-if="!sortedStocks.length" description="该板块暂无可用 Top10 数据" />
      <template v-else>
        <div class="sector-summary">
          <div class="summary-main">
            <div class="summary-title">{{ currentSector.sector_name }}</div>
            <div class="summary-copy">{{ currentSector.sector_summary_reason || currentSector.sector_comment || '暂无结论' }}</div>
          </div>
          <div class="summary-metrics">
            <div class="metric-card">
              <span>涨跌幅</span>
              <strong :class="currentSector.sector_change_pct > 0 ? 'text-red' : 'text-green'">
                {{ formatPct(currentSector.sector_change_pct) }}
              </strong>
            </div>
            <div class="metric-card">
              <span>综合分</span>
              <strong>{{ currentSector.sector_score ?? '-' }}</strong>
            </div>
            <div class="metric-card">
              <span>执行</span>
              <strong>{{ currentSector.sector_action_hint || '-' }}</strong>
            </div>
          </div>
        </div>

        <div class="stock-list">
          <article v-for="stock in sortedStocks" :key="stock.ts_code" class="stock-card">
            <div class="stock-card-head">
              <div class="stock-main">
                <div class="stock-title">
                  <span class="rank-chip">#{{ stockDisplayRank(stock) }}</span>
                  <strong>{{ stock.stock_name }}</strong>
                  <span class="stock-code">{{ stock.ts_code }}</span>
                </div>
                <div class="stock-tags">
                  <el-tag size="small" type="danger" effect="plain">{{ stock.role_tag || '前排' }}</el-tag>
                  <el-tag v-if="stock.candidate_source_tag" size="small" effect="plain">{{ stock.candidate_source_tag }}</el-tag>
                </div>
              </div>
              <div class="stock-side">
                <strong :class="stock.change_pct > 0 ? 'text-red' : 'text-green'">
                  {{ formatPct(stock.change_pct) }}
                </strong>
              </div>
            </div>

            <div class="stock-metrics">
              <span>成交额 {{ formatAmount(stock.amount) }}</span>
              <span>换手 {{ formatRate(stock.turnover_rate) }}</span>
              <span>量比 {{ formatNumber(stock.vol_ratio) }}</span>
            </div>

            <div class="stock-reason">{{ stock.top_reason || '当前板块内活跃度居前。' }}</div>

            <div class="stock-actions">
              <el-button type="primary" link size="small" @click="$emit('checkup', stock)">查看体检</el-button>
            </div>
          </article>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { sectorApi } from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  tradeDate: { type: String, default: '' },
  sector: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'checkup'])

const loading = ref(false)
const data = ref(null)
const sortBy = ref('default')

const currentSector = computed(() => props.sector || null)
const displayTradeDate = computed(() => props.tradeDate || '')

const sourceLabel = computed(() => {
  const type = currentSector.value?.sector_source_type
  if (type === 'concept') return '题材口径'
  if (type === 'limitup_industry') return '涨停行业口径'
  return '行业口径'
})

const sortedStocks = computed(() => {
  const rows = Array.isArray(data.value?.top_stocks) ? [...data.value.top_stocks] : []
  if (sortBy.value === 'default') {
    return rows
  }
  const key = sortBy.value
  return rows.sort((a, b) => Number(b?.[key] || 0) - Number(a?.[key] || 0))
})

const stockDisplayRank = (stock) => {
  if (sortBy.value === 'default') {
    return stock.rank
  }
  return sortedStocks.value.findIndex((row) => row.ts_code === stock.ts_code) + 1
}

const formatPct = (value) => {
  const num = Number(value || 0)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const formatRate = (value) => `${Number(value || 0).toFixed(2)}%`
const formatNumber = (value) => Number(value || 0).toFixed(2)
const formatAmount = (value) => `${Number(value || 0).toFixed(0)}万`

const handleClose = () => {
  emit('update:modelValue', false)
}

const loadData = async () => {
  if (!props.modelValue || !currentSector.value || !props.tradeDate || loading.value) {
    return
  }
  loading.value = true
  try {
    const res = await sectorApi.topStocks(
      props.tradeDate,
      currentSector.value.sector_name,
      currentSector.value.sector_source_type,
      10,
    )
    data.value = res.data?.data || null
  } catch (error) {
    ElMessage.warning('板块 Top10 加载失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.tradeDate, currentSector.value?.sector_name, currentSector.value?.sector_source_type],
  ([visible]) => {
    if (visible) {
      loadData()
    } else {
      data.value = null
      sortBy.value = 'default'
    }
  },
)
</script>

<style scoped>
.drawer-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}
.drawer-title {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 6px;
}
.drawer-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--color-text-sec);
  font-size: 13px;
}
.drawer-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
}
.drawer-body {
  display: grid;
  gap: 16px;
}
.sector-summary {
  display: grid;
  gap: 14px;
  padding: 16px;
  border-radius: 14px;
  background: var(--color-hover);
  border: 1px solid var(--color-border);
}
.summary-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 8px;
}
.summary-copy {
  color: var(--color-text-sec);
  line-height: 1.7;
}
.summary-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.metric-card {
  padding: 12px;
  border-radius: 12px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.05);
  display: grid;
  gap: 6px;
}
.metric-card span {
  color: var(--color-text-sec);
  font-size: 12px;
}
.stock-list {
  display: grid;
  gap: 12px;
}
.stock-card {
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--color-hover);
  border: 1px solid var(--color-border);
}
.stock-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}
.stock-main {
  display: grid;
  gap: 8px;
}
.stock-title {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.rank-chip {
  font-size: 12px;
  color: var(--color-text-sec);
}
.stock-code {
  color: var(--color-text-sec);
  font-size: 12px;
}
.stock-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.stock-side {
  font-size: 16px;
}
.stock-metrics {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--color-text-sec);
  font-size: 12px;
}
.stock-reason {
  line-height: 1.7;
}
.stock-actions {
  display: flex;
  justify-content: flex-end;
}
.text-red {
  color: var(--el-color-danger);
}
.text-green {
  color: var(--el-color-success);
}

@media (max-width: 900px) {
  .summary-metrics {
    grid-template-columns: 1fr;
  }
  .drawer-header {
    flex-direction: column;
  }
}
</style>
