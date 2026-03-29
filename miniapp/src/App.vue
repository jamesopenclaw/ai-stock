<template>
  <view class="app-container">
    <view v-if="!loggedIn" class="login-screen">
      <view class="login-card">
        <text class="login-title">轻舟交易系统</text>
        <text class="login-subtitle">迭代一先落地登录能力，小程序先接入基础认证。</text>
        <input v-model="loginForm.username" class="login-input" placeholder="用户名" />
        <input v-model="loginForm.password" class="login-input" password placeholder="密码" />
        <button class="login-button" :disabled="loginLoading" @click="handleLogin">
          {{ loginLoading ? '登录中...' : '登录' }}
        </button>
      </view>
    </view>
    <template v-else>
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
    </template>
  </view>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import Index from './pages/index/index.vue'
import Market from './pages/market/market.vue'
import Sectors from './pages/sectors/sectors.vue'
import Pools from './pages/pools/pools.vue'
import Buy from './pages/buy/buy.vue'
import Sell from './pages/sell/sell.vue'
import Account from './pages/account/account.vue'
import { authApi } from './api'
import { authState, clearSession, setSession } from './auth'

const currentPath = ref('/')
const loginLoading = ref(false)
const loginForm = reactive({
  username: '',
  password: '',
})
const loggedIn = computed(() => Boolean(authState.accessToken))

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

const handleLogin = async () => {
  if (!loginForm.username.trim() || !loginForm.password) {
    uni.showToast({ title: '请输入用户名和密码', icon: 'none' })
    return
  }

  loginLoading.value = true
  try {
    const response = await authApi.login({
      username: loginForm.username.trim(),
      password: loginForm.password,
    })
    const payload = response.data || {}
    setSession({
      accessToken: payload.access_token || '',
      refreshToken: payload.refresh_token || '',
      user: payload.user || null,
      account: payload.account || null,
    })
    uni.showToast({ title: '登录成功', icon: 'success' })
  } catch (error) {
    const message = error.data?.message || '登录失败'
    uni.showToast({ title: message, icon: 'none' })
  } finally {
    loginLoading.value = false
  }
}

const hydrateSession = async () => {
  if (!authState.accessToken) {
    return
  }
  try {
    const response = await authApi.me()
    const payload = response.data || {}
    setSession({
      accessToken: authState.accessToken,
      refreshToken: authState.refreshToken,
      user: payload.user || null,
      account: payload.account || null,
    })
  } catch {
    clearSession()
  }
}

onMounted(() => {
  hydrateSession()
})
</script>

<style>
page {
  background-color: #f5f5f5;
}

.app-container {
  min-height: 100vh;
  padding-bottom: 50px;
}

.login-screen {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32rpx;
  background: linear-gradient(135deg, #101521 0%, #182033 48%, #101521 100%);
}

.login-card {
  width: 100%;
  max-width: 640rpx;
  padding: 40rpx 36rpx;
  border-radius: 28rpx;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 20rpx 60rpx rgba(0, 0, 0, 0.18);
}

.login-title {
  display: block;
  margin-bottom: 16rpx;
  font-size: 40rpx;
  font-weight: 700;
  color: #111827;
}

.login-subtitle {
  display: block;
  margin-bottom: 32rpx;
  font-size: 26rpx;
  line-height: 1.6;
  color: #6b7280;
}

.login-input {
  width: 100%;
  height: 88rpx;
  margin-bottom: 20rpx;
  padding: 0 24rpx;
  border: 1px solid #dbe2ea;
  border-radius: 18rpx;
  background: #fff;
  box-sizing: border-box;
}

.login-button {
  width: 100%;
  margin-top: 8rpx;
  border-radius: 18rpx;
  background: #2962ff;
  color: #fff;
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
