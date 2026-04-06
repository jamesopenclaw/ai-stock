<template>
  <router-view v-if="!showShell" />
  <el-container v-else class="app-container">
    <el-aside width="200px">
      <div class="logo">
        <div class="logo-copy">
          <h3>轻舟交易系统</h3>
          <span>交易工作台</span>
        </div>
      </div>
      <el-menu
        :default-active="route.path"
        router
        class="el-menu-vertical"
      >
        <el-menu-item-group
          v-for="group in visibleMenuGroups"
          :key="group.key"
        >
          <template #title>
            <span class="menu-group-title">{{ group.label }}</span>
          </template>
          <el-menu-item
            v-for="item in group.items"
            :key="item.path"
            :index="item.path"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </el-menu-item>
        </el-menu-item-group>
      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header>
        <div class="header-title">
          <el-tag size="small" effect="plain" class="header-mode-tag">{{ currentGroupLabel }}</el-tag>
          <span>{{ route.meta.title }}</span>
        </div>
        <div class="header-right">
          <div class="header-user" v-if="currentUser">
            <el-tag type="info">{{ currentUser.display_name || currentUser.username }}</el-tag>
            <el-tag :type="currentUser.role === 'admin' ? 'danger' : 'success'">
              {{ currentUser.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
            <el-select
              v-if="isAdmin && accountOptions.length"
              v-model="selectedAccountId"
              class="account-switcher"
              placeholder="选择查看账户"
              :loading="switchingAccount"
              @change="handleAccountSwitch"
            >
              <el-option
                v-for="account in accountOptions"
                :key="account.id"
                :label="`${account.account_name} (${account.account_code})`"
                :value="account.id"
              />
            </el-select>
            <div v-else-if="currentAccount" class="current-account">
              <span class="current-account-label">
                {{ isAdmin ? '当前账户' : '我的账户' }}
              </span>
              <el-tag type="warning" effect="plain">
                {{ currentAccount.account_name }}
              </el-tag>
            </div>
          </div>
          <NotificationBell
            v-if="currentAccount"
            :unread-count="notificationSummary.unread_count"
            :critical-count="notificationSummary.critical_count"
            @open="notificationCenterVisible = true"
          />
          <el-tag>{{ currentDate }}</el-tag>
          <el-button type="danger" plain size="small" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      
      <el-main>
        <router-view />
      </el-main>
      <NotificationCenter
        v-model="notificationCenterVisible"
      />
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage, ElNotification } from 'element-plus'
import {
  Avatar,
  DataAnalysis,
  Grid,
  House,
  List,
  Minus,
  Operation,
  Plus,
  Setting,
  Tickets,
  TrendCharts,
  UserFilled,
  Wallet,
} from '@element-plus/icons-vue'
import NotificationBell from './components/NotificationBell.vue'
import NotificationCenter from './components/NotificationCenter.vue'
import { adminApi, authApi } from './api'
import { authState, clearSession, getRefreshToken, setCurrentAccount, setSession } from './auth'
import { useNotificationStore } from './stores/notificationStore'

const route = useRoute()
const router = useRouter()
const currentDate = ref(dayjs().format('YYYY-MM-DD'))
const accountOptions = ref([])
const switchingAccount = ref(false)
const selectedAccountId = ref('')
const notificationCenterVisible = ref(false)
const notificationInitialized = ref(false)
let clockTimer = null
let notificationPollTimer = null
const notificationStore = useNotificationStore()
const notificationSummary = computed(() => notificationStore.summary.value)
const currentUser = computed(() => authState.user)
const currentAccount = computed(() => authState.account)
const isAdmin = computed(() => currentUser.value?.role === 'admin')
const showShell = computed(() => route.meta.requiresAuth !== false)
const menuGroups = [
  {
    key: 'trade',
    label: '交易决策',
    items: [
      { path: '/', label: '今日指令', icon: House },
      { path: '/market', label: '市场环境', icon: TrendCharts },
      { path: '/sectors', label: '板块扫描', icon: Grid },
      { path: '/pools', label: '三池分类', icon: List },
      { path: '/buy', label: '买点分析', icon: Plus },
      { path: '/sell', label: '卖点分析', icon: Minus },
      { path: '/account', label: '账户管理', icon: Wallet },
      { path: '/review', label: '复盘统计', icon: DataAnalysis },
    ],
  },
  {
    key: 'admin',
    label: '系统管理',
    items: [
      { path: '/llm-logs', label: 'LLM调用记录', icon: Tickets },
      { path: '/system', label: '系统设置', icon: Setting, adminOnly: true },
      { path: '/tasks', label: '任务调度', icon: Operation, adminOnly: true },
      { path: '/admin/users', label: '用户管理', icon: UserFilled, adminOnly: true },
      { path: '/admin/accounts', label: '交易账户', icon: Avatar, adminOnly: true },
    ],
  },
]
const visibleMenuGroups = computed(() => (
  menuGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !item.adminOnly || currentUser.value?.role === 'admin'),
    }))
    .filter((group) => group.items.length)
))
const currentGroupLabel = computed(() => {
  const matchedGroup = visibleMenuGroups.value.find((group) => group.items.some((item) => item.path === route.path))
  return matchedGroup?.label || '交易工作台'
})

const syncSelectedAccount = () => {
  selectedAccountId.value = currentAccount.value?.id || ''
}

const loadAdminAccounts = async () => {
  if (!isAdmin.value) {
    accountOptions.value = []
    selectedAccountId.value = ''
    return
  }
  try {
    const response = await adminApi.listAccounts()
    accountOptions.value = (response.data?.data?.accounts || []).filter((account) => account.status === 'active')
    syncSelectedAccount()
  } catch {
    accountOptions.value = []
  }
}

const loadCurrentUser = async () => {
  if (!authState.accessToken) {
    return
  }
  try {
    const response = await authApi.me()
    const user = response.data?.data?.user || null
    const account = response.data?.data?.account || null
    if (user) {
      setSession({
        accessToken: authState.accessToken,
        refreshToken: authState.refreshToken,
        user,
        account,
      })
    }
  } catch {
    // 401 交给 axios 拦截器统一处理
  }
}

const handleAccountSwitch = (accountId) => {
  const nextAccount = accountOptions.value.find((account) => account.id === accountId)
  if (!nextAccount || nextAccount.id === currentAccount.value?.id) {
    syncSelectedAccount()
    return
  }
  switchingAccount.value = true
  setCurrentAccount(nextAccount)
  ElMessage.success(`已切换到 ${nextAccount.account_name}`)
  window.location.reload()
}

const handleLogout = async () => {
  const refreshToken = getRefreshToken()
  try {
    if (refreshToken) {
      await authApi.logout(refreshToken)
    }
  } catch {
    // 忽略服务端注销失败，仍清理本地状态
  } finally {
    clearSession()
    ElMessage.success('已退出登录')
    router.replace('/login')
  }
}

const stopNotificationPolling = () => {
  if (!notificationPollTimer) return
  window.clearTimeout(notificationPollTimer)
  notificationPollTimer = null
}

const scheduleNotificationPolling = () => {
  stopNotificationPolling()
  if (typeof window === 'undefined' || !showShell.value || !currentAccount.value?.id) return
      notificationPollTimer = window.setTimeout(async () => {
    await loadNotificationSummary()
    scheduleNotificationPolling()
  }, notificationCenterVisible.value ? 10000 : 25000)
}

const loadNotificationSummary = async ({ refresh = false } = {}) => {
  if (!currentAccount.value?.id || !showShell.value) {
    notificationStore.resetState()
    return
  }
  try {
    const previousCriticalCount = Number(notificationSummary.value.critical_count || 0)
    const payload = await notificationStore.loadSummary({ force: refresh })

    if (
      notificationInitialized.value
      && Number(payload.critical_count || 0) > previousCriticalCount
      && payload.latest_items.length
      && !payload.quiet_window_active
    ) {
      const latest = payload.latest_items[0]
      ElNotification({
        title: latest.title || '新的高优先级提醒',
        message: latest.message || '有新的盘中待处理事项',
        type: 'warning',
        duration: 5000,
      })
    }
    notificationInitialized.value = true
  } catch {
    // 避免顶栏轮询把页面打满错误提示
  }
}

onMounted(() => {
  loadCurrentUser()
  clockTimer = window.setInterval(() => {
    currentDate.value = dayjs().format('YYYY-MM-DD HH:mm')
  }, 60000)
})

onBeforeUnmount(() => {
  if (clockTimer) {
    window.clearInterval(clockTimer)
    clockTimer = null
  }
  stopNotificationPolling()
})

watch(
  () => currentUser.value?.role,
  () => {
    loadAdminAccounts()
    syncSelectedAccount()
  },
  { immediate: true }
)

watch(
  () => currentAccount.value?.id,
  () => {
    syncSelectedAccount()
    notificationInitialized.value = false
    notificationStore.ensureAccountScope()
    loadNotificationSummary({ refresh: true })
    scheduleNotificationPolling()
  },
  { immediate: true }
)

watch(
  () => [showShell.value, notificationCenterVisible.value],
  () => {
    scheduleNotificationPolling()
  },
  { immediate: true }
)
</script>

<style>
/* TradingView 风格暗色终端 — 与 Element Plus dark 对齐 */
:root {
  --color-bg:       #131722;
  --color-card:     #1e222d;
  --color-hover:    #2a2e39;
  --color-sidebar:  var(--color-card);
  --color-header:   var(--color-card);
  --color-border:   #2a2e39;
  --color-text-pri: #d1d4dc;
  --color-text-sec: #787b86;
  --color-brand:    #e02020;
  --color-primary:  #2962ff;
  --color-up:       #f23645;
  --color-down:     #089981;
  --color-neutral:  #d4a017;
  --shadow-card:    0 2px 8px rgba(0, 0, 0, 0.4);
}

/* 与 EP 暗色主题融合 */
html.dark {
  color-scheme: dark;
  --el-bg-color-page: #131722;
  --el-bg-color: #1e222d;
  --el-bg-color-overlay: #1e222d;
  --el-fill-color-blank: #131722;
  --el-fill-color-light: #2a2e39;
  --el-fill-color: #2a2e39;
  --el-border-color: #2a2e39;
  --el-border-color-light: #363a45;
  --el-text-color-primary: #d1d4dc;
  --el-text-color-regular: #a3a6af;
  --el-text-color-secondary: #787b86;
  --el-text-color-placeholder: #787b86;
  --el-color-primary: #2962ff;
}

html,
body {
  background-color: var(--color-bg);
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.app-container {
  height: 100vh;
}

/* 侧边栏 */
.el-aside {
  background-color: var(--color-card);
  border-right: 1px solid var(--color-border);
}

/* Logo：深底 + 左侧品牌红条 */
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-card);
  border-left: 4px solid var(--color-brand);
  border-bottom: 1px solid var(--color-border);
}

.logo-copy {
  display: grid;
  gap: 2px;
  justify-items: center;
}

.logo h3 {
  color: var(--color-text-pri);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.logo span {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

/* 导航菜单 */
.el-menu-vertical {
  border-right: none;
  background-color: var(--color-card);
}

.menu-group-title {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.el-menu-item {
  color: #a3a6af !important;
  font-size: 14px;
}

.el-menu-item:hover {
  color: var(--color-text-pri) !important;
  background-color: var(--color-hover) !important;
}

.el-menu-item.is-active {
  color: var(--color-primary) !important;
  background-color: var(--color-hover) !important;
  box-shadow: inset 3px 0 0 var(--color-primary);
}

/* 顶部 Header */
.el-header {
  background-color: var(--color-card);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  border-bottom: 1px solid var(--color-border);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-pri);
}

.header-mode-tag {
  border-color: rgba(41, 98, 255, 0.35);
  color: #8ab4ff;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.account-switcher {
  width: 240px;
}

.header-user {
  display: flex;
  align-items: center;
  gap: 8px;
}

.current-account {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.current-account-label {
  font-size: 12px;
  color: var(--color-text-sec);
  white-space: nowrap;
}

/* 内容区 */
.el-main {
  background-color: var(--color-bg);
  padding: 20px;
}

/* 全局卡片 */
.el-card {
  box-shadow: var(--shadow-card) !important;
  border-color: var(--color-border) !important;
  background-color: var(--color-card) !important;
}

/* 全局颜色 token（A 股习惯：红涨绿跌） */
.text-up,
.text-red {
  color: var(--color-up);
}
.text-down,
.text-green {
  color: var(--color-down);
}
.text-neutral,
.text-yellow {
  color: var(--color-neutral);
}
</style>
