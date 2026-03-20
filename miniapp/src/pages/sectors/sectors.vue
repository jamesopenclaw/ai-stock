<template>
  <view class="page">
    <view class="card">
      <view class="card-title">板块扫描</view>
      
      <view class="tabs">
        <view 
          v-for="tab in tabs" 
          :key="tab.key" 
          :class="['tab', activeTab === tab.key ? 'active' : '']"
          @click="activeTab = tab.key"
        >
          {{ tab.name }}
        </view>
      </view>

      <view class="sector-list">
        <view v-if="activeTab === 'mainline'" v-for="item in data.mainline_sectors" :key="item.sector_name" class="sector-item">
          <view class="sector-info">
            <text class="sector-name">{{ item.sector_name }}</text>
            <text class="sector-tag">{{ item.sector_mainline_tag }}</text>
          </view>
          <view class="sector-change">
            <text :class="item.sector_change_pct > 0 ? 'text-red' : 'text-green'">
              {{ item.sector_change_pct?.toFixed(2) }}%
            </text>
          </view>
        </view>

        <view v-if="activeTab === 'sub'" v-for="item in data.sub_mainline_sectors" :key="item.sector_name" class="sector-item">
          <view class="sector-info">
            <text class="sector-name">{{ item.sector_name }}</text>
            <text class="sector-tag">{{ item.sector_mainline_tag }}</text>
          </view>
          <view class="sector-change">
            <text :class="item.sector_change_pct > 0 ? 'text-red' : 'text-green'">
              {{ item.sector_change_pct?.toFixed(2) }}%
            </text>
          </view>
        </view>

        <view v-if="activeTab === 'follow'" v-for="item in data.follow_sectors" :key="item.sector_name" class="sector-item">
          <view class="sector-info">
            <text class="sector-name">{{ item.sector_name }}</text>
            <text class="sector-tag">{{ item.sector_tradeability_tag }}</text>
          </view>
          <view class="sector-change">
            <text :class="item.sector_change_pct > 0 ? 'text-red' : 'text-green'">
              {{ item.sector_change_pct?.toFixed(2) }}%
            </text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { sectorApi, getToday } from '../../api'

const today = ref(getToday())
const activeTab = ref('mainline')
const data = ref({ mainline_sectors: [], sub_mainline_sectors: [], follow_sectors: [] })

const tabs = [
  { key: 'mainline', name: '主线' },
  { key: 'sub', name: '次主线' },
  { key: 'follow', name: '跟风' }
]

const loadData = async () => {
  try {
    const res = await sectorApi.scan(today.value)
    data.value = res.data.data
  } catch (e) {
    console.error('加载失败', e)
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.page { padding: 10px; }
.card { background: #fff; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
.card-title { font-size: 16px; font-weight: bold; margin-bottom: 10px; }

.tabs { display: flex; margin-bottom: 15px; }
.tab { flex: 1; text-align: center; padding: 10px; border-bottom: 2px solid transparent; }
.tab.active { border-color: #409eff; color: #409eff; }

.sector-list { display: flex; flex-direction: column; }
.sector-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #f5f5f5; }
.sector-info { display: flex; align-items: center; }
.sector-name { font-weight: bold; margin-right: 10px; }
.sector-tag { font-size: 12px; padding: 2px 8px; background: #f0f0f0; border-radius: 4px; }
.sector-change { font-weight: bold; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
</style>
