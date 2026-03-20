<template>
  <div class="account-view">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>账户概况</span>
          </template>
          <div v-if="profile" class="profile-info">
            <div class="info-item">
              <span class="label">总资产</span>
              <span class="value">{{ (profile.total_asset / 10000).toFixed(2) }}万</span>
            </div>
            <div class="info-item">
              <span class="label">可用资金</span>
              <span class="value">{{ (profile.available_cash / 10000).toFixed(2) }}万</span>
            </div>
            <div class="info-item">
              <span class="label">持仓市值</span>
              <span class="value">{{ (profile.market_value / 10000).toFixed(2) }}万</span>
            </div>
            <div class="info-item">
              <span class="label">仓位</span>
              <span class="value">{{ (profile.total_position_ratio * 100).toFixed(1) }}%</span>
            </div>
            <div class="info-item">
              <span class="label">持仓数量</span>
              <span class="value">{{ profile.holding_count }}只</span>
            </div>
            <div class="info-item">
              <span class="label">T+1锁定</span>
              <span class="value">{{ profile.t1_locked_count }}只</span>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>账户状态</span>
          </template>
          <div v-if="status" class="status-info">
            <el-tag :type="status.can_trade ? 'success' : 'danger'" size="large">
              {{ status.can_trade ? '可以交易' : '暂停交易' }}
            </el-tag>
            <div class="status-item">
              <span class="label">操作建议</span>
              <span class="value">{{ status.action }}</span>
            </div>
            <div class="status-item">
              <span class="label">优先动作</span>
              <span class="value">{{ status.priority }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <el-card style="margin-top: 20px;">
      <template #header>
        <span>持仓明细</span>
      </template>
      <el-table :data="positions" style="width: 100%">
        <el-table-column prop="ts_code" label="代码" width="100" />
        <el-table-column prop="stock_name" label="名称" width="100" />
        <el-table-column prop="holding_qty" label="数量" width="100" />
        <el-table-column prop="cost_price" label="成本" width="100" />
        <el-table-column prop="market_price" label="现价" width="100" />
        <el-table-column prop="pnl_pct" label="盈亏">
          <template #default="{ row }">
            <span :class="row.pnl_pct > 0 ? 'text-red' : 'text-green'">
              {{ row.pnl_pct?.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="can_sell_today" label="可卖">
          <template #default="{ row }">
            <el-tag :type="row.can_sell_today ? 'success' : 'info'" size="small">
              {{ row.can_sell_today ? '是' : '否(T+1)' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="holding_reason" label="买入理由" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { accountApi } from '../api'
import { ElMessage } from 'element-plus'

const profile = ref(null)
const status = ref(null)
const positions = ref([])

const loadData = async () => {
  try {
    const [profileRes, statusRes, posRes] = await Promise.all([
      accountApi.profile(),
      accountApi.status(),
      accountApi.positions()
    ])
    profile.value = profileRes.data.data
    status.value = statusRes.data.data
    positions.value = posRes.data.data.positions || []
  } catch (error) {
    ElMessage.error('加载失败')
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.profile-info, .status-info { padding: 10px; }
.info-item, .status-item { padding: 12px 0; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }
.info-item .label, .status-item .label { color: #909399; }
.info-item .value, .status-item .value { font-weight: bold; font-size: 16px; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
</style>
