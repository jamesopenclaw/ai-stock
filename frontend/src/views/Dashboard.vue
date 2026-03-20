<template>
  <div class="dashboard">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="summary-card">
          <template #header>
            <div class="card-header">
              <span>今日执行摘要</span>
              <el-button type="primary" @click="refreshData" :loading="loading">
                <el-icon><Refresh /></el-icon> 刷新
              </el-button>
            </div>
          </template>
          <div v-if="summary" class="summary-content">
            <el-row :gutter="20">
              <el-col :span="6">
                <div class="summary-item">
                  <div class="label">操作建议</div>
                  <div class="value" :class="getActionClass(summary.today_action)">
                    {{ summary.today_action }}
                  </div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="summary-item">
                  <div class="label">市场环境</div>
                  <div class="value">{{ summary.market_env_tag }}</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="summary-item">
                  <div class="label">账户状态</div>
                  <div class="value">{{ summary.account_action_tag }}</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="summary-item">
                  <div class="label">优先动作</div>
                  <div class="value">{{ summary.priority_action }}</div>
                </div>
              </el-col>
            </el-row>
            <el-row :gutter="20" style="margin-top: 20px;">
              <el-col :span="12">
                <div class="summary-focus">
                  <span class="label">▶ 重点关注：</span>
                  <span class="value">{{ summary.focus }}</span>
                </div>
              </el-col>
              <el-col :span="12">
                <div class="summary-avoid">
                  <span class="label">▶ 规避：</span>
                  <span class="value">{{ summary.avoid }}</span>
                </div>
              </el-col>
            </el-row>
          </div>
          <el-skeleton v-else :rows="4" animated />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="8">
        <el-card class="market-card">
          <template #header>
            <span>市场环境</span>
          </template>
          <div v-if="marketEnv" class="market-env">
            <el-tag :type="getEnvTagType(marketEnv.market_env_tag)" size="large">
              {{ marketEnv.market_env_tag }}
            </el-tag>
            <p>{{ marketEnv.market_comment }}</p>
            <div class="env-detail">
              <div>突破允许: {{ marketEnv.breakout_allowed ? '是' : '否' }}</div>
              <div>风险等级: {{ marketEnv.risk_level }}</div>
            </div>
          </div>
          <el-skeleton v-else :rows="3" animated />
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="sector-card">
          <template #header>
            <span>主线板块</span>
          </template>
          <div v-if="leaderSector" class="leader-sector">
            <div class="sector-name">{{ leaderSector.sector.sector_name }}</div>
            <div class="sector-change">{{ leaderSector.sector.sector_change_pct }}%</div>
            <el-tag size="small">{{ leaderSector.sector.sector_mainline_tag }}</el-tag>
          </div>
          <el-skeleton v-else :rows="3" animated />
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="account-card">
          <template #header>
            <span>账户概况</span>
          </template>
          <div v-if="accountProfile" class="account-profile">
            <div class="profile-item">
              <span class="label">总资产：</span>
              <span class="value">{{ formatMoney(accountProfile.total_asset) }}</span>
            </div>
            <div class="profile-item">
              <span class="label">可用资金：</span>
              <span class="value">{{ formatMoney(accountProfile.available_cash) }}</span>
            </div>
            <div class="profile-item">
              <span class="label">仓位：</span>
              <span class="value">{{ (accountProfile.total_position_ratio * 100).toFixed(1) }}%</span>
            </div>
            <div class="profile-item">
              <span class="label">持仓数：</span>
              <span class="value">{{ accountProfile.holding_count }}只</span>
            </div>
          </div>
          <el-skeleton v-else :rows="3" animated />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>可买候选 ({{ buyPoints?.available_buy_points?.length || 0 }})</span>
          </template>
          <el-table :data="buyPoints?.available_buy_points?.slice(0, 5)" style="width: 100%">
            <el-table-column prop="ts_code" label="代码" width="100" />
            <el-table-column prop="stock_name" label="名称" width="100" />
            <el-table-column prop="buy_point_type" label="买点类型" width="100" />
            <el-table-column prop="buy_risk_level" label="风险" width="80" />
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header>
            <span>持仓处理 ({{ sellPoints?.sell_positions?.length + sellPoints?.reduce_positions?.length || 0 }})</span>
          </template>
          <el-table :data="sellPoints?.sell_positions?.slice(0, 5)" style="width: 100%">
            <el-table-column prop="ts_code" label="代码" width="100" />
            <el-table-column prop="stock_name" label="名称" width="100" />
            <el-table-column prop="sell_signal_tag" label="信号" width="80" />
            <el-table-column prop="sell_point_type" label="类型" width="100" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { decisionApi, marketApi, sectorApi, accountApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const summary = ref(null)
const marketEnv = ref(null)
const leaderSector = ref(null)
const accountProfile = ref(null)
const buyPoints = ref(null)
const sellPoints = ref(null)

const getActionClass = (action) => {
  if (action?.includes('少') || action?.includes('防守')) return 'text-red'
  if (action?.includes('适度') || action?.includes('积极')) return 'text-green'
  return 'text-yellow'
}

const getEnvTagType = (tag) => {
  if (tag === '进攻') return 'success'
  if (tag === '中性') return 'warning'
  return 'danger'
}

const formatMoney = (value) => {
  if (!value) return '-'
  return (value / 10000).toFixed(2) + '万'
}

const refreshData = async () => {
  loading.value = true
  try {
    const tradeDate = new Date().toISOString().split('T')[0]
    
    const [summaryRes, marketRes, sectorRes, accountRes, buyRes, sellRes] = await Promise.all([
      decisionApi.summary(tradeDate),
      marketApi.getEnv(tradeDate),
      sectorApi.leader(tradeDate),
      accountApi.profile(),
      decisionApi.buyPoint(tradeDate, 20),
      decisionApi.sellPoint(tradeDate)
    ])

    summary.value = summaryRes.data.data
    marketEnv.value = marketRes.data.data
    leaderSector.value = sectorRes.data.data
    accountProfile.value = accountRes.data.data
    buyPoints.value = buyRes.data.data
    sellPoints.value = sellRes.data.data

    ElMessage.success('数据刷新成功')
  } catch (error) {
    console.error('刷新数据失败:', error)
    ElMessage.error('数据加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refreshData()
})
</script>

<style scoped>
.dashboard {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.summary-item {
  text-align: center;
}

.summary-item .label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.summary-item .value {
  font-size: 18px;
  font-weight: bold;
}

.text-green { color: #67c23a; }
.text-yellow { color: #e6a23c; }
.text-red { color: #f56c6c; }

.summary-focus, .summary-avoid {
  padding: 10px;
  background: #f5f7fa;
  border-radius: 4px;
}

.summary-focus .label, .summary-avoid .label {
  font-weight: bold;
  color: #409eff;
}

.market-env {
  text-align: center;
}

.market-env p {
  margin: 15px 0;
  color: #606266;
}

.env-detail {
  display: flex;
  justify-content: space-around;
  font-size: 14px;
  color: #909399;
}

.leader-sector {
  text-align: center;
}

.sector-name {
  font-size: 20px;
  font-weight: bold;
  margin-bottom: 10px;
}

.sector-change {
  font-size: 24px;
  color: #f56c6c;
  margin-bottom: 10px;
}

.account-profile .profile-item {
  padding: 8px 0;
  border-bottom: 1px solid #eee;
}

.account-profile .label {
  color: #909399;
}

.account-profile .value {
  font-weight: bold;
  float: right;
}
</style>
