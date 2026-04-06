<template>
  <section class="freshness-bar">
    <div class="freshness-head">
      <span class="freshness-kicker">{{ headline }}</span>
      <span v-if="note" class="freshness-note">{{ note }}</span>
    </div>
    <div class="freshness-items">
      <article
        v-for="item in normalizedItems"
        :key="`${item.label}-${item.value}`"
        class="freshness-item"
        :class="item.tone ? `freshness-item-${item.tone}` : ''"
      >
        <span class="freshness-label">{{ item.label }}</span>
        <strong class="freshness-value">{{ item.value }}</strong>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  headline: { type: String, default: '数据口径' },
  note: { type: String, default: '' },
  items: {
    type: Array,
    default: () => [],
  },
})

const normalizedItems = computed(() => (
  (props.items || []).filter((item) => item && item.label && item.value)
))
</script>

<style scoped>
.freshness-bar {
  display: grid;
  gap: 12px;
  margin-bottom: 18px;
  padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.05));
}

.freshness-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.freshness-kicker {
  font-size: 12px;
  font-weight: 700;
  color: #93a0b8;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.freshness-note {
  font-size: 13px;
  color: var(--color-text-sec);
  line-height: 1.5;
}

.freshness-items {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}

.freshness-item {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}

.freshness-item-strong {
  background: rgba(41, 98, 255, 0.14);
}

.freshness-item-warn {
  background: rgba(224, 32, 32, 0.12);
}

.freshness-item-muted {
  background: rgba(147, 160, 184, 0.08);
}

.freshness-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.freshness-value {
  font-size: 14px;
  color: var(--color-text-pri);
  line-height: 1.4;
}
</style>
