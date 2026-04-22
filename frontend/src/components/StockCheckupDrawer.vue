<template>
  <el-drawer
    :model-value="modelValue"
    size="68%"
    :destroy-on-close="false"
    class="stock-checkup-drawer"
    @close="handleClose"
  >
    <template #header>
      <div class="drawer-header">
        <div class="header-shell">
          <div class="header-main">
            <div class="header-title-row">
              <div class="header-title">{{ headerTitle }}</div>
              <span v-if="rule?.strategy?.current_strategy" class="header-strategy-chip" :class="strategyBadgeClass">
                {{ rule.strategy.current_strategy }}
              </span>
            </div>
            <div class="header-subtitle">{{ headerSubtitle }}</div>
            <div class="header-meta">
              <span v-for="item in headerMetaItems" :key="item.label" class="header-meta-pill">
                <span class="header-meta-label">{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </span>
            </div>
          </div>

          <div class="header-actions">
            <div class="header-target-group">
              <span class="header-group-label">体检目标</span>
              <el-radio-group v-model="activeTarget" size="small" @change="loadData">
                <el-radio-button label="观察型" />
                <el-radio-button label="持仓型" />
                <el-radio-button label="交易型" />
              </el-radio-group>
            </div>
            <div class="header-button-row">
              <el-button @click="loadData()" :loading="loading">刷新</el-button>
              <el-button @click="refreshLlm()" :loading="llmRefreshing" type="primary" plain>
                {{ llmRefreshing ? '正在刷新解读...' : '刷新解读' }}
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <div class="drawer-body">
      <el-empty v-if="!tsCode" description="请选择一只股票后再查看体检" />
      <el-skeleton v-else-if="loading && !data" :rows="16" animated />
      <el-empty v-else-if="!data" description="暂无体检结果" />
      <template v-else>
        <div v-if="refreshStateVisible" class="refresh-banner" :class="`refresh-banner-${activeRefreshMode}`">
          <div class="refresh-banner-main">
            <span class="refresh-banner-spinner" />
            <div class="refresh-banner-copy">
              <strong>{{ refreshBannerTitle }}</strong>
              <span>{{ refreshBannerText }}</span>
            </div>
          </div>
          <span class="refresh-banner-tag">{{ refreshBannerTag }}</span>
        </div>

        <div class="content-shell" :class="{ 'content-shell-refreshing': refreshStateVisible }">
          <section class="hero-stage">
            <div class="hero-orb hero-orb-a" />
            <div class="hero-orb hero-orb-b" />

            <div class="hero-layout">
              <section class="hero-panel">
                <div class="hero-top">
                  <div class="hero-badge-stack">
                    <div class="hero-badge" :class="strategyBadgeClass">
                      {{ rule?.strategy?.current_strategy || '观察' }}
                    </div>
                    <span class="hero-badge-caption">当前策略</span>
                  </div>
                  <div class="hero-copy">
                    <div class="hero-kicker">结论先行</div>
                    <div class="hero-title">
                      {{ rule?.strategy?.current_characterization || '-' }} / {{ rule?.strategy?.current_role || '-' }}
                    </div>
                    <div class="hero-desc">
                      {{ llm?.overall_summary || rule?.strategy?.strategy_reason || '-' }}
                    </div>
                  </div>
                </div>

                <div class="hero-conclusion-card">
                  <span class="hero-conclusion-label">一句话结论</span>
                  <div class="hero-conclusion">
                    {{ llm?.one_line_conclusion || rule?.final_conclusion?.one_line_conclusion || '-' }}
                  </div>
                  <div class="hero-conclusion-note">
                    {{ actionSubline }}
                  </div>
                </div>

                <div class="hero-bottom">
                  <div class="hero-tags">
                    <span v-for="tag in heroTags" :key="tag" class="hero-tag">{{ tag }}</span>
                  </div>

                  <div v-if="llmStatusVisible" class="status-strip" :class="llmStatusClass">
                    <span class="status-label">LLM 解读</span>
                    <span>{{ llmStatusText }}</span>
                  </div>
                </div>
              </section>

              <aside class="action-panel">
                <div class="action-panel-head">
                  <div class="panel-head">
                    <span class="panel-kicker">怎么做</span>
                    <strong class="panel-title">{{ actionHeadline }}</strong>
                  </div>
                  <div class="panel-copy">{{ actionCopy }}</div>
                </div>

                <div class="execution-grid">
                  <article
                    v-for="(item, index) in executionCards"
                    :key="item.label"
                    class="execution-card"
                    :class="[
                      `execution-card-${item.tone || 'neutral'}`,
                      { 'execution-card-primary': index === 1 }
                    ]"
                  >
                    <span class="execution-step">{{ item.step }}</span>
                    <div class="execution-copy">
                      <span class="execution-label">{{ item.label }}</span>
                      <strong class="execution-value">{{ item.value }}</strong>
                      <span class="execution-note">{{ item.note }}</span>
                    </div>
                  </article>
                </div>
              </aside>
            </div>

            <div class="snapshot-grid">
              <article
                v-for="card in snapshotCards"
                :key="card.label"
                class="snapshot-card"
                :class="`snapshot-card-${card.tone || 'neutral'}`"
              >
                <div class="snapshot-top">
                  <span class="snapshot-label">{{ card.label }}</span>
                  <span class="snapshot-dot" />
                </div>
                <strong class="snapshot-value" :class="card.valueClass || ''">{{ card.value }}</strong>
                <span class="snapshot-tip">{{ card.tip }}</span>
              </article>
            </div>
          </section>

          <div class="decision-grid">
            <section class="decision-card decision-card-risk">
              <div class="decision-head">
                <span class="decision-kicker">风险与前提</span>
                <strong>先确认这些条件</strong>
              </div>
              <div v-if="riskItems.length" class="decision-chip-row">
                <span v-for="risk in riskItems" :key="risk" class="risk-chip">{{ risk }}</span>
              </div>
              <div v-else class="decision-note decision-note-muted">当前没有额外风险标签，仍需结合关键位与市场环境判断。</div>
              <div class="decision-footnote">{{ invalidationSummary }}</div>
            </section>

            <section class="decision-card decision-card-context">
              <div class="decision-head">
                <span class="decision-kicker">数据上下文</span>
                <strong>知道结论来自哪里</strong>
              </div>
              <div class="context-pill-grid">
                <article v-for="item in contextItems" :key="item.label" class="context-pill">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </article>
              </div>
            </section>
          </div>

          <section class="evidence-section">
            <div class="section-heading">
              <span class="section-kicker">为什么是这个结论</span>
              <h3>核心证据</h3>
              <p class="section-heading-copy">先看每组证据的核心判断，需要时再展开完整说明。</p>
            </div>

            <div class="evidence-grid">
              <article v-for="block in evidenceBlocks" :key="block.id" class="evidence-card">
                <div class="evidence-head">
                  <div>
                    <div class="evidence-kicker">{{ block.kicker }}</div>
                    <div class="evidence-title">{{ block.title }}</div>
                  </div>
                  <div class="evidence-summary">{{ block.summary }}</div>
                </div>

                <div v-if="block.highlight" class="evidence-highlight">
                  {{ block.highlight }}
                </div>

                <div class="evidence-fact-grid">
                  <div v-for="item in block.items" :key="item.label" class="data-item">
                    <span>{{ item.label }}</span>
                    <strong :class="item.valueClass || ''">{{ item.value }}</strong>
                  </div>
                </div>

                <details v-if="block.note || block.copy" class="evidence-details">
                  <summary class="evidence-details-summary">
                    <span>展开说明</span>
                    <span class="evidence-details-action">查看解读</span>
                  </summary>
                  <div v-if="block.note" class="section-note evidence-note">{{ block.note }}</div>
                  <div v-if="block.copy" class="llm-copy evidence-copy">{{ block.copy }}</div>
                </details>
              </article>
            </div>
          </section>

          <details class="details-disclosure">
            <summary class="details-summary">
              <div class="details-summary-copy">
                <span class="details-kicker">深度核对</span>
                <strong>查看完整体检明细</strong>
                <span>保留原始字段与逐项解读，方便回看和核对。</span>
              </div>
              <div class="details-summary-side">
                <span class="details-summary-pill">规则快照 + LLM 解读</span>
                <span class="details-summary-action">展开全部</span>
              </div>
            </summary>

            <div class="details-grid">
              <section class="detail-card">
                <div class="detail-card-head">
                  <span class="detail-card-kicker">原始快照</span>
                  <div class="detail-card-title">基础信息</div>
                </div>
                <div class="data-list">
                  <div class="data-item"><span>名称 / 代码</span><strong>{{ rule?.basic_info?.stock_name || '-' }} / {{ rule?.basic_info?.ts_code || '-' }}</strong></div>
                  <div class="data-item"><span>行业 / 板块</span><strong>{{ rule?.basic_info?.sector_name || '-' }}</strong></div>
                  <div class="data-item"><span>板块属性</span><strong>{{ rule?.basic_info?.board || '-' }}</strong></div>
                  <div class="data-item"><span>特殊属性</span><strong>{{ joinList(rule?.basic_info?.special_tags) }}</strong></div>
                </div>
                <div class="detail-note-band">{{ rule?.final_conclusion?.summary_note || '-' }}</div>
              </section>

              <section class="detail-card">
                <div class="detail-card-head">
                  <span class="detail-card-kicker">执行语境</span>
                  <div class="detail-card-title">策略视角</div>
                </div>
                <div class="strategy-pill" :class="strategyBadgeClass">{{ rule?.strategy?.current_strategy || '-' }}</div>
                <div class="section-emphasis">{{ rule?.strategy?.strategy_reason || '-' }}</div>
                <div v-if="rule?.buy_view" class="sub-panel">
                  <div class="sub-title">交易视角</div>
                  <div class="sub-copy">{{ rule.buy_view.buy_signal_tag || '-' }} / {{ rule.buy_view.buy_point_type || '-' }}</div>
                  <div class="sub-copy">{{ rule.buy_view.buy_comment || rule.buy_view.buy_trigger_cond || '-' }}</div>
                </div>
                <div v-if="rule?.sell_view" class="sub-panel">
                  <div class="sub-title">持仓视角</div>
                  <div class="sub-copy">{{ rule.sell_view.sell_signal_tag || '-' }} / {{ rule.sell_view.sell_point_type || '-' }}</div>
                  <div class="sub-copy">{{ rule.sell_view.sell_comment || rule.sell_view.sell_reason || '-' }}</div>
                </div>
              </section>

              <section class="detail-card detail-card-full">
                <div class="detail-card-head">
                  <span class="detail-card-kicker">章节解读</span>
                  <div class="detail-card-title">逐项解读</div>
                </div>
                <div v-if="visibleReportSections.length" class="report-grid">
                  <article v-for="(section, index) in visibleReportSections" :key="section.key" class="report-card">
                    <div class="report-card-top">
                      <span class="report-index">{{ String(index + 1).padStart(2, '0') }}</span>
                      <div class="report-title">{{ section.title }}</div>
                    </div>
                    <div class="report-copy">{{ section.content }}</div>
                  </article>
                </div>
                <div v-else class="section-note">暂无逐项 LLM 解读，当前以规则快照为准。</div>
              </section>
            </div>
          </details>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { stockApi } from '../api'
import { formatLocalDateTime } from '../utils/datetime'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  tsCode: { type: String, default: '' },
  stockName: { type: String, default: '' },
  tradeDate: { type: String, default: '' },
  defaultTarget: { type: String, default: '观察型' }
})

const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const llmRefreshing = ref(false)
const activeTarget = ref('观察型')
const data = ref(null)
const CHECKUP_TIMEOUT = 120000
/** 防止切换标的/目标后，较晚返回的 LLM 请求覆盖当前页面 */
const checkupRequestSeq = ref(0)

const rule = computed(() => data.value?.rule_snapshot || null)
const llm = computed(() => data.value?.llm_report || null)
const reportSections = computed(() => llm.value?.llm_report_sections || [])
const displayTradeDate = computed(() => props.tradeDate || getLocalDate())
const headerTitle = computed(() => `${props.stockName || '个股'}全面体检`)
const headerSubtitle = computed(() => (
  llm.value?.overall_summary
  || rule.value?.strategy?.strategy_reason
  || '围绕结论、执行与证据，快速判断这只票当前值不值得看。'
))
const headerMetaItems = computed(() => {
  const items = [
    { label: '代码', value: props.tsCode || '-' },
    { label: '体检日', value: displayTradeDate.value || '-' },
  ]
  if (data.value?.resolved_trade_date && data.value.resolved_trade_date !== displayTradeDate.value) {
    items.push({ label: '实际行情日', value: data.value.resolved_trade_date })
  }
  if (rule.value?.basic_info?.quote_time) {
    items.push({ label: '报价时间', value: formatQuoteTime(rule.value.basic_info.quote_time) })
  }
  return items
})
const activeRefreshMode = computed(() => {
  if (loading.value && data.value) return 'data'
  if (llmRefreshing.value && data.value) return 'llm'
  return ''
})
const refreshStateVisible = computed(() => Boolean(activeRefreshMode.value))
const refreshBannerTitle = computed(() => {
  if (activeRefreshMode.value !== 'llm') return '正在刷新最新体检'
  if (llmStatus.value?.status === 'pending' && !llm.value) return '正在加载 LLM 解读'
  return '正在刷新最新解读'
})
const refreshBannerText = computed(() => (
  activeRefreshMode.value === 'llm'
    ? '当前规则快照仍可阅读，但页面里的解读文案不是最新结果。'
    : '当前页面仍展示上一版体检结果，请等待刷新完成后再做判断。'
))
const refreshBannerTag = computed(() => (
  activeRefreshMode.value === 'llm' ? '旧解读展示中' : '旧结果展示中'
))
const llmStatus = computed(() => data.value?.llm_status || null)
const llmStatusVisible = computed(() => Boolean(llmStatus.value))
const llmStatusClass = computed(() => {
  if (llmStatus.value?.success) return 'status-success'
  if (llmStatus.value?.enabled) return 'status-warning'
  return 'status-muted'
})
const llmStatusText = computed(() => {
  if (llmRefreshing.value && llmStatus.value?.status === 'pending') {
    return '正在加载 LLM 解读，可先阅读上方规则结论与证据。'
  }
  if (llmRefreshing.value) return '正在刷新最新 LLM 解读，当前文案仍是上一版结果。'
  if (!llmStatus.value) return ''
  return llmStatus.value.message || (llmStatus.value.success ? 'LLM 体检已生效' : 'LLM 当前未生效')
})
const strategyBadgeClass = computed(() => {
  const strategy = rule.value?.strategy?.current_strategy
  if (strategy === '低吸') return 'badge-buy'
  if (strategy === '突破确认') return 'badge-break'
  if (strategy === '放弃') return 'badge-pass'
  return 'badge-watch'
})
const riskItems = computed(() => (
  llm.value?.key_risks?.length ? llm.value.key_risks : (rule.value?.strategy?.risk_points || [])
))
const heroTags = computed(() => {
  const tags = [
    `体检目标 ${activeTarget.value}`,
    rule.value?.market_context?.market_env_tag,
    rule.value?.direction_position?.direction_name,
    rule.value?.direction_position?.stock_role,
    rule.value?.daily_structure?.stage_position,
    rule.value?.basic_info?.sector_name,
  ].filter(Boolean)
  return Array.from(new Set(tags))
})
const actionHeadline = computed(() => {
  if (rule.value?.buy_view?.buy_signal_tag) {
    return `${rule.value.buy_view.buy_signal_tag} / ${rule.value.buy_view.buy_point_type || '等待触发'}`
  }
  if (rule.value?.sell_view?.sell_signal_tag) {
    return `${rule.value.sell_view.sell_signal_tag} / ${rule.value.sell_view.sell_point_type || '先按计划处理'}`
  }
  return rule.value?.strategy?.current_strategy || '-'
})
const actionCopy = computed(() => (
  rule.value?.buy_view?.buy_comment
  || rule.value?.buy_view?.buy_trigger_cond
  || rule.value?.sell_view?.sell_comment
  || rule.value?.sell_view?.sell_reason
  || rule.value?.strategy?.strategy_reason
  || '-'
))
const actionSubline = computed(() => {
  if (rule.value?.buy_view) return '按“盯触发 -> 看确认 -> 守失效”顺序处理，不抢第一下。'
  if (rule.value?.sell_view) return '按“等触发 -> 做处理 -> 守退出”顺序执行，先纪律后观点。'
  return '先看结构位置，再等触发信号，不提前预判。'
})
const executionCards = computed(() => {
  const cards = [
    {
      step: '00',
      label: '当前打法',
      value: rule.value?.strategy?.current_strategy || '-',
      note: rule.value?.strategy?.current_characterization || '-',
      tone: 'neutral',
    },
  ]

  if (rule.value?.buy_view) {
    cards.push(
      {
        step: '01',
        label: '触发条件',
        value: rule.value.buy_view.buy_trigger_cond || '-',
        note: rule.value.buy_view.buy_signal_tag || '等待主触发',
        tone: 'watch',
      },
      {
        step: '02',
        label: '确认点',
        value: rule.value.buy_view.buy_confirm_cond || '-',
        note: rule.value.buy_view.buy_point_type || '确认后再执行',
        tone: 'focus',
      },
      {
        step: '03',
        label: '失效条件',
        value: rule.value.buy_view.buy_invalid_cond || '-',
        note: '触发失败就撤退，不做硬扛',
        tone: 'risk',
      },
    )
  } else if (rule.value?.sell_view) {
    cards.push(
      {
        step: '01',
        label: '触发条件',
        value: rule.value.sell_view.sell_trigger_cond || '-',
        note: rule.value.sell_view.sell_signal_tag || '先盯执行触发',
        tone: 'watch',
      },
      {
        step: '02',
        label: '处理原因',
        value: rule.value.sell_view.sell_reason || '-',
        note: rule.value.sell_view.sell_point_type || '按持仓视角处理',
        tone: 'focus',
      },
      {
        step: '03',
        label: '今日能否执行',
        value: formatBoolean(rule.value.sell_view.can_sell_today),
        note: '结合盘中承接与仓位管理',
        tone: 'risk',
      },
    )
  } else {
    cards.push(
      {
        step: '01',
        label: '结构结论',
        value: rule.value?.daily_structure?.structure_conclusion || '-',
        note: rule.value?.daily_structure?.pattern_integrity || '-',
        tone: 'watch',
      },
      {
        step: '02',
        label: '关键防守',
        value: formatPrice(rule.value?.key_levels?.defense_level),
        note: '跌破后重新评估',
        tone: 'risk',
      },
    )
  }

  return cards
})
const snapshotCards = computed(() => ([
  {
    label: '市场环境',
    value: rule.value?.market_context?.market_env_tag || '-',
    tip: rule.value?.market_context?.stock_market_alignment || '-',
    tone: 'market',
  },
  {
    label: '个股地位',
    value: rule.value?.direction_position?.stock_role || '-',
    tip: rule.value?.direction_position?.sector_level || '-',
    tone: 'role',
  },
  {
    label: '日线阶段',
    value: rule.value?.daily_structure?.stage_position || '-',
    tip: rule.value?.daily_structure?.structure_conclusion || '-',
    tone: 'structure',
  },
  {
    label: '关键防守',
    value: formatPrice(rule.value?.key_levels?.defense_level),
    tip: defenseLevelsText.value,
    tone: 'defense',
  },
]))
const defenseLevelsText = computed(() => {
  const prices = joinPrices(rule.value?.key_levels?.support_levels)
  return prices === '-' ? '支撑位待确认' : `支撑 ${prices}`
})
const invalidationSummary = computed(() => {
  if (rule.value?.buy_view?.buy_invalid_cond) {
    return `失效条件：${rule.value.buy_view.buy_invalid_cond}`
  }
  if (rule.value?.sell_view?.sell_trigger_cond || rule.value?.sell_view?.sell_reason) {
    return `持仓处理：${rule.value.sell_view.sell_trigger_cond || rule.value.sell_view.sell_reason}`
  }
  if (rule.value?.key_levels?.defense_level !== null && rule.value?.key_levels?.defense_level !== undefined) {
    return `防守位 ${formatPrice(rule.value.key_levels.defense_level)}，跌破后要重新评估结构。`
  }
  return '当前没有明确失效条件字段，建议结合关键位和量价关系判断。'
})
const contextItems = computed(() => ([
  { label: '请求交易日', value: displayTradeDate.value || '-' },
  { label: '实际行情日', value: data.value?.resolved_trade_date || displayTradeDate.value || '-' },
  { label: '报价时间', value: formatQuoteTime(rule.value?.basic_info?.quote_time) },
  { label: '数据来源', value: rule.value?.basic_info?.data_source || '规则快照' },
]))
const evidenceBlocks = computed(() => ([
  {
    id: 'market-position',
    kicker: '环境与角色',
    title: '市场与方向地位',
    summary: `${rule.value?.market_context?.market_env_tag || '-'} · ${rule.value?.direction_position?.stock_role || '-'}`,
    items: [
      { label: '当前市场状态', value: rule.value?.market_context?.market_phase || '-' },
      { label: '顺势 / 逆势', value: rule.value?.market_context?.stock_market_alignment || '-' },
      { label: '所属方向', value: rule.value?.direction_position?.direction_name || '-' },
      { label: '板块级别', value: rule.value?.direction_position?.sector_level || '-' },
      { label: '板块状态', value: rule.value?.direction_position?.sector_trend || '-' },
      { label: '相对强弱', value: rule.value?.direction_position?.relative_strength || '-' },
    ],
    note: rule.value?.market_context?.market_comment || '',
    highlight: rule.value?.market_context?.tolerance_comment || '',
    copy: mergeReportContent(['market_context', 'direction_position']),
  },
  {
    id: 'structure-strength',
    kicker: '结构与节奏',
    title: '日线结构与短线强度',
    summary: `${rule.value?.daily_structure?.stage_position || '-'} · ${rule.value?.intraday_strength?.strength_level || '-'}`,
    items: [
      { label: '均线位置', value: rule.value?.daily_structure?.ma_position_summary || '-' },
      { label: '20日区间', value: rule.value?.daily_structure?.range_position_20d || '-' },
      { label: '60日区间', value: rule.value?.daily_structure?.range_position_60d || '-' },
      { label: '涨跌幅', value: formatSignedPct(rule.value?.intraday_strength?.change_pct), valueClass: pctClass(rule.value?.intraday_strength?.change_pct) },
      { label: '换手率', value: formatPct(rule.value?.intraday_strength?.turnover_rate) },
      { label: '量比', value: formatNumber(rule.value?.intraday_strength?.vol_ratio) },
    ],
    note: joinSegments([
      rule.value?.intraday_strength?.candle_label,
      rule.value?.intraday_strength?.close_position,
      rule.value?.intraday_strength?.volume_state,
    ]),
    highlight: rule.value?.daily_structure?.structure_conclusion || '',
    copy: mergeReportContent(['daily_structure', 'intraday_strength']),
  },
  {
    id: 'fund-peer',
    kicker: '筹码与同类',
    title: '资金质量与横向对比',
    summary: `${rule.value?.fund_quality?.cash_flow_quality || '-'} · ${rule.value?.peer_comparison?.relative_strength || '-'}`,
    items: [
      { label: '最近资金变化', value: rule.value?.fund_quality?.recent_fund_flow || '-' },
      { label: '大单参与', value: rule.value?.fund_quality?.big_order_status || '-' },
      { label: '放量特征', value: rule.value?.fund_quality?.volume_behavior || '-' },
      { label: '同类强弱', value: rule.value?.peer_comparison?.relative_strength || '-' },
      { label: '辨识度', value: rule.value?.peer_comparison?.recognizability || '-' },
      { label: '领涨样本', value: peerPreview.value },
    ],
    note: rule.value?.peer_comparison?.note || rule.value?.fund_quality?.note || '',
    highlight: peerLeadingMove.value,
    copy: mergeReportContent(['fund_quality', 'peer_comparison']),
  },
  {
    id: 'valuation-key-levels',
    kicker: '约束与边界',
    title: '估值属性与关键位',
    summary: `${rule.value?.valuation_profile?.drive_type || '-'} · 防守 ${formatPrice(rule.value?.key_levels?.defense_level)}`,
    items: [
      { label: 'PE', value: formatNumber(rule.value?.valuation_profile?.pe) },
      { label: 'PB', value: formatNumber(rule.value?.valuation_profile?.pb) },
      { label: 'PS', value: formatNumber(rule.value?.valuation_profile?.ps) },
      { label: '市值(亿)', value: formatNumber(rule.value?.valuation_profile?.market_value) },
      { label: '压力位', value: joinPrices(rule.value?.key_levels?.pressure_levels) },
      { label: '支撑位', value: joinPrices(rule.value?.key_levels?.support_levels) },
    ],
    note: rule.value?.key_levels?.note || rule.value?.valuation_profile?.note || '',
    highlight: joinSegments([
      rule.value?.valuation_profile?.valuation_level,
      rule.value?.valuation_profile?.drive_type,
    ]),
    copy: mergeReportContent(['valuation_profile', 'key_levels']),
  },
]))
const peerPreview = computed(() => {
  const firstPeer = rule.value?.peer_comparison?.peers?.[0]
  if (!firstPeer) return '暂无足够样本'
  return `${firstPeer.stock_name} ${formatSignedPct(firstPeer.change_pct)}`
})
const peerLeadingMove = computed(() => {
  const peers = rule.value?.peer_comparison?.peers || []
  if (!peers.length) return '暂无足够同类样本。'
  return peers
    .slice(0, 3)
    .map((peer) => `${peer.stock_name} ${formatSignedPct(peer.change_pct)} ${peer.role_hint || ''}`.trim())
    .join(' / ')
})
const visibleReportSections = computed(() => (
  reportSections.value.filter((section) => section?.content && section.content !== '-')
))

watch(
  () => [props.modelValue, props.tsCode, props.defaultTarget],
  ([visible, tsCode, defaultTarget]) => {
    if (!visible) return
    activeTarget.value = defaultTarget || '观察型'
    if (tsCode) loadData()
  }
)

const handleClose = () => {
  emit('update:modelValue', false)
}

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const fetchCheckupLlm = async ({ forceLlmRefresh = false, seq } = {}) => {
  if (!data.value?.rule_snapshot) return
  const res = await stockApi.checkupLlm(
    {
      rule_snapshot: data.value.rule_snapshot,
      trade_date: displayTradeDate.value,
      checkup_target: activeTarget.value,
      force_llm_refresh: forceLlmRefresh
    },
    { timeout: CHECKUP_TIMEOUT }
  )
  const payload = res.data || {}
  if (payload.code && payload.code !== 200) {
    throw new Error(payload.message || '加载 LLM 解读失败')
  }
  if (seq !== undefined && seq !== checkupRequestSeq.value) return
  const inner = payload.data || {}
  data.value = {
    ...data.value,
    llm_report: inner.llm_report ?? data.value.llm_report,
    llm_status: inner.llm_status ?? data.value.llm_status
  }
}

const loadData = async (options = {}) => {
  if (!props.tsCode) return
  const mySeq = ++checkupRequestSeq.value
  const forceLlmRefresh = Boolean(options.forceLlmRefresh)
  const hadData = Boolean(data.value)

  if (forceLlmRefresh) {
    if (!data.value?.rule_snapshot) {
      ElMessage.warning('暂无规则快照，无法单独刷新解读')
      return
    }
    llmRefreshing.value = true
    try {
      await fetchCheckupLlm({ forceLlmRefresh: true, seq: mySeq })
    } catch (error) {
      const isTimeout = error?.code === 'ECONNABORTED' || String(error?.message || '').toLowerCase().includes('timeout')
      const fallbackMessage = isTimeout ? '解读请求超时，请稍后重试' : (error?.message || '刷新解读失败')
      ElMessage.error(fallbackMessage)
    } finally {
      llmRefreshing.value = false
    }
    return
  }

  loading.value = true
  try {
    const res = await stockApi.checkup(
      props.tsCode,
      displayTradeDate.value,
      activeTarget.value,
      { includeLlm: false, forceLlmRefresh: false, timeout: CHECKUP_TIMEOUT }
    )
    const payload = res.data || {}
    if (payload.code && payload.code !== 200) {
      throw new Error(payload.message || '加载个股体检失败')
    }
    if (mySeq !== checkupRequestSeq.value) return
    data.value = payload.data || null
  } catch (error) {
    if (!hadData) data.value = null
    const isTimeout = error?.code === 'ECONNABORTED' || String(error?.message || '').toLowerCase().includes('timeout')
    const fallbackMessage = isTimeout ? '个股体检超时，请稍后重试' : (error?.message || '加载个股体检失败')
    ElMessage.error(hadData ? `刷新失败，当前仍显示上一版结果。${fallbackMessage}` : fallbackMessage)
  } finally {
    loading.value = false
  }

  if (mySeq !== checkupRequestSeq.value) return
  if (!data.value?.rule_snapshot) return
  const st = data.value.llm_status
  if (st?.status !== 'pending') return

  llmRefreshing.value = true
  try {
    await fetchCheckupLlm({ forceLlmRefresh: false, seq: mySeq })
  } catch (error) {
    const isTimeout = error?.code === 'ECONNABORTED' || String(error?.message || '').toLowerCase().includes('timeout')
    const fallbackMessage = isTimeout ? '解读请求超时，可稍后点击「刷新解读」重试' : (error?.message || '加载 LLM 解读失败')
    ElMessage.warning(fallbackMessage)
  } finally {
    llmRefreshing.value = false
  }
}

const refreshLlm = async () => {
  const mySeq = ++checkupRequestSeq.value
  if (!data.value?.rule_snapshot) {
    ElMessage.warning('暂无规则快照，无法刷新解读')
    return
  }
  llmRefreshing.value = true
  try {
    await fetchCheckupLlm({ forceLlmRefresh: true, seq: mySeq })
    if (mySeq !== checkupRequestSeq.value) return
    if (data.value) ElMessage.success('解读刷新完成')
  } catch (error) {
    const isTimeout = error?.code === 'ECONNABORTED' || String(error?.message || '').toLowerCase().includes('timeout')
    const fallbackMessage = isTimeout ? '解读请求超时，请稍后重试' : (error?.message || '刷新解读失败')
    ElMessage.error(fallbackMessage)
  } finally {
    llmRefreshing.value = false
  }
}

const reportContent = (key) => {
  const section = reportSections.value.find((item) => item.key === key)
  return section?.content || ''
}

const mergeReportContent = (keys) => {
  const parts = keys
    .map((key) => reportContent(key))
    .filter(Boolean)
  return parts.join('\n\n')
}

const joinSegments = (items) => items.filter(Boolean).join(' / ')

const formatQuoteTime = (value) => {
  if (!value) return '-'
  return formatLocalDateTime(value) || '-'
}

const joinList = (items) => (items?.length ? items.join(' / ') : '-')
const joinPrices = (items) => (items?.length ? items.map((item) => formatPrice(item)).join(' / ') : '-')

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(2)
}

const formatPrice = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(2)
}

const formatPct = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toFixed(2)}%`
}

const formatSignedPct = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const num = Number(value)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const formatBoolean = (value) => {
  if (value === true) return '可执行'
  if (value === false) return '暂不执行'
  return '-'
}

const pctClass = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return ''
  if (Number(value) > 0) return 'text-red'
  if (Number(value) < 0) return 'text-green'
  return 'text-neutral'
}
</script>

<style scoped>
.drawer-header {
  width: 100%;
}

.header-shell {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
  width: 100%;
  padding: 6px 2px 2px;
}

.header-main {
  display: grid;
  gap: 10px;
  min-width: 0;
  max-width: 760px;
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.header-title {
  font-size: clamp(1.25rem, 2vw, 1.7rem);
  font-weight: 700;
  letter-spacing: 0.01em;
}

.header-strategy-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.header-subtitle {
  color: rgba(255, 255, 255, 0.56);
  line-height: 1.7;
  font-size: 13px;
}

.header-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.header-meta-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.78);
  font-size: 12px;
}

.header-meta-label,
.header-group-label {
  color: rgba(255, 255, 255, 0.42);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 11px;
}

.header-actions {
  display: grid;
  gap: 12px;
  justify-items: end;
  flex-shrink: 0;
}

.header-target-group {
  display: grid;
  gap: 8px;
  justify-items: end;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.header-button-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.drawer-body {
  display: grid;
  gap: 18px;
}

.refresh-banner {
  position: sticky;
  top: 0;
  z-index: 6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(255, 184, 77, 0.22);
  background:
    linear-gradient(90deg, rgba(255, 184, 77, 0.16), rgba(255, 184, 77, 0.06)),
    rgba(18, 20, 28, 0.88);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
  backdrop-filter: blur(14px);
}

.refresh-banner-llm {
  border-color: rgba(88, 176, 255, 0.2);
  background:
    linear-gradient(90deg, rgba(88, 176, 255, 0.16), rgba(88, 176, 255, 0.06)),
    rgba(18, 20, 28, 0.88);
}

.refresh-banner-main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.refresh-banner-spinner {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  border: 2px solid rgba(255, 255, 255, 0.18);
  border-top-color: #ffcb7a;
  animation: refresh-spin 0.85s linear infinite;
  flex-shrink: 0;
}

.refresh-banner-llm .refresh-banner-spinner {
  border-top-color: #82b8ff;
}

.refresh-banner-copy {
  display: grid;
  gap: 2px;
}

.refresh-banner-copy strong {
  font-size: 14px;
  color: #fff3dc;
}

.refresh-banner-llm .refresh-banner-copy strong {
  color: #e2efff;
}

.refresh-banner-copy span {
  color: rgba(255, 255, 255, 0.76);
  line-height: 1.6;
  font-size: 13px;
}

.refresh-banner-tag {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.82);
  font-size: 12px;
  flex-shrink: 0;
}

.content-shell {
  display: grid;
  gap: 18px;
  transition: opacity 180ms ease, filter 180ms ease, transform 180ms ease;
}

.content-shell-refreshing {
  opacity: 0.68;
  filter: saturate(0.82);
}

.hero-stage {
  position: relative;
  display: grid;
  gap: 14px;
  padding: 18px;
  overflow: hidden;
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background:
    radial-gradient(circle at top left, rgba(244, 193, 77, 0.08), transparent 26%),
    radial-gradient(circle at right center, rgba(88, 176, 255, 0.12), transparent 30%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), 0 18px 46px rgba(5, 10, 20, 0.2);
}

.hero-orb {
  position: absolute;
  border-radius: 999px;
  pointer-events: none;
  filter: blur(8px);
  opacity: 0.7;
}

.hero-orb-a {
  top: -64px;
  left: -48px;
  width: 180px;
  height: 180px;
  background: radial-gradient(circle, rgba(243, 194, 77, 0.18), transparent 70%);
}

.hero-orb-b {
  right: 18%;
  bottom: -90px;
  width: 240px;
  height: 240px;
  background: radial-gradient(circle, rgba(79, 118, 217, 0.2), transparent 72%);
}

.hero-layout {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.95fr);
  gap: 16px;
  align-items: start;
}

.hero-panel,
.action-panel,
.decision-card,
.evidence-card,
.detail-card,
.snapshot-card {
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
  box-shadow: 0 16px 32px rgba(6, 10, 18, 0.16);
}

.hero-panel {
  display: grid;
  gap: 18px;
  padding: 22px;
  background:
    radial-gradient(circle at right top, rgba(79, 118, 217, 0.16), transparent 34%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.055));
}

.hero-badge-stack {
  display: grid;
  gap: 8px;
  justify-items: start;
}

.hero-top {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.hero-badge {
  min-width: 118px;
  min-height: 104px;
  padding: 20px 18px;
  border-radius: 24px;
  color: #fff;
  text-align: center;
  font-weight: 800;
  letter-spacing: 0.04em;
  display: grid;
  place-items: center;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 12px 30px rgba(0, 0, 0, 0.22);
}

.hero-badge-caption {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.badge-buy {
  background: linear-gradient(135deg, #1d8b6f, #2fcf9a);
}

.badge-break {
  background: linear-gradient(135deg, #4f76d9, #67a5ff);
}

.badge-watch {
  background: linear-gradient(135deg, #d39b24, #f3c24d);
}

.badge-pass {
  background: linear-gradient(135deg, #d84d58, #ff7a7f);
}

.hero-copy {
  display: grid;
  gap: 10px;
  max-width: 760px;
}

.hero-kicker,
.panel-kicker,
.decision-kicker,
.section-kicker,
.evidence-kicker,
.snapshot-label,
.status-label,
.execution-label,
.sub-title {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-title {
  font-size: clamp(1.22rem, 2vw, 1.66rem);
  font-weight: 700;
  letter-spacing: 0.01em;
}

.hero-desc,
.panel-copy,
.decision-note,
.section-note,
.execution-note,
.snapshot-tip,
.sub-copy {
  color: var(--color-text-sec);
  line-height: 1.7;
}

.hero-conclusion-card {
  display: grid;
  gap: 10px;
  padding: 18px 20px;
  border-radius: 22px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.025)),
    rgba(14, 18, 28, 0.32);
  border: 1px solid rgba(255, 255, 255, 0.07);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.hero-conclusion-label {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-conclusion {
  font-size: clamp(1.35rem, 2.7vw, 2rem);
  font-weight: 700;
  line-height: 1.5;
  color: #f5f7fb;
}

.hero-conclusion-note {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.58);
  line-height: 1.7;
}

.hero-bottom {
  display: grid;
  gap: 12px;
}

.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hero-tag {
  padding: 8px 13px;
  border-radius: 999px;
  background: rgba(88, 176, 255, 0.08);
  border: 1px solid rgba(88, 176, 255, 0.16);
  color: #d7e5ff;
  font-size: 12px;
}

.status-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 14px;
}

.status-success {
  border: 1px solid rgba(47, 207, 154, 0.25);
  background: rgba(47, 207, 154, 0.08);
}

.status-warning {
  border: 1px solid rgba(243, 194, 77, 0.25);
  background: rgba(243, 194, 77, 0.08);
}

.status-muted {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.action-panel {
  display: grid;
  gap: 18px;
  padding: 22px;
  background:
    radial-gradient(circle at left bottom, rgba(47, 207, 154, 0.14), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.018));
}

.action-panel-head {
  display: grid;
  gap: 10px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.panel-head {
  display: grid;
  gap: 6px;
}

.panel-title {
  font-size: 1.05rem;
  line-height: 1.5;
}

.execution-grid {
  display: grid;
  gap: 10px;
}

.execution-card {
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr);
  gap: 12px;
  padding: 14px 15px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.028);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.execution-card-primary {
  background: linear-gradient(135deg, rgba(88, 176, 255, 0.1), rgba(88, 176, 255, 0.03));
  border-color: rgba(88, 176, 255, 0.2);
}

.execution-card-watch {
  border-left: 3px solid rgba(243, 194, 77, 0.7);
}

.execution-card-focus {
  border-left: 3px solid rgba(88, 176, 255, 0.82);
}

.execution-card-risk {
  border-left: 3px solid rgba(255, 122, 127, 0.78);
}

.execution-card-neutral {
  border-left: 3px solid rgba(255, 255, 255, 0.16);
}

.execution-step {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  color: rgba(255, 255, 255, 0.68);
  background: rgba(255, 255, 255, 0.04);
}

.execution-copy,
.execution-value,
.snapshot-value,
.section-emphasis,
.detail-card-title,
.report-title,
.strategy-pill,
.sub-panel {
  display: grid;
  gap: 6px;
}

.execution-value,
.snapshot-value,
.section-emphasis,
.detail-card-title,
.report-title,
.strategy-pill {
  font-weight: 700;
  line-height: 1.7;
}

.sub-panel {
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.snapshot-grid,
.decision-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.decision-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.snapshot-card {
  display: grid;
  gap: 8px;
  padding: 16px 16px 18px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.038), rgba(255, 255, 255, 0.02)),
    rgba(255, 255, 255, 0.02);
}

.snapshot-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.snapshot-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.28);
  box-shadow: 0 0 0 6px rgba(255, 255, 255, 0.03);
}

.snapshot-card-market .snapshot-dot {
  background: #f3c24d;
}

.snapshot-card-role .snapshot-dot {
  background: #67a5ff;
}

.snapshot-card-structure .snapshot-dot {
  background: #88a6ff;
}

.snapshot-card-defense .snapshot-dot {
  background: #ff8d9b;
}

.snapshot-value {
  font-size: 1.42rem;
  line-height: 1.1;
}

.decision-card {
  display: grid;
  gap: 12px;
  padding: 16px 18px;
  border-radius: 18px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.028), rgba(255, 255, 255, 0.016)),
    rgba(255, 255, 255, 0.018);
  box-shadow: none;
}

.decision-head {
  display: grid;
  gap: 4px;
}

.decision-card-risk {
  border-color: rgba(255, 122, 127, 0.12);
}

.decision-card-context {
  border-color: rgba(88, 176, 255, 0.12);
}

.decision-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.decision-footnote {
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.62);
  line-height: 1.7;
  font-size: 13px;
}

.decision-note-muted {
  color: rgba(255, 255, 255, 0.5);
}

.risk-chip {
  padding: 6px 10px;
  border-radius: 999px;
  color: #ffc0c4;
  background: rgba(255, 122, 127, 0.08);
  border: 1px solid rgba(255, 122, 127, 0.15);
  font-size: 12px;
}

.context-pill-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.context-pill {
  display: grid;
  gap: 6px;
  padding: 12px 13px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.026);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.context-pill span {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.46);
}

.context-pill strong {
  line-height: 1.6;
  color: #f1f5ff;
}

.evidence-section {
  display: grid;
  gap: 14px;
}

.section-heading {
  display: grid;
  gap: 4px;
}

.section-heading h3 {
  margin: 0;
  font-size: 1.08rem;
}

.section-heading-copy {
  margin: 0;
  color: rgba(255, 255, 255, 0.52);
  line-height: 1.7;
  font-size: 13px;
}

.evidence-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.evidence-card {
  display: grid;
  gap: 14px;
  padding: 18px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.032), rgba(255, 255, 255, 0.018)),
    rgba(255, 255, 255, 0.018);
}

.evidence-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.evidence-title {
  margin-top: 4px;
  font-size: 1rem;
  font-weight: 700;
}

.evidence-summary {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-text-sec);
  font-size: 12px;
  white-space: nowrap;
}

.evidence-highlight {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(88, 176, 255, 0.08);
  border: 1px solid rgba(88, 176, 255, 0.14);
  color: #eef4ff;
  font-weight: 700;
  line-height: 1.7;
}

.evidence-fact-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.evidence-fact-grid .data-item {
  min-height: 68px;
  padding: 12px 14px;
  border-radius: 14px;
  border-bottom: none;
  background: rgba(255, 255, 255, 0.022);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.evidence-fact-grid .data-item strong {
  text-align: left;
}

.evidence-details {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 12px;
}

.evidence-details-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  list-style: none;
  color: rgba(255, 255, 255, 0.72);
  font-size: 13px;
  font-weight: 600;
}

.evidence-details-summary::-webkit-details-marker {
  display: none;
}

.evidence-details-action {
  color: rgba(255, 255, 255, 0.46);
  font-weight: 400;
}

.evidence-note {
  margin-top: 12px;
}

.evidence-copy {
  margin-top: 12px;
}

.data-list {
  display: grid;
  gap: 8px;
}

.compact-data-list {
  gap: 4px;
}

.data-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.data-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.data-item span {
  color: var(--color-text-sec);
  flex-shrink: 0;
}

.data-item strong {
  text-align: right;
}

.llm-copy {
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(88, 176, 255, 0.08);
  border: 1px solid rgba(88, 176, 255, 0.16);
  line-height: 1.8;
  white-space: pre-line;
}

.details-disclosure {
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background:
    radial-gradient(circle at top right, rgba(88, 176, 255, 0.08), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.024), rgba(255, 255, 255, 0.014));
  overflow: hidden;
}

.details-summary {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 18px 20px;
  cursor: pointer;
  list-style: none;
  background: rgba(255, 255, 255, 0.018);
}

.details-summary::-webkit-details-marker {
  display: none;
}

.details-summary-copy {
  display: grid;
  gap: 4px;
}

.details-kicker {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.42);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.details-summary-side {
  display: grid;
  gap: 8px;
  justify-items: end;
}

.details-summary-pill {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
}

.details-summary-action {
  color: var(--color-text-sec);
  font-size: 13px;
}

.details-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  padding: 0 18px 18px;
}

.detail-card {
  display: grid;
  gap: 12px;
  padding: 18px;
  border-radius: 18px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.028), rgba(255, 255, 255, 0.016)),
    rgba(255, 255, 255, 0.014);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.detail-card-full {
  grid-column: 1 / -1;
}

.detail-card-head {
  display: grid;
  gap: 4px;
}

.detail-card-kicker {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.42);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.strategy-pill {
  display: inline-flex;
  width: fit-content;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
}

.detail-note-band {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.62);
  line-height: 1.7;
}

.report-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.report-card {
  display: grid;
  gap: 8px;
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.report-card-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.report-index {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: rgba(88, 176, 255, 0.08);
  border: 1px solid rgba(88, 176, 255, 0.14);
  color: #d5e6ff;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.06em;
}

.report-copy {
  line-height: 1.8;
  color: var(--color-text-sec);
}

@keyframes refresh-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.text-red {
  color: #ff7b86;
}

.text-green {
  color: #35c48b;
}

.text-neutral {
  color: var(--color-text-pri);
}

@media (max-width: 1380px) {
  .hero-layout,
  .snapshot-grid,
  .decision-grid,
  .evidence-grid,
  .details-grid,
  .report-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1200px) {
  .header-shell,
  .hero-top,
  .evidence-head,
  .details-summary {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-actions,
  .header-target-group {
    justify-items: start;
  }

  .details-summary-side {
    justify-items: start;
  }

  .header-button-row {
    justify-content: flex-start;
  }

  .refresh-banner {
    flex-direction: column;
    align-items: flex-start;
  }

  .data-item {
    flex-direction: column;
  }

  .execution-card {
    grid-template-columns: 1fr;
  }

  .context-pill-grid {
    grid-template-columns: 1fr;
  }

  .evidence-fact-grid {
    grid-template-columns: 1fr;
  }

  .evidence-summary {
    white-space: normal;
  }
}
</style>
