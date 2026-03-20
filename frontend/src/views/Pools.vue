<template>
  <div class="pools-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>三池分类</span>
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </template>
      
      <el-tabs v-model="activeTab">
        <el-tab-pane label="市场最强观察池" name="market">
          <el-table :data="poolsData.market_watch_pool" style="width: 100%">
            <el-table-column prop="ts_code" label="代码" width="100" />
            <el-table-column prop="stock_name" label="名称" width="100" />
            <el-table-column prop="sector_name" label="板块" width="100" />
            <el-table-column prop="change_pct" label="涨跌幅" width="100">
              <template #default="{ row }">
                {{ row.change_pct?.toFixed(2) }}%
              </template>
            </el-table-column>
            <el-table-column prop="stock_core_tag" label="属性" width="80" />
            <el-table-column prop="stock_comment" label="简评" />
          </el-table>
        </el-tab-pane>
        
        <el-tab-pane label="账户可参与池" name="account">
          <el-table :data="poolsData.account_executable_pool" style="width: 100%">
            <el-table-column prop="ts_code" label="代码" width="100" />
            <el-table-column prop="stock_name" label="名称" width="100" />
            <el-table-column prop="sector_name" label="板块" width="100" />
            <el-table-column prop="stock_core_tag" label="属性" width="80" />
            <el-table-column prop="stock_tradeability_tag" label="交易性" width="100" />
          </el-table>
        </el-tab-pane>
        
        <el-tab-pane label="持仓处理池" name="holding">
          <el-table :data="poolsData.holding_process_pool" style="width: 100%">
            <el-table-column prop="ts_code" label="代码" width="100" />
            <el-table-column prop="stock_name" label="名称" width="100" />
            <el-table-column prop="sector_name" label="板块" width="100" />
            <el-table-column prop="stock_strength_tag" label="状态" width="80" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { stockApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const activeTab = ref('market')
const poolsData = ref({ market_watch_pool: [], account_executable_pool: [], holding_process_pool: [] })

const loadData = async () => {
  loading.value = true
  try {
    const tradeDate = new Date().toISOString().split('T')[0]
    const res = await stockApi.pools(tradeDate, 50)
    poolsData.value = res.data.data
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
