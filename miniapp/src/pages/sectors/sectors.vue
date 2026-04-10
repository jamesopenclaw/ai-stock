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
          {{ tab.name }} ({{ getCount(tab.key) }})
        </view>
      </view>

      <view class="sector-list">
        <!-- 主线题材 -->
        <view v-if="activeTab === 'theme'" v-for="item in data.theme_leaders" :key="`${item.sector_name}-${item.sector_source_type}`" class="sector-item" @click="showDetail(item)">
          <view class="sector-info">
            <text class="sector-name">{{ item.sector_name }}</text>
            <text class="sector-tag">{{ item.sector_source_type === 'concept' ? '题材主线' : item.sector_mainline_tag }}</text>
          </view>
          <view class="sector-right">
            <text :class="['sector-change', item.sector_change_pct > 0 ? 'text-red' : 'text-green']">
              {{ item.sector_change_pct?.toFixed(2) }}%
            </text>
            <text class="sector-arrow">›</text>
          </view>
        </view>

        <!-- 承接行业 -->
        <view v-if="activeTab === 'industry'" v-for="item in data.industry_leaders" :key="`${item.sector_name}-${item.sector_source_type}`" class="sector-item" @click="showDetail(item)">
          <view class="sector-info">
            <text class="sector-name">{{ item.sector_name }}</text>
            <text class="sector-tag">{{ item.sector_source_type === 'limitup_industry' ? '涨停行业' : '承接行业' }}</text>
          </view>
          <view class="sector-right">
            <text :class="['sector-change', item.sector_change_pct > 0 ? 'text-red' : 'text-green']">
              {{ item.sector_change_pct?.toFixed(2) }}%
            </text>
            <text class="sector-arrow">›</text>
          </view>
        </view>

        <!-- 主线候选 -->
        <view v-if="activeTab === 'mainline'" v-for="item in data.mainline_sectors" :key="`${item.sector_name}-${item.sector_source_type}`" class="sector-item" @click="showDetail(item)">
          <view class="sector-info">
            <text class="sector-name">{{ item.sector_name }}</text>
            <text class="sector-tag">{{ item.sector_mainline_tag }}</text>
          </view>
          <view class="sector-right">
            <text :class="['sector-change', item.sector_change_pct > 0 ? 'text-red' : 'text-green']">
              {{ item.sector_change_pct?.toFixed(2) }}%
            </text>
            <text class="sector-arrow">›</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 详情弹窗 -->
    <view v-if="showModal" class="modal-mask" @click="showModal = false">
      <view class="modal-content" @click.stop>
        <view class="modal-header">
          <text class="modal-title">{{ currentItem.sector_name }}</text>
          <text class="modal-close" @click="showModal = false">×</text>
        </view>
        <view class="modal-body">
          <view class="detail-row">
            <text class="detail-label">涨跌幅</text>
            <text :class="['detail-value', currentItem.sector_change_pct > 0 ? 'text-red' : 'text-green']">
              {{ currentItem.sector_change_pct?.toFixed(2) }}%
            </text>
          </view>
          <view class="detail-row">
            <text class="detail-label">强度排名</text>
            <text class="detail-value">#{{ currentItem.sector_strength_rank }}</text>
          </view>
          <view class="detail-row">
            <text class="detail-label">主线标签</text>
            <text class="detail-value">{{ currentItem.sector_mainline_tag }}</text>
          </view>
          <view class="detail-row">
            <text class="detail-label">来源类型</text>
            <text class="detail-value">{{ currentItem.sector_source_type }}</text>
          </view>
          <view class="detail-row">
            <text class="detail-label">连续性</text>
            <text class="detail-value">{{ currentItem.sector_continuity_tag }}</text>
          </view>
          <view class="detail-row">
            <text class="detail-label">交易性</text>
            <text class="detail-value">{{ currentItem.sector_tradeability_tag }}</text>
          </view>
          <view class="detail-row">
            <text class="detail-label">板块简评</text>
            <text class="detail-value">{{ currentItem.sector_comment }}</text>
          </view>
        </view>
      </view>
    </view>

    <view v-if="loading" class="loading">
      <text>加载中...</text>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { sectorApi, getToday } from '../../api'

const today = ref(getToday())
const activeTab = ref('theme')
const loading = ref(false)
const data = ref({ theme_leaders: [], industry_leaders: [], mainline_sectors: [], sub_mainline_sectors: [], follow_sectors: [] })
const showModal = ref(false)
const currentItem = ref({})

const tabs = [
  { key: 'theme', name: '题材主线' },
  { key: 'industry', name: '承接行业' },
  { key: 'mainline', name: '主线候选' }
]

const getCount = (key) => {
  if (key === 'theme') return data.value.theme_leaders?.length || 0
  if (key === 'industry') return data.value.industry_leaders?.length || 0
  return data.value.mainline_sectors?.length || 0
}

const showDetail = (item) => {
  currentItem.value = item
  showModal.value = true
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await sectorApi.scan(today.value)
    data.value = res.data.data
  } catch (e) {
    console.error('加载失败', e)
  } finally {
    loading.value = false
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
.sector-right { display: flex; align-items: center; }
.sector-change { font-weight: bold; margin-right: 10px; }
.sector-arrow { font-size: 20px; color: #999; }

.modal-mask { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 100; display: flex; align-items: center; justify-content: center; }
.modal-content { background: #fff; border-radius: 8px; width: 80%; max-height: 70%; overflow: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #eee; }
.modal-title { font-size: 18px; font-weight: bold; }
.modal-close { font-size: 24px; color: #999; }
.modal-body { padding: 15px; }
.detail-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f5f5f5; }
.detail-label { color: #999; }
.detail-value { font-weight: bold; }

.loading { text-align: center; padding: 30px; color: #999; }
.text-red { color: #f56c6c; }
.text-green { color: #67c23a; }
</style>
