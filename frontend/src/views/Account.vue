<template>
  <div class="account-view">
    <el-skeleton v-if="pageLoading" :rows="16" animated />
    <template v-else>
    <DataFreshnessBar
      :items="accountFreshnessItems"
      :note="accountFreshnessNote"
    />
    <el-row :gutter="20" class="equal-height">
      <el-col :span="12">
        <el-card class="fill-card">
          <template #header>
            <div class="card-header">
              <span>账户概况</span>
              <el-button type="primary" size="small" @click="openConfigDialog">账户设置</el-button>
            </div>
          </template>
          <div v-if="profile" class="profile-info">
            <div class="info-item">
              <span class="label">总资产</span>
              <span class="value">{{ formatYuan(profile.total_asset) }} 元</span>
            </div>
            <div class="info-item">
              <span class="label">可用资金</span>
              <span class="value">{{ formatYuan(profile.available_cash) }} 元</span>
            </div>
            <div class="info-item">
              <span class="label">持仓市值</span>
              <span class="value">{{ formatYuan(profile.market_value) }} 元</span>
            </div>
            <div class="info-item">
              <span class="label">账户总盈亏</span>
              <span
                class="value"
                :class="pnlAmountClass(profile.total_pnl_amount)"
              >{{ formatPnl(profile.total_pnl_amount) }} 元</span>
            </div>
            <div class="info-item">
              <span class="label">当日盈亏</span>
              <span
                class="value"
                :class="pnlAmountClass(profile.today_pnl_amount)"
              >{{ formatPnl(profile.today_pnl_amount) }} 元</span>
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
        <el-card class="fill-card">
          <template #header>
            <span>账户状态</span>
          </template>
          <div v-if="status && profile" class="status-info">
            <div class="trade-status-block">
              <el-tag
                class="trade-status-tag"
                :type="status.can_trade ? 'success' : 'danger'"
                effect="dark"
                size="large"
              >
                {{ status.can_trade ? '可以交易' : '暂停交易' }}
              </el-tag>
            </div>
            <div class="status-item">
              <span class="label">操作建议</span>
              <span class="value">{{ status.action }}</span>
            </div>
            <div class="status-item">
              <span class="label">优先动作</span>
              <span class="value">{{ status.priority }}</span>
            </div>
            <div class="status-item">
              <span class="label">当前仓位</span>
              <span class="value">{{ (profile.total_position_ratio * 100).toFixed(1) }}%</span>
            </div>
            <div class="status-item">
              <span class="label">可用资金</span>
              <span class="value">{{ formatYuan(profile.available_cash) }} 元</span>
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
      <div v-if="positions.length" class="quote-summary">
        {{ positionsQuoteSummary }}
      </div>
      <el-empty v-if="!positions.length" description="暂无持仓" />
      <el-table v-else :data="positions" style="width: 100%">
        <el-table-column prop="ts_code" label="代码" width="100" sortable />
        <el-table-column prop="stock_name" label="名称" width="120" sortable />
        <el-table-column prop="holding_qty" label="数量" width="100" sortable />
        <el-table-column prop="cost_price" label="成本" width="100" sortable />
        <el-table-column prop="market_price" label="现价" width="140" sortable>
          <template #default="{ row }">
            <div class="price-cell">
              <div>{{ formatPrice(row.market_price) }}</div>
              <div class="quote-meta">{{ formatQuoteMeta(row) }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="holding_market_value" label="市值" width="130" sortable>
          <template #default="{ row }">
            <span>{{ formatYuan(row.holding_market_value) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="holding_days" label="持股天数" width="110" sortable />
        <el-table-column prop="pnl_amount" label="盈亏金额" width="130" sortable>
          <template #default="{ row }">
            <span :class="pnlAmountClass(row.pnl_amount)">{{ formatPnl(row.pnl_amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="today_pnl_amount" label="当日盈亏" width="130" sortable>
          <template #default="{ row }">
            <span :class="pnlAmountClass(row.today_pnl_amount)">{{ formatPnl(row.today_pnl_amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="pnl_pct" label="盈亏%" width="90" sortable>
          <template #default="{ row }">
            <span :class="row.pnl_pct > 0 ? 'text-red' : 'text-green'">
              {{ row.pnl_pct?.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="buy_date" label="买入日期" width="130" sortable />
        <el-table-column prop="can_sell_today" label="可卖" width="100" sortable>
          <template #default="{ row }">
            <el-tag :type="row.can_sell_today ? 'success' : 'warning'" size="small">
              {{ row.can_sell_today ? '是' : '否(T+1)' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="holding_reason" label="买入理由" />
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <div class="action-buttons">
              <el-button type="primary" link size="small" @click="openCheckup(row)">全面体检</el-button>
              <el-button type="success" link size="small" @click="openEditDialog(row, 'add')">加仓</el-button>
              <el-button type="warning" link size="small" @click="openEditDialog(row, 'reduce')">减仓</el-button>
              <el-button type="primary" link size="small" @click="openEditDialog(row, 'update')">调整</el-button>
              <el-button type="danger" link size="small" @click="handleDelete(row)">清仓</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    </template>

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

    <!-- 编辑持仓 -->
    <el-dialog v-model="showEditDialog" :title="editDialogTitle" width="500px" @closed="resetEditForm">
      <el-form :model="editPosition" label-width="100px">
        <el-form-item label="股票代码">
          <span>{{ editPosition.ts_code }}</span>
        </el-form-item>
        <el-form-item label="股票名称">
          <span>{{ editPosition.stock_name }}</span>
        </el-form-item>
        <el-form-item :label="editQtyLabel" required>
          <el-input-number v-model="editPosition.holding_qty" :min="1" :step="100" style="width: 100%" />
          <div class="form-hint">{{ editDialogHint }}</div>
        </el-form-item>
        <el-form-item label="成本价" required>
          <el-input-number v-model="editPosition.cost_price" :min="0.01" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="买入理由">
          <el-input v-model="editPosition.holding_reason" type="textarea" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleEditSave" :loading="editSaving">{{ editConfirmLabel }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDeleteDialog" title="确认清仓" width="420px" class="delete-position-dialog">
      <div class="delete-dialog-body">
        <div class="delete-dialog-icon">!</div>
        <div class="delete-dialog-copy">
          <div class="delete-dialog-title">确定要清掉这条持仓吗？</div>
          <div class="delete-dialog-meta">
            <span>{{ deleteTarget.stock_name || '未命名持仓' }}</span>
            <span>{{ deleteTarget.ts_code || '-' }}</span>
          </div>
          <div class="delete-dialog-note">清仓后会按当前持仓现价回补可用资金，并从持仓列表移除。</div>
        </div>
      </div>
      <template #footer>
        <el-button :disabled="deleteLoading" @click="closeDeleteDialog">取消</el-button>
        <el-button type="danger" :loading="deleteLoading" @click="confirmDelete">确认清仓</el-button>
      </template>
    </el-dialog>

    <!-- 账户配置 -->
    <el-dialog v-model="showConfigDialog" title="账户设置" width="480px">
      <el-form label-width="100px">
        <el-form-item label="可用金额">
          <el-input-number
            v-model="configForm.availableCash"
            :min="0"
            :precision="2"
            :step="10000"
            style="width: 100%"
          />
          <div class="form-hint">单位：元。总资产会按“可用金额 + 持仓市值”自动计算。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showConfigDialog = false">取消</el-button>
        <el-button type="primary" :loading="configSaving" @click="saveAccountConfig">保存</el-button>
      </template>
    </el-dialog>

    <StockCheckupDrawer
      v-model="checkupVisible"
      :ts-code="checkupStock.tsCode"
      :stock-name="checkupStock.stockName"
      :default-target="checkupStock.defaultTarget"
      :trade-date="getLocalDate()"
    />
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { accountApi, stockApi } from '../api'
import { ElMessage } from 'element-plus'
import StockCheckupDrawer from '../components/StockCheckupDrawer.vue'
import { formatLocalTime } from '../utils/datetime'
import DataFreshnessBar from '../components/DataFreshnessBar.vue'

const profile = ref(null)
const status = ref(null)
const positions = ref([])
const pageLoading = ref(true)
const isFirstLoad = ref(true)
const loading = ref(false)
const showAddDialog = ref(false)
const showEditDialog = ref(false)
const editSaving = ref(false)
const showDeleteDialog = ref(false)
const deleteLoading = ref(false)
const showConfigDialog = ref(false)
const configSaving = ref(false)
const configForm = ref({ availableCash: 1_000_000 })
const checkupVisible = ref(false)
const checkupStock = ref({ tsCode: '', stockName: '', defaultTarget: '持仓型' })
const deleteTarget = ref({ id: null, ts_code: '', stock_name: '' })

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** 金额展示为千分位 + 两位小数 */
const formatYuan = (n) => {
  if (n == null || Number.isNaN(Number(n))) return '—'
  return Number(n).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

/** 盈亏金额：正数带 +，负数由 toLocaleString 自带负号 */
const formatPnl = (n) => {
  if (n == null || Number.isNaN(Number(n))) return '—'
  const num = Number(n)
  const sign = num > 0 ? '+' : ''
  return (
    sign +
    num.toLocaleString('zh-CN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })
  )
}

const pnlAmountClass = (n) => {
  if (n == null || Number.isNaN(Number(n))) return ''
  const num = Number(n)
  if (num > 0) return 'text-red'
  if (num < 0) return 'text-green'
  return ''
}

const formatPrice = (n) => {
  if (n == null || Number.isNaN(Number(n))) return '—'
  return Number(n).toFixed(2)
}

const simplifySource = (source) => {
  if (!source) return '未知来源'
  if (String(source).startsWith('realtime_')) return '盘中实时'
  if (String(source).includes('daily') || source === 'bak_daily') return '日线回退'
  return String(source)
}

const formatQuoteMeta = (row) => {
  const source = simplifySource(row?.data_source)
  if (!row?.quote_time) return source
  const time = formatLocalTime(row.quote_time)
  return `${source} ${time}`
}

const positionsQuoteSummary = computed(() => {
  if (!positions.value.length) return ''
  const realtimeRows = positions.value.filter(
    (row) => row?.data_source && String(row.data_source).startsWith('realtime_')
  )
  if (!realtimeRows.length) {
    return '当前持仓现价未取到盘中实时，已回退到最近可用日线。'
  }
  const latest = realtimeRows
    .map((row) => row.quote_time)
    .filter(Boolean)
    .sort()
    .slice(-1)[0]
  const prefix = realtimeRows.length === positions.value.length
    ? '当前持仓现价已切到盘中实时。'
    : '当前持仓现价为混合口径，部分股票已切到盘中实时。'
  if (!latest) return prefix
  const time = formatLocalTime(latest)
  return `${prefix} 最新时间 ${time}。`
})
const positionRealtimeCount = computed(() => (
  positions.value.filter((row) => row?.data_source && String(row.data_source).startsWith('realtime_')).length
))
const accountFreshnessItems = computed(() => [
  { label: '查看日', value: getLocalDate(), tone: 'strong' },
  {
    label: '价格口径',
    value: positions.value.length
      ? (!positionRealtimeCount.value
          ? '全部为回退价格'
          : positionRealtimeCount.value === positions.value.length
            ? '全部为盘中实时'
            : `混合口径 ${positionRealtimeCount.value}/${positions.value.length} 为盘中实时`)
      : '当前无持仓',
    tone: positionRealtimeCount.value ? 'strong' : 'warn',
  },
  {
    label: '持仓数量',
    value: `${positions.value.length} 只`,
    tone: 'muted',
  },
])
const accountFreshnessNote = computed(() => positionsQuoteSummary.value || '当前账户页优先回答仓位、可卖状态和持仓动作。')
const newPosition = ref({
  ts_code: '',
  stock_name: '',
  holding_qty: null,
  cost_price: null,
  buy_date: '',
  holding_reason: ''
})

const editPosition = ref({
  original_qty: null,
  ts_code: '',
  stock_name: '',
  holding_qty: null,
  cost_price: null,
  holding_reason: ''
})
const editMode = ref('update')

const editDialogTitleMap = {
  add: '加仓',
  reduce: '减仓',
  update: '调整持仓'
}

const editDialogTitle = computed(() => editDialogTitleMap[editMode.value] || '调整持仓')

const editQtyLabel = computed(() => {
  if (editMode.value === 'add') return '加仓后总持仓'
  if (editMode.value === 'reduce') return '减仓后剩余持仓'
  return '持仓数量'
})

const editConfirmLabel = computed(() => {
  if (editMode.value === 'add') return '确认加仓'
  if (editMode.value === 'reduce') return '确认减仓'
  return '保存调整'
})

const editDialogHint = computed(() => {
  const originalQty = Number(editPosition.value.original_qty || 0)
  if (!originalQty) return '填写调整后的持仓数量。'
  if (editMode.value === 'add') return `当前持仓 ${originalQty} 股，请填写加仓后的总持仓数量。`
  if (editMode.value === 'reduce') return `当前持仓 ${originalQty} 股，请填写减仓后保留的股数。`
  return `当前持仓 ${originalQty} 股，可同步调整成本价或买入理由。`
})

const openEditDialog = (row, mode = 'update') => {
  editMode.value = mode
  editPosition.value = {
    original_qty: row.holding_qty,
    ts_code: row.ts_code,
    stock_name: row.stock_name || '',
    holding_qty: row.holding_qty,
    cost_price: row.cost_price,
    holding_reason: row.holding_reason || ''
  }
  showEditDialog.value = true
}

const resetEditForm = () => {
  editMode.value = 'update'
  editPosition.value = {
    original_qty: null,
    ts_code: '',
    stock_name: '',
    holding_qty: null,
    cost_price: null,
    holding_reason: ''
  }
}

const handleEditSave = async () => {
  const { ts_code, holding_qty, cost_price, original_qty } = editPosition.value
  if (!ts_code || holding_qty == null || holding_qty < 1 || cost_price == null || cost_price <= 0) {
    ElMessage.warning('请填写有效的持仓数量与成本价')
    return
  }
  if (editMode.value === 'add' && Number(holding_qty) <= Number(original_qty || 0)) {
    ElMessage.warning('加仓后的总持仓数量必须大于当前持仓')
    return
  }
  if (editMode.value === 'reduce' && Number(holding_qty) >= Number(original_qty || 0)) {
    ElMessage.warning('减仓后剩余股数必须小于当前持仓')
    return
  }
  editSaving.value = true
  try {
    const res = await accountApi.updatePosition(ts_code, {
      holding_qty,
      cost_price,
      holding_reason: editPosition.value.holding_reason ?? ''
    })
    const data = res.data
    if (data.code === 200) {
      ElMessage.success(data.data?.message || '保存成功')
      showEditDialog.value = false
      await loadData({ refresh: true })
    } else {
      ElMessage.error(data.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    editSaving.value = false
  }
}

const fetchStockName = async () => {
  if (!newPosition.value.ts_code) return
  try {
    const tsCode = newPosition.value.ts_code.trim()
    const res = await stockApi.detail(tsCode)
    const payload = res.data
    if (payload?.data?.stock) {
      newPosition.value.stock_name = payload.data.stock.stock_name
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
    const res = await accountApi.addPosition({
      ts_code: newPosition.value.ts_code,
      holding_qty: newPosition.value.holding_qty,
      cost_price: newPosition.value.cost_price,
      buy_date: newPosition.value.buy_date,
      holding_reason: newPosition.value.holding_reason
    })
    const data = res.data

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
      loadData({ refresh: true })
    } else {
      ElMessage.error(data.message || '添加失败')
    }
  } catch (e) {
    ElMessage.error('添加失败')
  } finally {
    loading.value = false
  }
}

const handleDelete = (row) => {
  deleteTarget.value = {
    id: row.id,
    ts_code: row.ts_code || '',
    stock_name: row.stock_name || ''
  }
  showDeleteDialog.value = true
}

const closeDeleteDialog = (force = false) => {
  if (deleteLoading.value && !force) return
  showDeleteDialog.value = false
  deleteTarget.value = { id: null, ts_code: '', stock_name: '' }
}

const confirmDelete = async () => {
  if (!deleteTarget.value.id) return
  deleteLoading.value = true
  try {
    const res = await accountApi.deletePosition(deleteTarget.value.id)
    const data = res.data

    if (data.code === 200) {
      ElMessage.success(data.data?.message || '清仓成功')
      closeDeleteDialog(true)
      await loadData({ refresh: true })
    } else {
      ElMessage.error(data.message || '删除失败')
    }
  } catch (e) {
    ElMessage.error('删除失败')
  } finally {
    deleteLoading.value = false
  }
}

const openCheckup = (row) => {
  checkupStock.value = {
    tsCode: row.ts_code,
    stockName: row.stock_name || row.ts_code,
    defaultTarget: '持仓型'
  }
  checkupVisible.value = true
}

const loadData = async (options = {}) => {
  if (isFirstLoad.value) pageLoading.value = true
  try {
    const res = await accountApi.overview({ refresh: Boolean(options.refresh) })
    const data = res.data?.data || {}
    profile.value = data.profile || null
    status.value = data.status || null
    positions.value = data.positions || []
    if (!profile.value || !status.value) {
      throw new Error('账户核心数据加载失败')
    }
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    pageLoading.value = false
    isFirstLoad.value = false
  }
}

const openConfigDialog = async () => {
  try {
    const res = await accountApi.getConfig()
    const payload = res.data
    const data = payload?.code === 200 ? (payload.data || {}) : {}
    const availableCash = data.available_cash != null ? data.available_cash : profile.value?.available_cash ?? 1_000_000
    configForm.value = { availableCash: Math.max(0, Number(Number(availableCash).toFixed(2))) }
  } catch {
    const availableCash = profile.value?.available_cash ?? 1_000_000
    configForm.value = { availableCash: Math.max(0, Number(Number(availableCash).toFixed(2))) }
  }
  showConfigDialog.value = true
}

const saveAccountConfig = async () => {
  const available_cash = configForm.value.availableCash
  if (available_cash == null || available_cash < 0) {
    ElMessage.warning('可用金额不能小于 0 元')
    return
  }
  configSaving.value = true
  try {
    const res = await accountApi.updateConfig({ available_cash })
    const payload = res.data
    if (payload.code === 200) {
      ElMessage.success('保存成功')
      showConfigDialog.value = false
      await loadData({ refresh: true })
    } else {
      ElMessage.error(payload.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    configSaving.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.form-hint { font-size: 12px; color: var(--color-text-sec); margin-top: 6px; }
.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 6px;
}

.account-view :deep(.el-table th .cell) {
  white-space: nowrap;
}

.equal-height {
  align-items: stretch;
}
.equal-height .el-col {
  display: flex;
  flex-direction: column;
}
.fill-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.fill-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.profile-info {
  padding: 10px;
  flex: 1;
  display: flex;
  flex-direction: column;
}
.status-info {
  padding: 10px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
/* 交易状态为账户页核心信息：大号字 + 区域纵向居中，弱化「大块空白里一小条标签」 */
.trade-status-block {
  flex: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 12px 8px;
  min-height: 0;
}
.trade-status-block :deep(.trade-status-tag.el-tag) {
  font-size: clamp(1.35rem, 3.2vw, 2rem);
  font-weight: 700;
  line-height: 1.2;
  height: auto;
  padding: 14px 28px;
  border-radius: 10px;
  letter-spacing: 0.06em;
}
.delete-dialog-body {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 6px 2px 2px;
}
.delete-dialog-icon {
  width: 32px;
  height: 32px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #ffd6d6;
  background: rgba(242, 54, 69, 0.18);
  border: 1px solid rgba(242, 54, 69, 0.32);
  flex: 0 0 auto;
}
.delete-dialog-copy {
  display: grid;
  gap: 8px;
}
.delete-dialog-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-pri);
  line-height: 1.5;
}
.delete-dialog-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--color-text-sec);
  font-size: 13px;
}
.delete-dialog-note {
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}
.info-item, .status-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.status-item {
  flex: 1;
  min-height: 0;
}
.info-item .label, .status-item .label { color: var(--color-text-sec); flex-shrink: 0; }
.info-item .value, .status-item .value { font-weight: bold; font-size: 16px; text-align: right; }
.status-item .value { flex: 1; word-break: break-all; }

.quote-summary {
  margin-bottom: 14px;
  padding: 10px 12px;
  border: 1px solid rgba(214, 166, 56, 0.28);
  border-radius: 10px;
  background: rgba(214, 166, 56, 0.08);
  color: var(--color-warning);
  font-size: 13px;
}

.price-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  line-height: 1.2;
}

.quote-meta {
  color: var(--color-text-sec);
  font-size: 12px;
}
</style>
