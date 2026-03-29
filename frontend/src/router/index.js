import { createRouter, createWebHistory } from 'vue-router'
import { authState, isAuthenticated } from '../auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    meta: { title: '登录', requiresAuth: false },
    component: () => import('../views/Login.vue')
  },
  {
    path: '/',
    name: 'Dashboard',
    meta: { title: 'Dashboard' },
    component: () => import('../views/Dashboard.vue')
  },
  {
    path: '/market',
    name: 'Market',
    meta: { title: '市场环境' },
    component: () => import('../views/Market.vue')
  },
  {
    path: '/sectors',
    name: 'Sectors',
    meta: { title: '板块扫描' },
    component: () => import('../views/Sectors.vue')
  },
  {
    path: '/pools',
    name: 'Pools',
    meta: { title: '三池分类' },
    component: () => import('../views/Pools.vue')
  },
  {
    path: '/buy',
    name: 'Buy',
    meta: { title: '买点分析' },
    component: () => import('../views/BuyPoint.vue')
  },
  {
    path: '/sell',
    name: 'Sell',
    meta: { title: '卖点分析' },
    component: () => import('../views/SellPoint.vue')
  },
  {
    path: '/account',
    name: 'Account',
    meta: { title: '账户管理' },
    component: () => import('../views/Account.vue')
  },
  {
    path: '/review',
    name: 'Review',
    meta: { title: '复盘统计' },
    component: () => import('../views/ReviewStats.vue')
  },
  {
    path: '/system',
    name: 'SystemSettings',
    meta: { title: '系统设置', adminOnly: true },
    component: () => import('../views/SystemSettings.vue')
  },
  {
    path: '/llm-logs',
    name: 'LlmLogs',
    meta: { title: 'LLM调用记录' },
    component: () => import('../views/LlmLogs.vue')
  },
  {
    path: '/tasks',
    name: 'TaskRuns',
    meta: { title: '任务调度', adminOnly: true },
    component: () => import('../views/TaskRuns.vue')
  },
  {
    path: '/admin/users',
    name: 'AdminUsers',
    meta: { title: '用户管理', adminOnly: true },
    component: () => import('../views/AdminUsers.vue')
  },
  {
    path: '/admin/accounts',
    name: 'AdminAccounts',
    meta: { title: '交易账户', adminOnly: true },
    component: () => import('../views/AdminAccounts.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const requiresAuth = to.meta.requiresAuth !== false
  if (!requiresAuth) {
    if (to.path === '/login' && isAuthenticated()) {
      return '/'
    }
    return true
  }

  if (isAuthenticated()) {
    if (to.meta.adminOnly && authState.user?.role !== 'admin') {
      return '/'
    }
    return true
  }

  return {
    path: '/login',
    query: { redirect: to.fullPath }
  }
})

export default router
