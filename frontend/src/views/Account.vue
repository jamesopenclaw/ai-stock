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
        <div class="card-header">
          <span>持仓明细 ({{ positions.length }}只)</span>
          <el-button type="primary" @click="showAddDialog = true">+ 新增持仓</el-button>
        </div>
      </template>
      <el-table :data="positions" style="width: 100%">
        <el-table-column prop="ts_code" label="代码" width="100" />
        <el-table-column prop="stock_name" label="名称" width="120" />
        <el-table-column prop="holding_qty" label="数量" width="100" />
        <el-table-column prop="cost_price" label="成本" width="100" />
        <el-table-column prop="market_price" label="现价" width="100" />
        <el-table-column prop="pnl_pct" label="盈亏" width="100">
          <template #default="{ row }">
            <span :class="row.pnl_pct > 0 ? 'text-red' : 'text-green'">
              {{ row.pnl_pct?.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="buy_date" label="买入日期" width="120" />
        <el-table-column prop="can_sell_today" label="可卖" width="100">
          <template #default="{ row }">
            <el-tag :type="row.can_sell_today ? 'success' : 'warning'" size="small">
              {{ row.can_sell_today ? '是' : '否(T+1)' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="holding_reason" label="买入理由" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增持仓对话框 -->
    <el-dialog v-model="showAddDialog" title="新增持仓" width="500px">
      <el-form :model="newPosition" label-width="100px">
        <el-form-item label="股票代码" required>
          <el-input v-model="newPosition.ts_code" placeholder="如: 000001" @blur="fetchStockName" />
        </el-form-item>
        <el-form-item label="股票名称">
          <span>{{ newPosition.stock_name || '输入代码后自动获取' }}</span>
        </el-form-item>
        <el-form-item label="持仓数量" required>
          <el-input-number v-model="newPosition.holding_qty" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="成本价" required>
          <el-input-number v-model="newPosition.cost_price" :min="0.01" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="买入日期" required>
          <el-date-picker v-model="newPosition.buy_date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="买入理由">
          <el-input v-model="newPosition.holding_reason" type="textarea" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="handleAdd" :loading="loading">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { accountApi } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const profile = ref(null)
const status = ref(null)
const positions = ref([])
const loading = ref(false)
const showAddDialog = ref(false)
const newPosition = ref({
  ts_code: '',
  stock_name: '',
  holding_qty: null,
  cost_price: null,
  buy_date: '',
  holding_reason: ''
})

const fetchStockName = async () => {
  if (!newPosition.value.ts_code) return
  try {
    const tsCode = newPosition.value.ts_code.trim()
    const res = await fetch(`http://localhost:8000/api/v1/stock/detail/${tsCode}`)
    const data = await res.json()
    if (data.data && data.data.stock) {
      newPosition.value.stock_name = data.data.stock.stock_name
    }
  } catch (e) {
    console.log('获取股票名称失败', e)
  }
}

const handleAdd = async () => {
  if (!newPosition.value.ts_code || !newPosition.value.holding_qty || !newPosition.value.cost_price || !newPosition.value.buy_date) {
    ElMessage.warning('请填写完整信息')
    return
  }
  
  loading.value = true
  try {
    const res = await fetch('http://localhost:8000/api/v1/account/positions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ts_code: newPosition.value.ts_code,
        holding_qty: newPosition.value.holding_qty,
        cost_price: newPosition.value.cost_price,
        buy_date: newPosition.value.buy_date,
        holding_reason: newPosition.value.holding_reason
      })
    })
    const data = await res.json()
    
    if (data.code === 200) {
      ElMessage.success('添加成功')
      showAddDialog.value = false
      // 重置表单
      newPosition.value = {
        ts_code: '',
        stock_name: '',
        holding_qty: null,
        cost_price: null,
        buy_date: '',
        holding_reason: ''
      }
      loadData()
    } else {
      ElMessage.error(data.message || '添加失败')
    }
  } catch (e) {
    ElMessage.error('添加失败')
  } finally {
    loading.value = false
  }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这条持仓记录吗？', '确认删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    const res = await fetch(`http://localhost:8000/api/v1/account/positions/${row.id}`, {
      method: 'DELETE'
    })
    const data = await res.json()
    
    if (data.code === 200) {
      ElMessage.success('删除成功')
      loadData()
    } else {
      ElMessage.error('删除失败')
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const loadData = async () => {
  try {
    const [profileRes, statusRes, posRes] = await Promise.all([
      accountApi.profile(),
      accountApi.status(),
      accountApi.positions()
    ])
    profile.value = profileRes.data
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
.card-header { display: flex; justify-content: space-between; align-items: center; }
.profile-info, .status-info { padding: 10px; }
.info-item, .status-item { padding: 12px 0; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }
.info-item .label, .status-item .label { color: #909399; }
.info-item .value, .status-item .value { font-weight: bold; font-size: 16px; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
</style>
