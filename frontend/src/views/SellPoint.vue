<template>
  <div class="sell-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>卖点分析</span>
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </template>
      
      <el-tabs v-model="activeTab">
        <el-tab-pane label="建议卖出" name="sell">
          <el-table :data="sellData.sell_positions" style="width: 100%">
            <el-table-column prop="ts_code" label="代码" width="100" />
            <el-table-column prop="stock_name" label="名称" width="100" />
            <el-table-column prop="sell_point_type" label="卖点类型" width="100" />
            <el-table-column prop="sell_trigger_cond" label="触发条件" />
            <el-table-column prop="sell_reason" label="原因" />
            <el-table-column prop="sell_priority" label="优先级" width="80" />
          </el-table>
        </el-tab-pane>
        
        <el-tab-pane label="建议减仓" name="reduce">
          <el-table :data="sellData.reduce_positions" style="width: 100%">
            <el-table-column prop="ts_code" label="代码" width="100" />
            <el-table-column prop="stock_name" label="名称" width="100" />
            <el-table-column prop="sell_point_type" label="类型" width="100" />
            <el-table-column prop="sell_trigger_cond" label="触发条件" />
            <el-table-column prop="sell_reason" label="原因" />
          </el-table>
        </el-tab-pane>
        
        <el-tab-pane label="持有观察" name="hold">
          <el-table :data="sellData.hold_positions" style="width: 100%">
            <el-table-column prop="ts_code" label="代码" width="100" />
            <el-table-column prop="stock_name" label="名称" width="100" />
            <el-table-column prop="sell_point_type" label="类型" width="100" />
            <el-table-column prop="sell_comment" label="说明" />
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
const activeTab = ref('sell')
const sellData = ref({ sell_positions: [], reduce_positions: [], hold_positions: [] })

const loadData = async () => {
  loading.value = true
  try {
    const tradeDate = new Date().toISOString().split('T')[0]
    const res = await decisionApi.sellPoint(tradeDate)
    sellData.value = res.data.data
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
