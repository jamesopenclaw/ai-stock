import { createRouter, createWebHistory } from 'vue-router'

const routes = [
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
    meta: { title: '系统设置' },
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
    meta: { title: '任务调度' },
    component: () => import('../views/TaskRuns.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
