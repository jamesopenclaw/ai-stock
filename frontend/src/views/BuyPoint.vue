<template>
  <div class="buy-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>买点分析</span>
            <span v-if="displayDate" class="header-date">{{ displayDate }}</span>
          </div>
          <el-button @click="loadData" :loading="loading">刷新</el-button>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="8" animated />
      <template v-else>
        <div v-if="buyData.market_env_tag" class="decision-overview">
          <div class="overview-main">
            <div class="market-mode-chip" :class="envChipClass(buyData.market_env_tag)">
              {{ buyData.market_env_tag }}
            </div>
            <div class="overview-copy">
              <div class="overview-title">{{ envHeadline(buyData.market_env_tag) }}</div>
              <div class="overview-desc">{{ envGuidance(buyData.market_env_tag) }}</div>
            </div>
          </div>

          <div class="overview-stats">
            <div class="stat-card stat-buy">
              <span class="stat-label">可买</span>
              <strong class="stat-value">{{ buyData.available_buy_points?.length || 0 }}</strong>
              <span class="stat-tip">可直接跟盘</span>
            </div>
            <div class="stat-card stat-watch">
              <span class="stat-label">观察</span>
              <strong class="stat-value">{{ buyData.observe_buy_points?.length || 0 }}</strong>
              <span class="stat-tip">等确认再动</span>
            </div>
            <div class="stat-card stat-skip">
              <span class="stat-label">不买</span>
              <strong class="stat-value">{{ buyData.not_buy_points?.length || 0 }}</strong>
              <span class="stat-tip">今天先放弃</span>
            </div>
          </div>

          <div class="overview-rules">
            <div v-for="rule in envChecklist(buyData.market_env_tag)" :key="rule" class="rule-chip">
              {{ rule }}
            </div>
          </div>
        </div>

        <el-tabs v-model="activeTab">
          <el-tab-pane name="available">
            <template #label>
              <span>可买 <em class="tab-count">{{ buyData.available_buy_points?.length || 0 }}</em></span>
            </template>
            <el-empty
              v-if="!buyData.available_buy_points?.length"
              :description="buyData.market_env_tag === '防守' ? '当前是防守环境，只有极少数试错票会出现在这里' : '暂无可买标的'"
            />
            <div v-else class="signal-grid">
              <article
                v-for="point in buyData.available_buy_points"
                :key="point.ts_code"
                class="signal-card signal-card-buy"
              >
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ point.stock_name }}</div>
                    <div class="signal-code">{{ point.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" type="primary">{{ point.buy_point_type }}</el-tag>
                    <el-tag size="small" :type="riskTagType(point.buy_risk_level)">{{ point.buy_risk_level }}风险</el-tag>
                    <el-tag size="small" :type="accountFitType(point.buy_account_fit)">{{ point.buy_account_fit }}</el-tag>
                  </div>
                </div>

                <div class="signal-meta">
                  <span>{{ point.candidate_bucket_tag || '未分层' }}</span>
                  <span>{{ point.candidate_source_tag || '无来源标记' }}</span>
                </div>

                <div class="signal-intent">
                  {{ primaryActionLine(point, buyData.market_env_tag) }}
                </div>

                <div class="quote-strip">
                  <div class="quote-main">
                    <span class="quote-label">最新价</span>
                    <strong class="quote-price">{{ formatPrice(point.buy_current_price) }}</strong>
                    <span :class="['quote-change', priceClass(point.buy_current_change_pct)]">
                      {{ formatSignedPct(point.buy_current_change_pct) }}
                    </span>
                  </div>
                  <div class="quote-side">
                    <span class="quote-pair">
                      距触发
                      <strong :class="priceClass(point.buy_trigger_gap_pct)">{{ formatGap(point.buy_trigger_gap_pct) }}</strong>
                    </span>
                    <span class="quote-pair">
                      距失效
                      <strong :class="invalidGapClass(point.buy_invalid_gap_pct)">{{ formatGap(point.buy_invalid_gap_pct) }}</strong>
                    </span>
                  </div>
                </div>

                <div class="price-strip">
                  <div class="metric-card">
                    <span class="metric-label">触发价</span>
                    <strong class="metric-value">{{ formatPrice(point.buy_trigger_price) }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">失效价</span>
                    <strong class="metric-value">{{ formatPrice(point.buy_invalid_price) }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">量比门槛</span>
                    <strong class="metric-value">{{ formatRatio(point.buy_required_volume_ratio) }}</strong>
                  </div>
                </div>

                <div class="condition-section">
                  <div class="section-kicker">执行清单</div>
                  <div class="condition-panel-grid">
                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">触发</div>
                          <div class="panel-subtitle">先到这个位置再开始盯盘</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ point.buy_trigger_cond }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-confirm">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">确认</div>
                          <div class="panel-subtitle">下面条件没到齐，不算信号成立</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <ul class="condition-bullets">
                          <li v-for="item in splitCond(point.buy_confirm_cond)" :key="item">{{ item }}</li>
                        </ul>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-invalid">
                      <div class="panel-head">
                        <span class="panel-step">3</span>
                        <div>
                          <div class="panel-title">失效</div>
                          <div class="panel-subtitle">出现下面任一条，就不要继续做</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <ul class="condition-bullets condition-bullets-risk">
                          <li v-for="item in splitCond(point.buy_invalid_cond)" :key="item">{{ item }}</li>
                        </ul>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ point.buy_comment || '-' }}</span>
                  <span v-if="point.buy_requires_sector_resonance" class="footer-flag">需要板块共振</span>
                </div>
              </article>
            </div>
          </el-tab-pane>

          <el-tab-pane name="observe">
            <template #label>
              <span>观察 <em class="tab-count">{{ buyData.observe_buy_points?.length || 0 }}</em></span>
            </template>
            <el-empty v-if="!buyData.observe_buy_points?.length" description="暂无观察标的" />
            <div v-else class="signal-grid">
              <article
                v-for="point in buyData.observe_buy_points"
                :key="point.ts_code"
                class="signal-card signal-card-watch"
              >
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ point.stock_name }}</div>
                    <div class="signal-code">{{ point.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" type="warning">{{ point.buy_point_type }}</el-tag>
                    <el-tag size="small" :type="riskTagType(point.buy_risk_level)">{{ point.buy_risk_level }}风险</el-tag>
                  </div>
                </div>

                <div class="signal-meta">
                  <span>{{ point.candidate_bucket_tag || '未分层' }}</span>
                  <span>{{ point.candidate_source_tag || '无来源标记' }}</span>
                </div>

                <div class="signal-intent signal-intent-watch">
                  {{ observeActionLine(point, buyData.market_env_tag) }}
                </div>

                <div class="quote-strip quote-strip-watch">
                  <div class="quote-main">
                    <span class="quote-label">最新价</span>
                    <strong class="quote-price">{{ formatPrice(point.buy_current_price) }}</strong>
                    <span :class="['quote-change', priceClass(point.buy_current_change_pct)]">
                      {{ formatSignedPct(point.buy_current_change_pct) }}
                    </span>
                  </div>
                  <div class="quote-side">
                    <span class="quote-pair">
                      距触发
                      <strong :class="priceClass(point.buy_trigger_gap_pct)">{{ formatGap(point.buy_trigger_gap_pct) }}</strong>
                    </span>
                  </div>
                </div>

                <div class="condition-section">
                  <div class="section-kicker">观察重点</div>
                  <div class="condition-panel-grid condition-panel-grid-watch">
                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">先看</div>
                          <div class="panel-subtitle">先等这个动作出现</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ point.buy_trigger_cond }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-confirm">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">卡点</div>
                          <div class="panel-subtitle">条件没到齐就继续观察</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <ul class="condition-bullets">
                          <li v-for="item in splitCond(point.buy_confirm_cond)" :key="item">{{ item }}</li>
                        </ul>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ point.buy_comment || '-' }}</span>
                  <span class="footer-flag">未到执行位</span>
                </div>
              </article>
            </div>
          </el-tab-pane>

          <el-tab-pane name="skip">
            <template #label>
              <span>不买 <em class="tab-count">{{ buyData.not_buy_points?.length || 0 }}</em></span>
            </template>
            <el-empty v-if="!buyData.not_buy_points?.length" description="暂无明确放弃标的" />
            <div v-else class="skip-list">
              <div v-for="point in buyData.not_buy_points" :key="point.ts_code" class="skip-row">
                <div class="skip-main">
                  <strong>{{ point.stock_name }}</strong>
                  <span class="signal-code">{{ point.ts_code }}</span>
                  <span class="skip-meta">{{ point.candidate_bucket_tag || '未分层' }}</span>
                  <span class="skip-meta">{{ point.buy_point_type }}</span>
                </div>
                <div class="skip-reason">{{ skipReasonLine(point, buyData.market_env_tag) }}</div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { decisionApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const activeTab = ref('available')
const displayDate = ref('')
const buyData = ref({
  market_env_tag: '',
  available_buy_points: [],
  observe_buy_points: [],
  not_buy_points: [],
})

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const envChipClass = (tag) => {
  if (tag === '进攻') return 'chip-attack'
  if (tag === '中性') return 'chip-neutral'
  return 'chip-defense'
}

const envHeadline = (tag) => {
  if (tag === '进攻') return '环境偏进攻，优先看强势确认和突破延续'
  if (tag === '中性') return '环境中性，只做确认过的回踩承接'
  return '环境偏防守，只保留极少数轻仓试错机会'
}

const envGuidance = (tag) => {
  if (tag === '进攻') return '可买列表是今天优先跟盘的对象，先看触发价，再看量比和确认条件。'
  if (tag === '中性') return '先看观察池，只有在确认条件满足时再转为执行，避免盘中追高。'
  return '可买不代表正常开仓，只代表系统允许你对最强核心股做轻仓试错。'
}

const riskTagType = (level) => {
  if (level === '高') return 'danger'
  if (level === '中') return 'warning'
  return 'success'
}

const accountFitType = (fit) => {
  if (fit === '适合') return 'success'
  if (fit === '一般') return 'warning'
  return 'info'
}

const formatPrice = (value) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(2)
}

const formatRatio = (value) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(1)
}

const formatSignedPct = (value) => {
  if (value === null || value === undefined) return '-'
  const num = Number(value)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const formatGap = (value) => {
  if (value === null || value === undefined) return '-'
  const num = Number(value)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const priceClass = (value) => {
  if (value === null || value === undefined) return ''
  if (Number(value) > 0) return 'text-red'
  if (Number(value) < 0) return 'text-green'
  return 'text-neutral'
}

const invalidGapClass = (value) => {
  if (value === null || value === undefined) return ''
  return Number(value) <= 0 ? 'text-red' : 'text-neutral'
}

const splitCond = (text) => {
  if (!text) return ['-']
  return String(text)
    .split('；')
    .map((item) => item.trim())
    .filter(Boolean)
}

const envChecklist = (tag) => {
  if (tag === '进攻') {
    return ['先看强势确认', '触发价到了再看量能', '失效价破位立即放弃']
  }
  if (tag === '中性') {
    return ['优先做回踩承接', '确认条件不够就继续等', '不要用观察票代替可买票']
  }
  return ['只做最强核心股试错', '仓位先轻，不要满上', '确认条件不齐就不动手']
}

const primaryActionLine = (point, envTag) => {
  const trigger = formatPrice(point.buy_trigger_price)
  const invalid = formatPrice(point.buy_invalid_price)
  const prefix = envTag === '防守' ? '轻仓试错' : '执行计划'
  return `${prefix}：到 ${trigger} 附近再看，跌回 ${invalid} 下方就放弃。`
}

const observeActionLine = (point, envTag) => {
  if (envTag === '防守') {
    return '先观察，不抢先手；只有触发和确认都到位才考虑出手。'
  }
  return '这只票先看触发，再等确认，不要把观察票当成已执行信号。'
}

const skipReasonLine = (point, envTag) => {
  if (envTag === '防守' && point.buy_comment) {
    return `${point.buy_comment}，今天不作为正常开仓对象。`
  }
  return point.buy_comment || point.buy_invalid_cond || '不符合执行条件'
}

const loadData = async () => {
  loading.value = true
  try {
    const tradeDate = getLocalDate()
    displayDate.value = tradeDate
    const res = await decisionApi.buyPoint(tradeDate, 30)
    buyData.value = res.data.data
    if (buyData.value.available_buy_points?.length) activeTab.value = 'available'
    else if (buyData.value.observe_buy_points?.length) activeTab.value = 'observe'
    else activeTab.value = 'skip'
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  displayDate.value = getLocalDate()
  loadData()
})
</script>

<style scoped>
.buy-view {
  min-height: 100%;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.card-header-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.header-date {
  font-size: 13px;
  color: var(--color-text-sec);
  letter-spacing: 0.02em;
  font-weight: 400;
}

.decision-overview {
  display: grid;
  gap: 18px;
  margin-bottom: 24px;
  padding: 20px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(92, 122, 255, 0.12), transparent 32%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.04));
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.overview-main {
  display: flex;
  align-items: center;
  gap: 18px;
}

.market-mode-chip {
  min-width: 112px;
  padding: 16px 18px;
  border-radius: 18px;
  font-size: clamp(1.5rem, 2.2vw, 2rem);
  font-weight: 800;
  text-align: center;
  letter-spacing: 0.08em;
  color: #fff;
}

.chip-attack {
  background: linear-gradient(135deg, #178f63, #22c58b);
}

.chip-neutral {
  background: linear-gradient(135deg, #d39b24, #f3c24d);
}

.chip-defense {
  background: linear-gradient(135deg, #d84d58, #ff7a7f);
}

.overview-copy {
  display: grid;
  gap: 8px;
}

.overview-title {
  font-size: 1.05rem;
  font-weight: 700;
}

.overview-desc {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.overview-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.overview-rules {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.rule-chip {
  padding: 8px 12px;
  border-radius: 999px;
  color: var(--color-text-sec);
  font-size: 13px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.stat-card {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-sec);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.stat-value {
  font-size: 1.6rem;
  line-height: 1;
}

.stat-tip {
  color: var(--color-text-sec);
  font-size: 13px;
}

.stat-buy .stat-value {
  color: #44d19f;
}

.stat-watch .stat-value {
  color: #f3c24d;
}

.stat-skip .stat-value {
  color: #b8bfcc;
}

.tab-count {
  font-style: normal;
  color: var(--color-text-sec);
  margin-left: 4px;
}

.signal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.signal-card {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
}

.signal-card-buy {
  box-shadow: inset 0 1px 0 rgba(80, 190, 140, 0.12);
}

.signal-card-watch {
  box-shadow: inset 0 1px 0 rgba(243, 194, 77, 0.12);
}

.signal-card-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.signal-stock {
  font-size: 1.05rem;
  font-weight: 700;
}

.signal-code {
  font-size: 13px;
  color: var(--color-text-sec);
}

.signal-badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.signal-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--color-text-sec);
  font-size: 13px;
}

.signal-meta span {
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
}

.signal-intent {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(68, 209, 159, 0.08);
  border: 1px solid rgba(68, 209, 159, 0.14);
  line-height: 1.6;
}

.signal-intent-watch {
  background: rgba(243, 194, 77, 0.08);
  border-color: rgba(243, 194, 77, 0.16);
}

.quote-strip {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(9, 14, 23, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.quote-strip-watch {
  background: rgba(255, 255, 255, 0.025);
}

.quote-main {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.quote-label {
  color: var(--color-text-sec);
  font-size: 12px;
}

.quote-price {
  font-size: 1.45rem;
  line-height: 1;
}

.quote-change {
  font-size: 13px;
  font-weight: 600;
}

.quote-side {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.quote-pair {
  color: var(--color-text-sec);
  font-size: 13px;
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
}

.price-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  display: grid;
  gap: 6px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(9, 14, 23, 0.35);
}

.metric-label {
  color: var(--color-text-sec);
  font-size: 12px;
}

.metric-value {
  font-size: 1.15rem;
}

.condition-section {
  display: grid;
  gap: 10px;
}

.section-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.condition-panel-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.condition-panel-grid-watch {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.condition-panel {
  display: grid;
  gap: 12px;
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
  min-width: 0;
}

.condition-panel-trigger {
  background: linear-gradient(180deg, rgba(68, 209, 159, 0.06), rgba(255, 255, 255, 0.02));
}

.condition-panel-confirm {
  background: linear-gradient(180deg, rgba(92, 122, 255, 0.06), rgba(255, 255, 255, 0.02));
}

.condition-panel-invalid {
  background: linear-gradient(180deg, rgba(255, 122, 127, 0.08), rgba(255, 255, 255, 0.02));
}

.panel-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.panel-step {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: rgba(255, 255, 255, 0.14);
  flex-shrink: 0;
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
}

.panel-subtitle {
  font-size: 12px;
  color: var(--color-text-sec);
  line-height: 1.5;
  margin-top: 2px;
}

.panel-body {
  min-width: 0;
}

.condition-title {
  line-height: 1.6;
  font-size: 15px;
}

.condition-bullets {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  line-height: 1.6;
}

.condition-bullets-risk li {
  color: #ffc0c4;
}

.signal-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  color: var(--color-text-sec);
  font-size: 13px;
}

.footer-flag {
  white-space: nowrap;
  color: #8ab4ff;
}

.skip-list {
  display: grid;
  gap: 10px;
}

.skip-row {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.skip-main {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.skip-meta {
  color: var(--color-text-sec);
  font-size: 13px;
}

.skip-reason {
  color: var(--color-text-sec);
  line-height: 1.5;
}

@media (max-width: 900px) {
  .overview-main {
    align-items: flex-start;
    flex-direction: column;
  }

  .overview-stats {
    grid-template-columns: 1fr;
  }

  .overview-rules {
    flex-direction: column;
  }

  .price-strip {
    grid-template-columns: 1fr;
  }

  .condition-panel-grid,
  .condition-panel-grid-watch {
    grid-template-columns: 1fr;
  }

  .quote-strip {
    align-items: flex-start;
    flex-direction: column;
  }

  .quote-side {
    justify-content: flex-start;
  }

  .signal-footer {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
