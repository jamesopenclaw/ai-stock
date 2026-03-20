<template>
  <div class="sectors-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>板块扫描结果</span>
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </template>
      
      <el-tabs v-model="activeTab">
        <el-tab-pane label="主线板块" name="mainline">
          <el-table :data="scanData.mainline_sectors" style="width: 100%">
            <el-table-column prop="sector_name" label="板块名称" />
            <el-table-column prop="sector_change_pct" label="涨跌幅">
              <template #default="{ row }">
                <span :class="row.sector_change_pct > 0 ? 'text-red' : 'text-green'">
                  {{ row.sector_change_pct?.toFixed(2) }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="sector_mainline_tag" label="主线标签" />
            <el-table-column prop="sector_tradeability_tag" label="交易性" />
            <el-table-column prop="sector_comment" label="简评" />
          </el-table>
        </el-tab-pane>
        
        <el-tab-pane label="次主线" name="sub">
          <el-table :data="scanData.sub_mainline_sectors" style="width: 100%">
            <el-table-column prop="sector_name" label="板块名称" />
            <el-table-column prop="sector_change_pct" label="涨跌幅" />
            <el-table-column prop="sector_mainline_tag" label="标签" />
            <el-table-column prop="sector_tradeability_tag" label="交易性" />
          </el-table>
        </el-tab-pane>
        
        <el-tab-pane label="跟风板块" name="follow">
          <el-table :data="scanData.follow_sectors" style="width: 100%">
            <el-table-column prop="sector_name" label="板块名称" />
            <el-table-column prop="sector_change_pct" label="涨跌幅" />
            <el-table-column prop="sector_tradeability_tag" label="交易性" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { sectorApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const activeTab = ref('mainline')
const scanData = ref({ mainline_sectors: [], sub_mainline_sectors: [], follow_sectors: [] })

const loadData = async () => {
  loading.value = true
  try {
    const tradeDate = new Date().toISOString().split('T')[0]
    const res = await sectorApi.scan(tradeDate)
    scanData.value = res.data.data
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
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
</style>
