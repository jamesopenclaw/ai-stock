<template>
  <el-container class="app-container">
    <el-aside width="200px">
      <div class="logo">
        <h3>轻舟交易系统</h3>
      </div>
      <el-menu
        :default-active="route.path"
        router
        class="el-menu-vertical"
      >
        <el-menu-item index="/">
          <el-icon><House /></el-icon>
          <span>Dashboard</span>
        </el-menu-item>
        <el-menu-item index="/market">
          <el-icon><TrendCharts /></el-icon>
          <span>市场环境</span>
        </el-menu-item>
        <el-menu-item index="/sectors">
          <el-icon><Grid /></el-icon>
          <span>板块扫描</span>
        </el-menu-item>
        <el-menu-item index="/pools">
          <el-icon><List /></el-icon>
          <span>三池分类</span>
        </el-menu-item>
        <el-menu-item index="/buy">
          <el-icon><Plus /></el-icon>
          <span>买点分析</span>
        </el-menu-item>
        <el-menu-item index="/sell">
          <el-icon><Minus /></el-icon>
          <span>卖点分析</span>
        </el-menu-item>
        <el-menu-item index="/account">
          <el-icon><Wallet /></el-icon>
          <span>账户管理</span>
        </el-menu-item>
        <el-menu-item index="/review">
          <el-icon><DataAnalysis /></el-icon>
          <span>复盘统计</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header>
        <div class="header-title">
          <span>{{ route.meta.title }}</span>
        </div>
        <div class="header-right">
          <el-tag>{{ currentDate }}</el-tag>
        </div>
      </el-header>
      
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'

const route = useRoute()
const currentDate = ref(dayjs().format('YYYY-MM-DD'))

onMounted(() => {
  setInterval(() => {
    currentDate.value = dayjs().format('YYYY-MM-DD HH:mm')
  }, 60000)
})
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

.logo h3 {
  color: var(--color-text-pri);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

/* 导航菜单 */
.el-menu-vertical {
  border-right: none;
  background-color: var(--color-card);
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
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-pri);
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
