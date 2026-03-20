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
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.app-container {
  height: 100vh;
}

.el-aside {
  background-color: #304156;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #2b3a4a;
}

.logo h3 {
  color: #fff;
  font-size: 18px;
}

.el-menu-vertical {
  border-right: none;
  background-color: #304156;
}

.el-menu-item {
  color: #bfcbd9;
}

.el-menu-item:hover,
.el-menu-item.is-active {
  background-color: #263445 !important;
  color: #409eff !important;
}

.el-header {
  background-color: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  border-bottom: 1px solid #e6e6e6;
}

.header-title {
  font-size: 18px;
  font-weight: bold;
}

.el-main {
  background-color: #f0f2f5;
  padding: 20px;
}
</style>
