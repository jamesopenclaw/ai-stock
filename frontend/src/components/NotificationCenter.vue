<template>
  <el-drawer
    :model-value="modelValue"
    title="通知中心"
    direction="rtl"
    size="420px"
    @close="$emit('update:modelValue', false)"
  >
    <div class="notification-center">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="待处理" name="pending" />
        <el-tab-pane label="全部" name="all" />
        <el-tab-pane label="设置" name="settings" />
      </el-tabs>

      <template v-if="activeTab === 'settings'">
        <el-skeleton v-if="settingsLoading" :rows="6" animated />
        <el-form v-else label-position="top" class="settings-form">
          <el-form-item label="站内提醒">
            <el-switch v-model="settings.in_app_enabled" active-text="开启" inactive-text="关闭" />
          </el-form-item>
          <el-form-item label="企业微信提醒">
            <el-switch v-model="settings.wecom_enabled" active-text="开启" inactive-text="关闭" />
          </el-form-item>
          <el-form-item label="提醒级别">
            <div class="rule-grid">
              <div v-for="rule in ruleOptions" :key="rule.key" class="rule-row">
                <span>{{ rule.label }}</span>
                <el-select v-model="settings.rules[rule.key]" size="small">
                  <el-option label="关闭" value="off" />
                  <el-option label="高优先级" value="high" />
                  <el-option label="中优先级" value="medium" />
                  <el-option label="低优先级" value="low" />
                  <el-option label="系统提示" value="info" />
                </el-select>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="静默时段">
            <div class="quiet-window-list">
              <div
                v-for="(window, index) in settings.quiet_windows"
                :key="`${window.start || 'start'}-${window.end || 'end'}-${index}`"
                class="quiet-window-row"
              >
                <el-time-select
                  v-model="window.start"
                  class="quiet-time"
                  start="00:00"
                  step="00:15"
                  end="23:45"
                  placeholder="开始"
                />
                <span class="quiet-window-sep">至</span>
                <el-time-select
                  v-model="window.end"
                  class="quiet-time"
                  start="00:00"
                  step="00:15"
                  end="23:45"
                  placeholder="结束"
                />
                <el-button link type="danger" @click="removeQuietWindow(index)">删除</el-button>
              </div>
              <el-button link type="primary" @click="addQuietWindow">新增静默时段</el-button>
              <div class="quiet-window-hint">
                静默时段会暂停企业微信推送和顶部站内弹窗，铃铛红点与通知列表仍会保留。
              </div>
            </div>
          </el-form-item>
          <div class="settings-actions">
            <el-button type="primary" :loading="settingsSaving" @click="saveSettings">保存设置</el-button>
          </div>
        </el-form>
      </template>

      <template v-else>
        <div class="toolbar">
          <div class="filter-row">
            <el-select v-model="filters.category" size="small" placeholder="分类">
              <el-option label="全部分类" value="" />
              <el-option label="持仓" value="holding" />
              <el-option label="候选" value="candidate" />
              <el-option label="市场" value="market" />
              <el-option label="系统" value="system" />
            </el-select>
            <el-select v-model="filters.priority" size="small" placeholder="优先级">
              <el-option label="全部优先级" value="" />
              <el-option label="高" value="high" />
              <el-option label="中" value="medium" />
              <el-option label="低" value="low" />
              <el-option label="系统" value="info" />
            </el-select>
          </div>
          <el-button link @click="handleMarkAllRead">全部已读</el-button>
        </div>

        <el-skeleton v-if="loading" :rows="6" animated />
        <el-empty v-else-if="!items.length" description="当前没有待处理提醒" />

        <div v-else class="notification-list">
          <section
            v-for="group in groupedItems"
            :key="group.priority"
            class="notification-group"
          >
            <div class="notification-group-head">
              <div class="notification-group-title">{{ priorityLabel(group.priority) }}优先级</div>
              <div class="notification-group-count">{{ group.items.length }} 条</div>
            </div>
            <article
              v-for="item in group.items"
              :key="item.id"
              class="notification-card"
              :class="`notification-card-${item.priority}`"
            >
              <div class="notification-top">
                <div class="notification-title">{{ item.title }}</div>
                <el-tag size="small" :type="priorityTagType(item.priority)">{{ priorityLabel(item.priority) }}</el-tag>
              </div>
              <div class="notification-message">{{ item.message }}</div>
              <div class="notification-meta">
                <span>{{ categoryLabel(item.category) }}</span>
                <span>{{ sourceLabel(item.data_source) }}</span>
                <span>{{ formatLocalTime(item.updated_at, { assumeUtc: true }) }}</span>
              </div>
              <div class="notification-actions">
                <el-button type="primary" link @click="openNotification(item)">{{ item.action_label }}</el-button>
                <el-button link @click="markRead(item)">已读</el-button>
                <el-button link @click="snooze(item)">稍后</el-button>
              </div>
            </article>
          </section>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useNotificationStore } from '../stores/notificationStore'
import { formatLocalTime } from '../utils/datetime'
import { dataSourceLabel } from '../utils/dataSource'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

const router = useRouter()
const loading = ref(false)
const settingsLoading = ref(false)
const settingsSaving = ref(false)
const activeTab = ref('pending')
const items = ref([])
const notificationStore = useNotificationStore()
const filters = reactive({
  category: '',
  priority: '',
})
const settings = reactive({
  in_app_enabled: true,
  wecom_enabled: false,
  rules: {},
  quiet_windows: [],
})

const ruleOptions = [
  { key: 'holding_to_sell', label: '持仓转卖出' },
  { key: 'holding_to_reduce', label: '持仓转减仓' },
  { key: 'candidate_to_executable', label: '候选转可执行' },
  { key: 'candidate_near_trigger', label: '接近触发位' },
  { key: 'market_env_downgraded', label: '市场转防守' },
  { key: 'realtime_source_degraded', label: '实时源降级' },
]

const currentStatus = computed(() => (activeTab.value === 'pending' ? 'pending' : ''))
const groupedItems = computed(() => {
  const order = ['high', 'medium', 'low', 'info']
  return order
    .map((priority) => ({
      priority,
      items: items.value.filter((item) => item.priority === priority),
    }))
    .filter((group) => group.items.length)
})

const loadList = async () => {
  loading.value = true
  try {
    const payload = await notificationStore.loadList({
      status: currentStatus.value || undefined,
      category: filters.category || undefined,
      priority: filters.priority || undefined,
    })
    items.value = payload.items || []
  } catch (error) {
    const message = error?.response?.data?.message || error?.message || '加载通知失败'
    ElMessage.error(message)
  } finally {
    loading.value = false
  }
}

const loadSettings = async () => {
  settingsLoading.value = true
  try {
    const payload = await notificationStore.loadSettings()
    settings.in_app_enabled = Boolean(payload.in_app_enabled)
    settings.wecom_enabled = Boolean(payload.wecom_enabled)
    settings.rules = { ...payload.rules }
    settings.quiet_windows = Array.isArray(payload.quiet_windows) ? [...payload.quiet_windows] : []
  } catch (error) {
    const message = error?.response?.data?.message || error?.message || '加载通知设置失败'
    ElMessage.error(message)
  } finally {
    settingsLoading.value = false
  }
}

const saveSettings = async () => {
  settingsSaving.value = true
  try {
    await notificationStore.updateSettings({
      in_app_enabled: settings.in_app_enabled,
      wecom_enabled: settings.wecom_enabled,
      rules: settings.rules,
      quiet_windows: settings.quiet_windows,
    })
    ElMessage.success('通知设置已保存')
  } catch (error) {
    const message = error?.response?.data?.message || error?.message || '保存通知设置失败'
    ElMessage.error(message)
  } finally {
    settingsSaving.value = false
  }
}

const addQuietWindow = () => {
  settings.quiet_windows = [
    ...settings.quiet_windows,
    { start: '11:30', end: '13:00' },
  ]
}

const removeQuietWindow = (index) => {
  settings.quiet_windows = settings.quiet_windows.filter((_, currentIndex) => currentIndex !== index)
}

const markRead = async (item) => {
  await notificationStore.markRead(item.id)
  await loadList()
}

const handleMarkAllRead = async () => {
  const isHighOnly = filters.priority === 'high'
  const hasHighItems = items.value.some((item) => item.priority === 'high')
  if (isHighOnly && items.value.length) {
    try {
      await ElMessageBox.confirm(
        '当前筛选下是高优先级提醒，批量已读后这些风险提醒会从待处理列表移除。',
        '确认清空高优先级提醒',
        {
          type: 'warning',
          confirmButtonText: '确认已读',
          cancelButtonText: '取消',
        }
      )
    } catch {
      return
    }
  }

  await notificationStore.markAllRead({
    status: currentStatus.value || undefined,
    category: filters.category || undefined,
    priority: filters.priority || undefined,
    exclude_priorities: !isHighOnly && !filters.priority ? ['high'] : [],
  })
  if (!isHighOnly && !filters.priority && hasHighItems) {
    ElMessage.warning('已批量处理非高优先级提醒，高优先级提醒已保留。')
  }
  await loadList()
}

const snooze = async (item) => {
  await notificationStore.snooze(item.id, 30)
  await loadList()
}

const openNotification = async (item) => {
  await notificationStore.markRead(item.id)
  const payload = item.action_target_payload || {}
  const route = payload.route || '/'
  const query = payload.query || {}
  emit('update:modelValue', false)
  await router.push({ path: route, query })
}

const priorityLabel = (value) => {
  if (value === 'high') return '高'
  if (value === 'medium') return '中'
  if (value === 'low') return '低'
  return '系统'
}

const priorityTagType = (value) => {
  if (value === 'high') return 'danger'
  if (value === 'medium') return 'warning'
  if (value === 'low') return 'success'
  return 'info'
}

const categoryLabel = (value) => {
  if (value === 'holding') return '持仓'
  if (value === 'candidate') return '候选'
  if (value === 'market') return '市场'
  return '系统'
}

const sourceLabel = (value) => {
  return dataSourceLabel(value, { emptyLabel: '规则结果' })
}

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return
    if (activeTab.value === 'settings') {
      loadSettings()
      return
    }
    loadList()
  }
)

watch(activeTab, (tab) => {
  if (!props.modelValue) return
  if (tab === 'settings') {
    loadSettings()
    return
  }
  loadList()
})

watch(
  () => [filters.category, filters.priority],
  () => {
    if (!props.modelValue || activeTab.value === 'settings') return
    loadList()
  }
)
</script>

<style scoped>
.notification-center {
  display: grid;
  gap: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.filter-row {
  display: flex;
  gap: 10px;
  flex: 1;
}

.notification-list {
  display: grid;
  gap: 12px;
}

.notification-group {
  display: grid;
  gap: 10px;
}

.notification-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--color-text-sec);
  font-size: 12px;
}

.notification-group-title {
  font-weight: 700;
  color: var(--color-text-pri);
}

.notification-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.notification-card-high {
  border-color: rgba(255, 122, 127, 0.18);
}

.notification-card-medium {
  border-color: rgba(243, 194, 77, 0.18);
}

.notification-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.notification-title {
  font-weight: 700;
  line-height: 1.5;
}

.notification-message {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.notification-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: var(--color-text-sec);
}

.notification-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.settings-form {
  display: grid;
  gap: 8px;
}

.rule-grid {
  display: grid;
  gap: 10px;
}

.rule-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 130px;
  align-items: center;
  gap: 12px;
}

.settings-actions {
  display: flex;
  justify-content: flex-end;
}

.quiet-window-list {
  display: grid;
  gap: 10px;
}

.quiet-window-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.quiet-time {
  width: 110px;
}

.quiet-window-sep {
  color: var(--color-text-sec);
}

.quiet-window-hint {
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-sec);
}
</style>
