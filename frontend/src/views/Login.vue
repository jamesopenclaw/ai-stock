<template>
  <div class="login-page">
    <div class="login-shell">
      <div class="login-brand">
        <span class="brand-kicker">Iteration 1</span>
        <h1>轻舟交易系统</h1>
        <p>先完成登录与权限骨架，后续再叠加多账户能力。</p>
      </div>

      <el-card class="login-card">
        <template #header>
          <div class="card-header">
            <span>账号登录</span>
            <span class="card-tip">默认管理员在后端启动时自动初始化</span>
          </div>
        </template>

        <el-form @submit.prevent>
          <el-form-item label="用户名">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              autocomplete="username"
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-form-item label="密码">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              placeholder="请输入密码"
              autocomplete="current-password"
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-button type="primary" class="login-button" :loading="loading" @click="handleLogin">
            登录
          </el-button>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { authApi } from '../api'
import { setSession } from '../auth'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
})

const handleLogin = async () => {
  if (!form.username.trim() || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }

  loading.value = true
  try {
    const response = await authApi.login({
      username: form.username.trim(),
      password: form.password,
    })
    const payload = response.data?.data || {}
    setSession({
      accessToken: payload.access_token || '',
      refreshToken: payload.refresh_token || '',
      user: payload.user || null,
      account: payload.account || null,
    })
    ElMessage.success('登录成功')
    const redirectTarget = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.replace(redirectTarget || '/')
  } catch (error) {
    const message = error.response?.data?.message || '登录失败，请检查用户名和密码'
    ElMessage.error(message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at top left, rgba(41, 98, 255, 0.18), transparent 32%),
    radial-gradient(circle at bottom right, rgba(224, 32, 32, 0.18), transparent 28%),
    linear-gradient(135deg, #101521 0%, #171d2a 48%, #111722 100%);
  padding: 24px;
}

.login-shell {
  width: 100%;
  max-width: 980px;
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 24px;
}

.login-brand {
  padding: 36px 28px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 24px;
  background: rgba(19, 23, 34, 0.72);
  backdrop-filter: blur(14px);
}

.brand-kicker {
  display: inline-block;
  margin-bottom: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(41, 98, 255, 0.16);
  color: #8ab4ff;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.login-brand h1 {
  margin: 0 0 12px;
  font-size: 40px;
  line-height: 1.05;
  color: #f5f7fb;
}

.login-brand p {
  margin: 0;
  max-width: 420px;
  color: #9ca7bb;
  font-size: 15px;
  line-height: 1.7;
}

.login-card {
  border-radius: 24px;
}

.card-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.card-tip {
  color: #787b86;
  font-size: 12px;
}

.login-button {
  width: 100%;
  margin-top: 8px;
}

@media (max-width: 900px) {
  .login-shell {
    grid-template-columns: 1fr;
  }

  .login-brand {
    padding: 28px 22px;
  }

  .login-brand h1 {
    font-size: 32px;
  }
}
</style>
