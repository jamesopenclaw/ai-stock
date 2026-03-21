<template>
  <view class="page">
    <view class="card">
      <view class="card-title">账户概况</view>
      <view v-if="profile" class="account-info">
        <view class="info-row">
          <text class="info-label">总资产</text>
          <text class="info-value">{{ formatMoney(profile.total_asset) }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">可用资金</text>
          <text class="info-value">{{ formatMoney(profile.available_cash) }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">持仓市值</text>
          <text class="info-value">{{ formatMoney(profile.market_value) }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">仓位</text>
          <text class="info-value">{{ (profile.total_position_ratio * 100).toFixed(1) }}%</text>
        </view>
        <view class="info-row">
          <text class="info-label">持仓数量</text>
          <text class="info-value">{{ profile.holding_count }}只</text>
        </view>
        <view class="info-row">
          <text class="info-label">T+1锁定</text>
          <text class="info-value">{{ profile.t1_locked_count }}只</text>
        </view>
      </view>
    </view>

    <view class="card">
      <view class="card-title">账户状态</view>
      <view v-if="status" class="status-content">
        <text :class="['status-tag', status.can_trade ? 'tag-success' : 'tag-danger']">
          {{ status.can_trade ? '可以交易' : '暂停交易' }}
        </text>
        <view class="status-info">
          <view class="status-row">
            <text class="status-label">操作建议</text>
            <text class="status-value">{{ status.action }}</text>
          </view>
          <view class="status-row">
            <text class="status-label">优先动作</text>
            <text class="status-value">{{ status.priority }}</text>
          </view>
        </view>
      </view>
    </view>

    <view class="card">
      <view class="card-header">
        <text class="card-title">持仓明细 ({{ positions.length }}只)</text>
        <view class="add-btn" @click="showAddModal = true">+ 新增持仓</view>
      </view>
      
      <view class="position-list">
        <view v-for="(item, index) in positions" :key="item.id || index" class="position-item" @click="toggleDetail(item)">
          <view class="position-header">
            <view class="position-info">
              <text class="position-name">{{ item.stock_name }}</text>
              <text class="position-code">{{ item.ts_code }}</text>
            </view>
            <view class="position-right">
              <text :class="['position-pnl', item.pnl_pct > 0 ? 'text-red' : 'text-green']">
                {{ item.pnl_pct?.toFixed(2) }}%
              </text>
              <text v-if="!item.can_sell_today" class="t1-tag">T+1</text>
            </view>
          </view>
          <!-- 详情展开 -->
          <view v-if="expandedItem === item.id" class="position-detail">
            <view class="detail-row">
              <text class="detail-label">持仓数量</text>
              <text class="detail-value">{{ item.holding_qty }}股</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">成本价</text>
              <text class="detail-value">{{ item.cost_price?.toFixed(2) }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">现价</text>
              <text class="detail-value">{{ item.market_price?.toFixed(2) }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">持仓市值</text>
              <text class="detail-value">{{ formatMoney(item.holding_market_value) }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">盈亏金额</text>
              <text :class="['detail-value', item.pnl_pct > 0 ? 'text-red' : 'text-green']">
                {{ item.pnl_pct > 0 ? '+' : '' }}{{ (item.holding_market_value * item.pnl_pct / 100)?.toFixed(2) }}元
              </text>
            </view>
            <view class="detail-row">
              <text class="detail-label">买入日期</text>
              <text class="detail-value">{{ item.buy_date }}</text>
            </view>
            <view class="detail-row">
              <text class="detail-label">可卖状态</text>
              <text :class="['detail-value', item.can_sell_today ? 'text-green' : 'text-orange']">
                {{ item.can_sell_today ? '是' : '否(T+1)' }}
              </text>
            </view>
            <view class="detail-row" v-if="item.holding_reason">
              <text class="detail-label">买入理由</text>
              <text class="detail-value">{{ item.holding_reason }}</text>
            </view>
            <!-- 删除按钮 -->
            <view class="delete-btn" @click.stop="deletePosition(item.id)">
              删除持仓
            </view>
          </view>
        </view>
      </view>
    </view>

    <!-- 新增持仓弹窗 -->
    <view v-if="showAddModal" class="modal-mask" @click="showAddModal = false">
      <view class="modal-content" @click.stop>
        <view class="modal-header">
          <text class="modal-title">新增持仓</text>
          <text class="modal-close" @click="showAddModal = false">×</text>
        </view>
        <view class="modal-body">
          <view class="form-item">
            <text class="form-label">股票代码 *</text>
            <input class="form-input" v-model="newPosition.ts_code" placeholder="如: 000001" @blur="fetchStockName" />
          </view>
          <view class="form-item">
            <text class="form-label">股票名称</text>
            <text class="form-value">{{ newPosition.stock_name || '输入代码后自动获取' }}</text>
          </view>
          <view class="form-item">
            <text class="form-label">持仓数量 *</text>
            <input class="form-input" v-model="newPosition.holding_qty" type="number" placeholder="如: 1000" />
          </view>
          <view class="form-item">
            <text class="form-label">成本价 *</text>
            <input class="form-input" v-model="newPosition.cost_price" type="digit" placeholder="如: 12.50" />
          </view>
          <view class="form-item">
            <text class="form-label">买入日期 *</text>
            <picker mode="date" :value="newPosition.buy_date" @change="onDateChange">
              <view class="picker-value">{{ newPosition.buy_date || '选择日期' }}</view>
            </picker>
          </view>
          <view class="form-item">
            <text class="form-label">买入理由</text>
            <input class="form-input" v-model="newPosition.holding_reason" placeholder="可选" />
          </view>
          <view class="form-actions">
            <view class="btn-cancel" @click="showAddModal = false">取消</view>
            <view class="btn-confirm" @click="addPosition">确定</view>
          </view>
        </view>
      </view>
    </view>

    <view v-if="loading" class="loading">
      <text>加载中...</text>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { accountApi } from '../../api'

const loading = ref(false)
const profile = ref(null)
const status = ref(null)
const positions = ref([])
const expandedItem = ref(null)
const showAddModal = ref(false)
const newPosition = ref({
  ts_code: '',
  stock_name: '',
  holding_qty: '',
  cost_price: '',
  buy_date: '',
  holding_reason: ''
})

const formatMoney = (value) => {
  if (!value) return '-'
  return (value / 10000).toFixed(2) + '万'
}

const toggleDetail = (item) => {
  expandedItem.value = expandedItem.value === item.id ? null : item.id
}

const fetchStockName = async () => {
  if (!newPosition.value.ts_code) return
  try {
    const tsCode = newPosition.value.ts_code.trim()
    const res = await uni.request({
      url: 'http://localhost:8000/api/v1/stock/detail/' + tsCode,
      method: 'GET'
    })
    if (res.data && res.data.data && res.data.data.stock) {
      newPosition.value.stock_name = res.data.data.stock.stock_name
    }
  } catch (e) {
    console.log('获取股票名称失败', e)
  }
}

const onDateChange = (e) => {
  newPosition.value.buy_date = e.detail.value
}

const addPosition = async () => {
  if (!newPosition.value.ts_code || !newPosition.value.holding_qty || !newPosition.value.cost_price || !newPosition.value.buy_date) {
    uni.showToast({ title: '请填写完整信息', icon: 'none' })
    return
  }
  
  loading.value = true
  try {
    const res = await uni.request({
      url: 'http://localhost:8000/api/v1/account/positions',
      method: 'POST',
      data: {
        ts_code: newPosition.value.ts_code,
        holding_qty: parseInt(newPosition.value.holding_qty),
        cost_price: parseFloat(newPosition.value.cost_price),
        buy_date: newPosition.value.buy_date,
        holding_reason: newPosition.value.holding_reason
      }
    })
    
    if (res.data.code === 200) {
      uni.showToast({ title: '添加成功', icon: 'success' })
      showAddModal.value = false
      // 重置表单
      newPosition.value = {
        ts_code: '',
        stock_name: '',
        holding_qty: '',
        cost_price: '',
        buy_date: '',
        holding_reason: ''
      }
      // 刷新数据
      loadData()
    } else {
      uni.showToast({ title: res.data.message || '添加失败', icon: 'none' })
    }
  } catch (e) {
    uni.showToast({ title: '添加失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

const deletePosition = async (id) => {
  uni.showModal({
    title: '确认删除',
    content: '确定要删除这条持仓记录吗？',
    success: async (res) => {
      if (res.confirm) {
        loading.value = true
        try {
          const res = await uni.request({
            url: 'http://localhost:8000/api/v1/account/positions/' + id,
            method: 'DELETE'
          })
          
          if (res.data.code === 200) {
            uni.showToast({ title: '删除成功', icon: 'success' })
            loadData()
          } else {
            uni.showToast({ title: '删除失败', icon: 'none' })
          }
        } catch (e) {
          uni.showToast({ title: '删除失败', icon: 'none' })
        } finally {
          loading.value = false
        }
      }
    }
  })
}

const loadData = async () => {
  loading.value = true
  try {
    const [profileRes, statusRes, posRes] = await Promise.all([
      accountApi.profile(),
      accountApi.status(),
      accountApi.positions()
    ])
    profile.value = profileRes.data
    status.value = statusRes.data.data
    positions.value = posRes.data.data.positions || []
  } catch (e) {
    console.error('加载失败', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.page { padding: 10px; }

.card { background: #fff; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.card-title { font-size: 16px; font-weight: bold; }

.add-btn { color: #409eff; font-size: 14px; }

.account-info { display: flex; flex-direction: column; }
.info-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f5f5f5; }
.info-label { color: #999; }
.info-value { font-weight: bold; }

.status-content { text-align: center; }
.status-tag { display: inline-block; padding: 5px 20px; border-radius: 15px; font-size: 16px; margin-bottom: 15px; }
.tag-success { background: #e1f3d8; color: #67c23a; }
.tag-danger { background: #fef0f0; color: #f56c6c; }

.status-info { display: flex; flex-direction: column; }
.status-row { display: flex; justify-content: space-between; padding: 8px 0; }
.status-label { color: #999; }
.status-value { font-weight: bold; }

.position-list { display: flex; flex-direction: column; }
.position-item { padding: 12px 0; border-bottom: 1px solid #f5f5f5; }
.position-header { display: flex; justify-content: space-between; align-items: center; }
.position-info { display: flex; flex-direction: column; }
.position-name { font-weight: bold; }
.position-code { font-size: 12px; color: #999; }
.position-right { display: flex; align-items: center; gap: 8px; }
.position-pnl { font-size: 16px; font-weight: bold; }
.t1-tag { font-size: 10px; padding: 2px 6px; background: #fdf6ec; color: #e6a23c; border-radius: 4px; }

.position-detail { margin-top: 10px; padding: 10px; background: #f9f9f9; border-radius: 8px; }
.detail-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #eee; }
.detail-row:last-child { border-bottom: none; }
.detail-label { font-size: 12px; color: #999; }
.detail-value { font-size: 14px; color: #333; }

.delete-btn { margin-top: 10px; padding: 8px; text-align: center; color: #f56c6c; border: 1px solid #f56c6c; border-radius: 4px; font-size: 14px; }

/* 弹窗样式 */
.modal-mask { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 100; display: flex; align-items: center; justify-content: center; }
.modal-content { background: #fff; border-radius: 8px; width: 85%; max-height: 80%; overflow: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #eee; }
.modal-title { font-size: 18px; font-weight: bold; }
.modal-close { font-size: 24px; color: #999; }
.modal-body { padding: 15px; }

.form-item { margin-bottom: 15px; }
.form-label { display: block; font-size: 14px; color: #666; margin-bottom: 5px; }
.form-input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
.form-value { font-size: 14px; color: #999; }
.picker-value { padding: 10px; border: 1px solid #ddd; border-radius: 4px; color: #333; }

.form-actions { display: flex; gap: 10px; margin-top: 20px; }
.btn-cancel, .btn-confirm { flex: 1; padding: 12px; text-align: center; border-radius: 4px; font-size: 14px; }
.btn-cancel { background: #f5f5f5; color: #666; }
.btn-confirm { background: #409eff; color: #fff; }

.loading { text-align: center; padding: 30px; color: #999; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
.text-orange { color: #e6a23c; }
</style>
