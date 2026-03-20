<template>
  <div class="market-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>市场环境分析</span>
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </template>
      
      <el-row :gutter="20" v-if="marketEnv">
        <el-col :span="6">
          <div class="env-tag">
            <el-tag size="large" :type="getEnvType(marketEnv.market_env_tag)">
              {{ marketEnv.market_env_tag }}
            </el-tag>
          </div>
        </el-col>
        <el-col :span="18">
          <p class="comment">{{ marketEnv.market_comment }}</p>
          <el-row :gutter="20">
            <el-col :span="8">
              <div class="stat-item">
                <div class="label">指数评分</div>
                <div class="value">{{ marketEnv.index_score?.toFixed(1) }}</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="stat-item">
                <div class="label">情绪评分</div>
                <div class="value">{{ marketEnv.sentiment_score?.toFixed(1) }}</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="stat-item">
                <div class="label">综合评分</div>
                <div class="value">{{ marketEnv.overall_score?.toFixed(1) }}</div>
              </div>
            </el-col>
          </el-row>
        </el-col>
      </el-row>
    </el-card>

    <el-card style="margin-top: 20px;">
      <template #header>
        <span>主要指数行情</span>
      </template>
      <el-table :data="indexData" style="width: 100%">
        <el-table-column prop="name" label="指数" />
        <el-table-column prop="close" label="收盘价" />
        <el-table-column prop="change_pct" label="涨跌幅">
          <template #default="{ row }">
            <span :class="row.change_pct > 0 ? 'text-red' : 'text-green'">
              {{ row.change_pct?.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="volume" label="成交量" />
        <el-table-column prop="amount" label="成交额" />
      </el-table>
    </el-card>

    <el-card style="margin-top: 20px;">
      <template #header>
        <span>市场情绪指标</span>
      </template>
      <el-row :gutter="20" v-if="marketStats">
        <el-col :span="6">
          <div class="stat-card">
            <div class="label">涨停数</div>
            <div class="value text-red">{{ marketStats.limit_up_count }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="label">跌停数</div>
            <div class="value text-green">{{ marketStats.limit_down_count }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="label">炸板率</div>
            <div class="value">{{ marketStats.broken_board_rate?.toFixed(1) }}%</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="label">成交额</div>
            <div class="value">{{ (marketStats.market_turnover / 10000)?.toFixed(1) }}万亿</div>
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { marketApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const marketEnv = ref(null)
const indexData = ref([])
const marketStats = ref(null)

const getEnvType = (tag) => {
  if (tag === '进攻') return 'success'
  if (tag === '中性') return 'warning'
  return 'danger'
}

const loadData = async () => {
  loading.value = true
  try {
    const tradeDate = new Date().toISOString().split('T')[0]
    const [envRes, indexRes, statsRes] = await Promise.all([
      marketApi.getEnv(tradeDate),
      marketApi.getIndex(tradeDate),
      marketApi.getStats(tradeDate)
    ])
    marketEnv.value = envRes.data.data
    indexData.value = indexRes.data.data.indexes || []
    marketStats.value = statsRes.data.data
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
.env-tag { text-align: center; padding: 20px; }
.comment { font-size: 16px; margin-bottom: 20px; }
.stat-item { text-align: center; }
.stat-item .label { color: #909399; margin-bottom: 8px; }
.stat-item .value { font-size: 24px; font-weight: bold; }
.stat-card { text-align: center; padding: 20px; background: #f5f7fa; border-radius: 8px; }
.stat-card .label { color: #909399; margin-bottom: 8px; }
.stat-card .value { font-size: 28px; font-weight: bold; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
</style>
