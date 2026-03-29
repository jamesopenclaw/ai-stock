<template>
  <div class="dashboard">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="summary-card">
          <template #header>
            <div class="card-header">
              <span>今日执行摘要</span>
              <el-button type="primary" @click="refreshData()" :loading="refreshing">
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

    <el-row :gutter="20" style="margin-top: 20px;" class="equal-height">
      <el-col :span="8">
        <el-card class="fill-card market-card">
          <template #header>
            <span>市场环境</span>
          </template>
          <div v-if="marketEnv" class="market-env">
            <div class="market-env-tag-wrap">
              <el-tag
                class="market-env-tag"
                :type="getEnvTagType(marketEnv.market_env_tag)"
                effect="dark"
                size="large"
              >
                {{ marketEnv.market_env_tag }}
              </el-tag>
            </div>
            <p class="market-env-comment">{{ marketEnv.market_comment }}</p>
            <div class="env-detail">
              <div>突破允许: {{ marketEnv.breakout_allowed ? '是' : '否' }}</div>
              <div>风险等级: {{ marketEnv.risk_level }}</div>
            </div>
          </div>
          <el-skeleton v-else :rows="3" animated class="fill-skeleton" />
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="fill-card sector-card">
          <template #header>
            <span>主线板块</span>
          </template>
          <div v-if="leaderSector" class="leader-sector">
            <div class="sector-name">{{ leaderSector.sector.sector_name }}</div>
            <div class="sector-change">{{ leaderSector.sector.sector_change_pct }}%</div>
            <el-tag size="small">{{ leaderSector.sector.sector_mainline_tag }}</el-tag>
          </div>
          <el-skeleton v-else :rows="3" animated class="fill-skeleton" />
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="fill-card account-card">
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
          <el-skeleton v-else :rows="3" animated class="fill-skeleton" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>分层复盘统计</span>
          </template>
          <el-skeleton v-if="loadingState.reviewStats && !reviewStats" :rows="4" animated />
          <el-empty v-else-if="!reviewStats?.bucket_stats?.length" description="暂无复盘快照" />
          <el-table v-else :data="reviewStats.bucket_stats.slice(0, 8)" style="width: 100%">
            <el-table-column prop="snapshot_type" label="类型" width="100" />
            <el-table-column prop="candidate_bucket_tag" label="分层" width="120" />
            <el-table-column prop="count" label="出现次数" width="100" />
            <el-table-column prop="avg_return_1d" label="1日均值" width="90" />
            <el-table-column prop="avg_return_3d" label="3日均值" width="90" />
            <el-table-column prop="avg_return_5d" label="5日均值" width="90" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px;" class="equal-height">
      <el-col :span="12">
        <el-card class="fill-card dashboard-bottom-card">
          <template #header>
            <span>可买候选 ({{ buyPoints?.available_buy_points?.length || 0 }})</span>
          </template>
          <div class="bottom-card-body">
            <el-skeleton v-if="loadingState.buyPoints && !buyPoints" :rows="5" animated class="fill-skeleton" />
            <el-empty v-else-if="!buyPoints?.available_buy_points?.length" description="暂无可买候选" />
            <el-table v-else :data="buyPoints.available_buy_points.slice(0, 5)" style="width: 100%">
              <el-table-column prop="ts_code" label="代码" width="100" />
              <el-table-column prop="stock_name" label="名称" width="100" />
              <el-table-column prop="candidate_bucket_tag" label="分层" width="100" />
              <el-table-column prop="buy_point_type" label="买点类型" width="100" />
              <el-table-column prop="buy_risk_level" label="风险" width="80" />
            </el-table>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="fill-card dashboard-bottom-card">
          <template #header>
            <span>持仓处理 ({{ (sellPoints?.sell_positions?.length || 0) + (sellPoints?.reduce_positions?.length || 0) }})</span>
          </template>
          <div class="bottom-card-body">
            <el-skeleton v-if="loadingState.sellPoints && !sellPoints" :rows="5" animated class="fill-skeleton" />
            <el-empty
              v-else-if="!sellPoints?.sell_positions?.length && !sellPoints?.reduce_positions?.length"
              description="暂无卖出/减仓信号"
            />
            <el-table v-else :data="sellPoints?.sell_positions?.slice(0, 5)" style="width: 100%">
              <el-table-column prop="ts_code" label="代码" width="100" />
              <el-table-column prop="stock_name" label="名称" width="100" />
              <el-table-column prop="sell_signal_tag" label="信号" width="80" />
              <el-table-column prop="sell_point_type" label="类型" width="100" />
            </el-table>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { decisionApi, marketApi, sectorApi, accountApi } from '../api'
import { ElMessage } from 'element-plus'

const summary = ref(null)
const marketEnv = ref(null)
const leaderSector = ref(null)
const accountProfile = ref(null)
const buyPoints = ref(null)
const sellPoints = ref(null)
const reviewStats = ref(null)
const loadingState = ref({
  summary: false,
  marketEnv: false,
  leaderSector: false,
  accountProfile: false,
  buyPoints: false,
  sellPoints: false,
  reviewStats: false,
})
const refreshVersion = ref(0)

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

const DASHBOARD_REQUEST_TIMEOUT = 90000
const DASHBOARD_BUY_POINT_LIMIT = 10
const DASHBOARD_CACHE_KEY = 'dashboard_snapshot_v1'

const refreshing = computed(() => Object.values(loadingState.value).some(Boolean))

const getTradeDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const setModuleLoading = (key, value) => {
  loadingState.value = {
    ...loadingState.value,
    [key]: value
  }
}

const isAbortedRequest = (error) => {
  const code = String(error?.code || '')
  const message = String(error?.message || '').toLowerCase()
  return (
    code === 'ERR_CANCELED'
    || message.includes('request aborted')
    || message.includes('aborted')
    || message.includes('canceled')
  )
}

const persistDashboardCache = () => {
  if (typeof window === 'undefined') return
  const payload = {
    summary: summary.value,
    marketEnv: marketEnv.value,
    leaderSector: leaderSector.value,
    accountProfile: accountProfile.value,
    buyPoints: buyPoints.value,
    sellPoints: sellPoints.value,
    reviewStats: reviewStats.value,
    updatedAt: Date.now()
  }
  window.sessionStorage.setItem(DASHBOARD_CACHE_KEY, JSON.stringify(payload))
}

const hydrateDashboardCache = () => {
  if (typeof window === 'undefined') return false
  const raw = window.sessionStorage.getItem(DASHBOARD_CACHE_KEY)
  if (!raw) return false
  try {
    const payload = JSON.parse(raw)
    summary.value = payload.summary || null
    marketEnv.value = payload.marketEnv || null
    leaderSector.value = payload.leaderSector || null
    accountProfile.value = payload.accountProfile || null
    buyPoints.value = payload.buyPoints || null
    sellPoints.value = payload.sellPoints || null
    reviewStats.value = payload.reviewStats || null
    return true
  } catch (error) {
    window.sessionStorage.removeItem(DASHBOARD_CACHE_KEY)
    return false
  }
}

const refreshData = async ({ silent = false } = {}) => {
  const version = refreshVersion.value + 1
  refreshVersion.value = version
  try {
    const tradeDate = getTradeDate()
    const failedModules = []

    const loadModule = async (key, label, loader, assign) => {
      setModuleLoading(key, true)
      try {
        const res = await loader()
        if (refreshVersion.value !== version) return
        assign(res.data.data)
      } catch (error) {
        if (isAbortedRequest(error)) {
          return
        }
        console.error(`${label}加载失败:`, error)
        if (refreshVersion.value === version) {
          failedModules.push(label)
        }
      } finally {
        if (refreshVersion.value === version) {
          setModuleLoading(key, false)
        }
      }
    }

    await Promise.allSettled([
      loadModule(
      'marketEnv',
      '市场环境',
      () => marketApi.getEnv(tradeDate, { timeout: DASHBOARD_REQUEST_TIMEOUT }),
      (data) => {
        marketEnv.value = data
      }
    ),
      loadModule(
      'summary',
      '执行摘要',
      () => decisionApi.summary(tradeDate, { timeout: DASHBOARD_REQUEST_TIMEOUT }),
      (data) => {
        summary.value = data
      }
    ),
      loadModule(
      'leaderSector',
      '主线板块',
      () => sectorApi.leader(tradeDate, { timeout: DASHBOARD_REQUEST_TIMEOUT }),
      (data) => {
        leaderSector.value = data
      }
    ),
      loadModule(
      'accountProfile',
      '账户概况',
      () => accountApi.profile({ timeout: DASHBOARD_REQUEST_TIMEOUT }),
      (data) => {
        accountProfile.value = data
      }
    ),
      loadModule(
      'buyPoints',
      '可买候选',
      () => decisionApi.buyPoint(tradeDate, DASHBOARD_BUY_POINT_LIMIT, { timeout: DASHBOARD_REQUEST_TIMEOUT }),
      (data) => {
        buyPoints.value = data
      }
    ),
      loadModule(
      'sellPoints',
      '持仓处理',
      () => decisionApi.sellPoint(tradeDate, {
        includeLlm: false,
        timeout: DASHBOARD_REQUEST_TIMEOUT
      }),
      (data) => {
        sellPoints.value = data
      }
    ),
      loadModule(
      'reviewStats',
      '复盘统计',
      () => decisionApi.reviewStats(10, { timeout: DASHBOARD_REQUEST_TIMEOUT }),
      (data) => {
        reviewStats.value = data
      }
    )])

    if (refreshVersion.value !== version) return

    if ([summary.value, marketEnv.value, leaderSector.value, accountProfile.value, buyPoints.value, sellPoints.value, reviewStats.value].some(Boolean)) {
      persistDashboardCache()
    }

    if (failedModules.length === 7) {
      throw new Error('全部接口加载失败')
    }

    if (failedModules.length && !silent) {
      ElMessage.warning(`部分数据加载失败：${failedModules.join('、')}`)
    } else if (!failedModules.length && !silent) {
      ElMessage.success('数据刷新成功')
    }
  } catch (error) {
    console.error('刷新数据失败:', error)
    if (!silent) {
      ElMessage.error('数据加载失败')
    }
  }
}

onMounted(() => {
  hydrateDashboardCache()
  refreshData({ silent: true })
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

/* 同一行内卡片等高 */
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
  width: 100%;
}
.fill-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.fill-skeleton {
  flex: 1;
  width: 100%;
}

.summary-item {
  text-align: center;
}

.summary-item .label {
  font-size: 14px;
  color: var(--color-text-sec);
  margin-bottom: 8px;
}

.summary-item .value {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-pri);
}
.summary-item .value.text-red {
  color: var(--color-up);
}
.summary-item .value.text-green {
  color: var(--color-down);
}
.summary-item .value.text-yellow {
  color: var(--color-neutral);
}

.summary-focus, .summary-avoid {
  padding: 12px 14px;
  background: var(--color-hover);
  border-radius: 6px;
  border: 1px solid var(--color-border);
}

.summary-focus .label, .summary-avoid .label {
  font-weight: bold;
  color: var(--color-primary);
}

/* 市场环境：主标签加大（进攻/防守/中性） */
.market-env {
  text-align: center;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.market-env-tag-wrap {
  flex-shrink: 0;
  padding: 4px 0 8px;
}
.market-env :deep(.market-env-tag.el-tag) {
  font-size: clamp(1.35rem, 3vw, 2rem);
  font-weight: 700;
  line-height: 1.2;
  height: auto;
  padding: 14px 28px;
  border-radius: 10px;
  letter-spacing: 0.06em;
}
.market-env-comment {
  flex: 1;
  margin: 12px 0;
  color: var(--color-text-sec);
  text-align: left;
  line-height: 1.55;
  font-size: 14px;
}

.env-detail {
  display: flex;
  justify-content: space-around;
  font-size: 14px;
  color: var(--color-text-sec);
  flex-shrink: 0;
  padding-top: 4px;
  border-top: 1px solid var(--color-border);
}

.leader-sector {
  text-align: center;
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 0;
}

.sector-name {
  font-size: 20px;
  font-weight: bold;
  margin-bottom: 10px;
}

.sector-change {
  font-size: 24px;
  color: var(--color-up);
  margin-bottom: 10px;
}

.account-profile {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 0;
}
.account-profile .profile-item {
  padding: 10px 0;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.account-profile .profile-item:last-child {
  border-bottom: none;
}

.account-profile .label {
  color: var(--color-text-sec);
  flex-shrink: 0;
}

.account-profile .value {
  font-weight: bold;
  text-align: right;
}

/* 底部两栏：空状态与表格同高对齐 */
.dashboard-bottom-card .bottom-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.dashboard-bottom-card .bottom-card-body :deep(.el-empty) {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 32px 16px;
}
.dashboard-bottom-card .bottom-card-body :deep(.el-table) {
  flex: 1;
}
</style>
