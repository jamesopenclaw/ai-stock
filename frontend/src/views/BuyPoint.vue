<template>
  <div class="buy-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>买点分析</span>
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </template>
      
      <el-alert v-if="buyData.market_env_tag" :title="`市场环境: ${buyData.market_env_tag}`" type="info" style="margin-bottom: 20px;" />
      
      <el-tabs v-model="activeTab">
        <el-tab-pane label="可买" name="available">
          <el-table :data="buyData.available_buy_points" style="width: 100%">
            <el-table-column prop="ts_code" label="代码" width="100" />
            <el-table-column prop="stock_name" label="名称" width="100" />
            <el-table-column prop="buy_point_type" label="买点类型" width="100" />
            <el-table-column prop="buy_trigger_cond" label="触发条件" />
            <el-table-column prop="buy_confirm_cond" label="确认条件" />
            <el-table-column prop="buy_invalid_cond" label="失效条件" />
            <el-table-column prop="buy_risk_level" label="风险" width="80" />
          </el-table>
        </el-tab-pane>
        
        <el-tab-pane label="观察" name="observe">
          <el-table :data="buyData.observe_buy_points" style="width: 100%">
            <el-table-column prop="ts_code" label="代码" width="100" />
            <el-table-column prop="stock_name" label="名称" width="100" />
            <el-table-column prop="buy_point_type" label="买点类型" width="100" />
            <el-table-column prop="buy_comment" label="说明" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { decisionApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const activeTab = ref('available')
const buyData = ref({ available_buy_points: [], observe_buy_points: [] })

const loadData = async () => {
  loading.value = true
  try {
    const tradeDate = new Date().toISOString().split('T')[0]
    const res = await decisionApi.buyPoint(tradeDate, 30)
    buyData.value = res.data.data
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
