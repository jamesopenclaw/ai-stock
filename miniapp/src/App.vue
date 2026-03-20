<template>
  <view class="app-container">
    <view class="tab-bar">
      <view 
        v-for="tab in tabs" 
        :key="tab.path" 
        :class="['tab-item', currentPath === tab.path ? 'active' : '']"
        @click="switchTab(tab.path)"
      >
        <text class="tab-icon">{{ tab.icon }}</text>
        <text class="tab-text">{{ tab.name }}</text>
      </view>
    </view>
    <view class="page-content">
      <Index v-if="currentPath === '/'" />
      <Market v-else-if="currentPath === '/market'" />
      <Sectors v-else-if="currentPath === '/sectors'" />
      <Pools v-else-if="currentPath === '/pools'" />
      <Buy v-else-if="currentPath === '/buy'" />
      <Sell v-else-if="currentPath === '/sell'" />
      <Account v-else-if="currentPath === '/account'" />
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import Index from './pages/index/index.vue'
import Market from './pages/market/market.vue'
import Sectors from './pages/sectors/sectors.vue'
import Pools from './pages/pools/pools.vue'
import Buy from './pages/buy/buy.vue'
import Sell from './pages/sell/sell.vue'
import Account from './pages/account/account.vue'

const currentPath = ref('/')

const tabs = [
  { name: '首页', path: '/', icon: '🏠' },
  { name: '市场', path: '/market', icon: '📊' },
  { name: '板块', path: '/sectors', icon: '🔥' },
  { name: '三池', path: '/pools', icon: '🏊' },
  { name: '买点', path: '/buy', icon: '💰' },
  { name: '卖点', path: '/sell', icon: '📉' },
  { name: '账户', path: '/account', icon: '💳' },
]

const switchTab = (path) => {
  currentPath.value = path
}
</script>

<style>
page {
  background-color: #f5f5f5;
}

.app-container {
  min-height: 100vh;
  padding-bottom: 50px;
}

.tab-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  background-color: #fff;
  border-top: 1px solid #eee;
  z-index: 100;
}

.tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  font-size: 12px;
  color: #666;
}

.tab-item.active {
  color: #409eff;
}

.tab-icon {
  font-size: 20px;
  margin-bottom: 2px;
}

.page-content {
  padding: 10px;
}
</style>
