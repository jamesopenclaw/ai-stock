<template>
  <el-badge :value="badgeValue" :hidden="!badgeValue" :max="99" :type="criticalCount > 0 ? 'danger' : 'primary'">
    <el-button
      class="notification-bell"
      :class="{ 'notification-bell-critical': criticalCount > 0 }"
      circle
      plain
      @click="$emit('open')"
    >
      <el-icon><Bell /></el-icon>
    </el-button>
  </el-badge>
</template>

<script setup>
import { computed } from 'vue'
import { Bell } from '@element-plus/icons-vue'

const props = defineProps({
  unreadCount: {
    type: Number,
    default: 0,
  },
  criticalCount: {
    type: Number,
    default: 0,
  },
})

defineEmits(['open'])

const badgeValue = computed(() => Number(props.unreadCount || 0))
</script>

<style scoped>
.notification-bell {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.notification-bell-critical {
  border-color: rgba(255, 122, 127, 0.35);
  color: #ff8c69;
  background: rgba(255, 122, 127, 0.08);
}
</style>
