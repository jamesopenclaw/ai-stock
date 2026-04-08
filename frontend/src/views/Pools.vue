<template>
  <div class="pools-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>三池分类</span>
            <span v-if="displayDate" class="header-date">{{ displayDate }}</span>
            <span
              v-if="poolsData.resolved_trade_date && poolsData.resolved_trade_date !== displayDate"
              class="header-date"
            >
              实际候选日 {{ poolsData.resolved_trade_date }}
            </span>
            <span
              v-if="poolsData.sector_scan_trade_date && poolsData.sector_scan_trade_date !== displayDate"
              class="header-date"
            >
              板块请求日 {{ poolsData.sector_scan_trade_date }}
            </span>
            <span
              v-if="poolsData.sector_scan_resolved_trade_date"
              class="header-date"
            >
              板块实际日 {{ poolsData.sector_scan_resolved_trade_date }}
            </span>
          </div>
          <div class="header-actions">
            <el-radio-group v-model="poolMode" size="small" class="mode-switch">
              <el-radio-button label="stable">稳定模式</el-radio-button>
              <el-radio-button label="radar">实时雷达</el-radio-button>
            </el-radio-group>
            <el-button @click="handleRefresh" :loading="refreshButtonLoading">
              {{ poolsData.refresh_in_progress ? '刷新中...' : '刷新' }}
            </el-button>
          </div>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="8" animated />
      <template v-else>
        <el-alert
          v-if="loadError"
          :title="loadError"
          type="error"
          show-icon
          :closable="false"
          class="page-alert"
        />
        <el-alert
          v-if="isRadarMode"
          :title="radarModeBanner"
          type="warning"
          show-icon
          :closable="false"
          class="page-alert"
        />
        <DataFreshnessBar
          :items="poolsFreshnessItems"
          :note="poolsFreshnessNote"
        />
        <section class="ops-toolbar">
          <div class="ops-toolbar-main">
            <div class="ops-toolbar-copy">
              <div class="section-kicker">今日操作栏</div>
              <div class="ops-toolbar-title">{{ operatorBarTitle }}</div>
              <div class="ops-toolbar-desc">{{ operatorBarDesc }}</div>
            </div>
            <div class="ops-toolbar-context">
              <span class="ops-context-chip">{{ isRadarMode ? '实时雷达' : '稳定模式' }}</span>
              <span class="ops-context-chip">{{ marketEnvironmentTagLabel }}</span>
              <span v-if="primaryDirectionItems.length" class="ops-context-chip">
                主线 {{ primaryDirectionItems[0].name }}
              </span>
              <span class="ops-context-chip">{{ globalTradeGate.status }}</span>
            </div>
          </div>
          <div class="ops-toolbar-actions">
            <button
              v-for="step in decisionSteps"
              :key="`ops-${step.key}`"
              type="button"
              class="ops-step-button"
              :class="`ops-step-button-${step.tone}`"
              @click="activateTab(step.tab, { scroll: true })"
            >
              <span class="ops-step-rank">{{ step.rank }}</span>
              <span class="ops-step-copy">
                <strong>{{ step.title }}</strong>
                <em>{{ step.countLabel }}</em>
              </span>
            </button>
            <el-button text type="primary" @click="router.push({ path: '/buy', query: focusSector ? { focus_sector: focusSector } : {} })">
              去买点分析
            </el-button>
            <el-button text @click="goToSectors(focusSector)">
              看板块扫描
            </el-button>
          </div>
        </section>
        <section class="command-center">
          <article class="summary-card summary-card-decision">
            <div class="summary-card-head">
              <div>
                <div class="summary-kicker">今日结论</div>
                <div class="summary-title-row">
                  <el-tag size="large" effect="dark" :type="globalTradeGate.allow_new_positions ? 'success' : 'danger'">
                    {{ globalTradeGate.status }}
                  </el-tag>
                  <span class="summary-headline summary-headline-action">{{ executionGuidanceTitle }}</span>
                </div>
              </div>
              <div v-if="primaryDecisionStep" class="decision-priority-pill">
                <span>先做</span>
                <strong>{{ primaryDecisionStep.title }}</strong>
              </div>
            </div>
            <div class="summary-copy">{{ executionGuidanceCopy }}</div>
            <div class="summary-chip-row">
              <span class="summary-chip">
                <strong>环境</strong>{{ marketEnvironmentTagLabel }}
              </span>
              <span class="summary-chip">
                <strong>节奏</strong>{{ todayMarketEnv.trading_tempo_label || (todayMarketEnv.breakout_allowed ? '确认后可做' : '先不追') }}
              </span>
              <span v-if="todayMarketEnv.dominant_factor_label" class="summary-chip">
                <strong>主因</strong>{{ todayMarketEnv.dominant_factor_label }}
              </span>
              <span class="summary-chip"><strong>风险</strong>{{ todayMarketEnv.risk_level }}</span>
            </div>
            <div class="decision-summary-grid">
              <section class="decision-summary-panel">
                <span class="decision-summary-label">市场环境</span>
                <strong class="decision-summary-value">{{ marketEnvironmentHeadline }}</strong>
                <div class="decision-summary-text">{{ marketEnvironmentCopy }}</div>
              </section>
              <section class="decision-summary-panel">
                <span class="decision-summary-label">操作顺序</span>
                <div class="decision-step-inline-list">
                  <button
                    v-for="step in decisionSteps"
                    :key="`decision-inline-${step.key}`"
                    type="button"
                    class="decision-step-inline"
                    :class="`decision-step-inline-${step.tone}`"
                    @click="activateTab(step.tab, { scroll: true })"
                  >
                    <span class="decision-step-inline-rank">{{ step.rank }}</span>
                    <span class="decision-step-inline-copy">
                      <strong>{{ step.title }}</strong>
                      <em>{{ step.countLabel }}</em>
                    </span>
                  </button>
                </div>
                <div class="decision-summary-text">{{ compactRuleSummary }}</div>
              </section>
            </div>
          </article>

          <article class="summary-card summary-card-direction">
            <div class="summary-card-head summary-card-head-direction">
              <div>
                <div class="summary-kicker">今日主线</div>
                <div class="summary-headline">{{ directionHeadline }}</div>
              </div>
              <el-button text type="primary" @click="goToSectors()">
                看板块扫描
              </el-button>
            </div>
            <div class="summary-copy">{{ directionOverviewCopy }}</div>
            <div v-if="primaryDirectionItems.length" class="direction-grid">
              <button
                v-for="(item, index) in primaryDirectionItems"
                :key="`${item.name}-${item.state}`"
                type="button"
                :class="['direction-card', { 'direction-card-lead': index === 0 }]"
                @click="goToSectors(item.name)"
              >
                <div class="direction-card-top">
                  <div class="direction-card-title-group">
                    <strong>{{ item.name }}</strong>
                    <span v-if="item.subtitle" class="direction-card-subtitle">{{ item.subtitle }}</span>
                  </div>
                  <span :class="['direction-card-change', pctClass(item.changePct)]">
                    {{ formatSignedPct(item.changePct) }}
                  </span>
                </div>
                <div class="direction-card-tags">
                  <span class="direction-badge direction-badge-mainline">{{ item.mainlineTag }}</span>
                  <span v-if="item.tier" class="direction-badge direction-badge-tier">{{ item.tier }}类</span>
                  <span
                    v-if="item.actionHint"
                    :class="['direction-badge', directionActionBadgeClass(item.actionHint)]"
                  >
                    {{ item.actionHint }}
                  </span>
                  <span
                    v-if="item.state"
                    :class="['direction-badge', directionStateBadgeClass(item.state)]"
                  >
                    {{ item.state }}
                  </span>
                </div>
                <div class="direction-card-copy">{{ item.reason }}</div>
              </button>
            </div>
          </article>

          <article class="summary-card summary-card-account">
            <div class="summary-kicker">账户执行概览</div>
              <div class="overview-mini-stats overview-mini-stats-compact">
                <div class="overview-mini-stat overview-mini-stat-account">
                  <span class="overview-mini-label">接近执行位</span>
                  <strong class="overview-mini-value">{{ readyStandardExecutionPool.length }}</strong>
                  <span class="overview-mini-tip">优先看这里</span>
                </div>
                <div class="overview-mini-stat overview-mini-stat-market">
                  <span class="overview-mini-label">待触发</span>
                  <strong class="overview-mini-value">{{ waitingStandardExecutionPool.length }}</strong>
                  <span class="overview-mini-tip">跟计划不急追</span>
                </div>
                <div class="overview-mini-stat overview-mini-stat-defense">
                  <span class="overview-mini-label">进攻试错</span>
                  <strong class="overview-mini-value">{{ aggressiveTrialPool.length }}</strong>
                  <span class="overview-mini-tip">仅小仓试错</span>
                </div>
                <div class="overview-mini-stat overview-mini-stat-trend">
                  <span class="overview-mini-label">防守试错</span>
                  <strong class="overview-mini-value">{{ defenseTrialPool.length }}</strong>
                  <span class="overview-mini-tip">防守日极少数</span>
                </div>
                <div class="overview-mini-stat overview-mini-stat-holding">
                <span class="overview-mini-label">观察票</span>
                <strong class="overview-mini-value">{{ marketCount }}</strong>
                <span class="overview-mini-tip">先盯不先做</span>
              </div>
              <div class="overview-mini-stat overview-mini-stat-holding">
                <span class="overview-mini-label">持仓处理</span>
                <strong class="overview-mini-value">{{ holdingCount }}</strong>
                <span class="overview-mini-tip">旧仓优先</span>
              </div>
            </div>
          </article>
        </section>
        <div class="decision-overview">
          <div v-if="reviewBucketFilter" class="focus-context focus-context-review">
            <div class="focus-context-copy">
              当前按复盘来源 <strong>{{ reviewSourceLabel }}</strong> 的 <strong>{{ reviewBucketFilter }}</strong> 结构查看三池。
            </div>
            <div class="focus-context-actions">
              <el-button link type="primary" size="small" @click="clearReviewFilter">清除筛选</el-button>
            </div>
          </div>
          <div v-if="focusSector" class="focus-context">
            <div class="focus-context-copy">
              当前按 <strong>{{ focusSector }}</strong> 方向查看三池，相关标的会优先排到前面。
            </div>
            <div class="focus-context-actions">
              <el-switch v-model="focusOnly" size="small" inline-prompt active-text="只看当前方向" inactive-text="全部" />
              <el-button link type="primary" size="small" @click="clearFocusSector">清除方向</el-button>
            </div>
          </div>
          <section v-if="topFocusItems.length || reviewInsight || focusSector" class="decision-support-shell">
            <div class="section-head section-head-support">
              <div>
                <div class="section-kicker">执行补充</div>
                <div class="section-title">今天先盯谁，以及哪些信号该加权或降权</div>
              </div>
              <div class="section-actions">
                <el-button v-if="focusSector" text @click="router.push('/sectors')">回板块扫描</el-button>
                <el-button text type="primary" @click="router.push({ path: '/buy', query: focusSector ? { focus_sector: focusSector } : {} })">
                  去买点分析
                </el-button>
              </div>
            </div>
            <div class="decision-support-grid">
              <section v-if="topFocusItems.length" class="support-card support-card-focus">
                <div class="support-card-head">
                  <div>
                    <div class="section-kicker">优先名单</div>
                    <div class="section-title">今天先盯这些票</div>
                  </div>
                </div>
                <div class="top-focus-list">
                  <article v-for="item in topFocusItems" :key="`${item.poolKey}-${item.ts_code}`" class="top-focus-item">
                    <span class="top-focus-rank">{{ item.rank }}</span>
                    <div class="top-focus-content">
                      <div class="top-focus-head">
                        <div class="top-focus-main">
                          <strong>{{ item.orderLabel }}{{ item.stock_name }}</strong>
                          <span class="top-focus-meta">{{ item.meta }}</span>
                        </div>
                        <span class="top-focus-pool">{{ focusItemPoolLabel(item) }}</span>
                      </div>
                      <div class="top-focus-trigger">
                        <span class="top-focus-trigger-label">重点</span>
                        <span class="top-focus-trigger-text">{{ item.focus }}</span>
                      </div>
                      <div class="top-focus-actions">
                        <el-button size="small" @click="openFocusAnalysis(item)">
                          {{ item.poolKey === 'holding' ? '卖点详解' : '买点详解' }}
                        </el-button>
                        <el-button text size="small" @click="activateTab(focusItemTab(item), { scroll: true })">
                          定位到{{ focusItemPoolLabel(item) }}
                        </el-button>
                      </div>
                    </div>
                  </article>
                </div>
              </section>

              <section v-if="reviewInsight || focusSector" class="support-card support-card-insight">
                <div class="support-card-head">
                  <div>
                    <div class="section-kicker">辅助判断</div>
                    <div class="section-title">复盘和方向怎么影响今天</div>
                  </div>
                </div>
                <div v-if="focusSector" class="focus-hit-inline">
                  <div class="focus-hit-inline-title">{{ focusSector }} 当前命中</div>
                  <div class="focus-hit-inline-grid">
                    <div class="focus-hit-inline-item">
                      <span>账户池</span>
                      <strong>{{ focusMatches.account }}</strong>
                    </div>
                    <div class="focus-hit-inline-item">
                      <span>观察池</span>
                      <strong>{{ focusMatches.market }}</strong>
                    </div>
                  </div>
                  <div class="focus-hit-summary">{{ focusSummary }}</div>
                </div>
                <div v-if="reviewInsight" class="review-compact">
                  <div class="review-compact-row review-compact-row-do">
                    <span class="review-compact-label">优先看</span>
                    <span class="review-compact-text">{{ reviewInsight.doText }}</span>
                  </div>
                  <div class="review-compact-row review-compact-row-watch">
                    <span class="review-compact-label">先观察</span>
                    <span class="review-compact-text">{{ reviewInsight.watchText }}</span>
                  </div>
                  <div class="review-compact-row review-compact-row-avoid">
                    <span class="review-compact-label">暂时少做</span>
                    <span class="review-compact-text">{{ reviewInsight.avoidText }}</span>
                  </div>
                </div>
              </section>
            </div>
          </section>
        </div>

        <section class="priority-stack">
          <article class="priority-panel priority-panel-account">
            <div class="priority-panel-head">
              <div>
                <div class="section-kicker">模块 A</div>
                <div class="section-title">账户可参与池</div>
                <div class="priority-panel-desc">先看今天通过账户准入的票，再决定要不要回买点页确认执行位。</div>
              </div>
              <el-button text type="primary" @click="activateTab('account', { scroll: true })">查看详细清单</el-button>
            </div>
            <div v-if="!accountPool.length" class="priority-empty">
              {{ accountEmptyReason }}
            </div>
            <div v-else class="execution-lane-stack">
              <div class="execution-dual-grid">
              <section v-if="readyStandardExecutionPool.length" class="execution-lane execution-lane-standard">
                <div class="lane-head">
                  <div class="lane-title-wrap">
                    <div class="lane-title">标准候选 · 接近执行位</div>
                    <div class="lane-caption">已通过账户准入，且现价已靠近执行区，先看这一组</div>
                  </div>
                  <span class="lane-badge">{{ readyStandardExecutionPool.length }} 只</span>
                </div>
                <article v-for="stock in readyStandardExecutionPool" :key="`std-${stock.ts_code}`" class="action-card action-card-standard">
                  <div class="action-card-top">
                    <div>
                      <div class="action-stock">{{ stock.stock_name }}</div>
                      <div class="action-meta">{{ stock.ts_code }} · {{ stock.sector_name || '无方向' }}</div>
                    </div>
                    <span class="action-type-badge action-type-badge-standard">标准候选</span>
                  </div>
                  <div class="action-state-row">
                    <span class="action-state-chip">{{ stock.stock_strength_tag || '强弱待定' }}</span>
                    <span class="action-state-chip">{{ stock.structure_state_tag || '结构待定' }}</span>
                    <span class="action-state-chip">{{ stock.direction_signal_tag || '稳定主线' }}</span>
                    <span v-if="stock.execution_proximity_tag" class="action-state-chip" :class="executionProximityChipClass(stock)">
                      {{ stock.execution_proximity_tag }}
                    </span>
                  </div>
                  <div class="action-judgement">{{ executionJudgementLine(stock) }}</div>
                  <div v-if="stock.execution_proximity_note" class="action-proximity" :class="executionProximityNoteClass(stock)">
                    {{ stock.execution_proximity_note }}
                  </div>
                  <div class="action-grid">
                    <div class="action-block">
                      <span class="action-block-label">执行方式</span>
                      <strong>{{ executionMethodLabel(stock) }}</strong>
                    </div>
                    <div class="action-block">
                      <span class="action-block-label">仓位提示</span>
                      <strong>{{ executionPositionLabel(stock) }}</strong>
                    </div>
                  </div>
                  <div class="action-reason">{{ stock.pool_entry_reason || stock.why_this_pool || stock.stock_comment || '已通过账户准入，仍要回买点页确认。' }}</div>
                  <div class="action-risk">{{ executionRiskLine(stock) }}</div>
                  <div class="stock-inline-actions">
                    <el-button class="buy-analysis-btn" size="small" @click="openBuyAnalysis(stock)">买点详解</el-button>
                  </div>
                </article>
              </section>

              <section v-if="waitingStandardExecutionPool.length" class="execution-lane execution-lane-standard">
                <div class="lane-head">
                  <div class="lane-title-wrap">
                    <div class="lane-title">标准候选 · 待触发</div>
                    <div class="lane-caption">已经过准入，但现价离执行位还有距离，先按计划跟踪</div>
                  </div>
                  <span class="lane-badge">{{ waitingStandardExecutionPool.length }} 只</span>
                </div>
                <article v-for="stock in waitingStandardExecutionPool" :key="`std-wait-${stock.ts_code}`" class="action-card action-card-standard">
                  <div class="action-card-top">
                    <div>
                      <div class="action-stock">{{ stock.stock_name }}</div>
                      <div class="action-meta">{{ stock.ts_code }} · {{ stock.sector_name || '无方向' }}</div>
                    </div>
                    <span class="action-type-badge action-type-badge-standard">标准候选</span>
                  </div>
                  <div class="action-state-row">
                    <span class="action-state-chip">{{ stock.stock_strength_tag || '强弱待定' }}</span>
                    <span class="action-state-chip">{{ stock.structure_state_tag || '结构待定' }}</span>
                    <span class="action-state-chip">{{ stock.direction_signal_tag || '稳定主线' }}</span>
                    <span v-if="stock.execution_proximity_tag" class="action-state-chip" :class="executionProximityChipClass(stock)">
                      {{ stock.execution_proximity_tag }}
                    </span>
                  </div>
                  <div class="action-judgement">{{ executionJudgementLine(stock) }}</div>
                  <div v-if="stock.execution_proximity_note" class="action-proximity" :class="executionProximityNoteClass(stock)">
                    {{ stock.execution_proximity_note }}
                  </div>
                  <div class="action-grid">
                    <div class="action-block">
                      <span class="action-block-label">执行方式</span>
                      <strong>{{ executionMethodLabel(stock) }}</strong>
                    </div>
                    <div class="action-block">
                      <span class="action-block-label">仓位提示</span>
                      <strong>{{ executionPositionLabel(stock) }}</strong>
                    </div>
                  </div>
                  <div class="action-reason">{{ stock.pool_entry_reason || stock.why_this_pool || stock.stock_comment || '已通过账户准入，仍要回买点页确认。' }}</div>
                  <div class="action-risk">{{ executionRiskLine(stock) }}</div>
                  <div class="stock-inline-actions">
                    <el-button class="buy-analysis-btn" size="small" @click="openBuyAnalysis(stock)">买点详解</el-button>
                  </div>
                </article>
              </section>

              <section v-if="aggressiveTrialPool.length" class="execution-lane execution-lane-trial">
                <div class="lane-head">
                  <div class="lane-title-wrap">
                    <div class="lane-title">进攻试错</div>
                    <div class="lane-caption">不是标准舒服位，只适合小仓试错</div>
                  </div>
                  <span class="lane-badge lane-badge-trial">{{ aggressiveTrialPool.length }} 只</span>
                </div>
                <article v-for="stock in aggressiveTrialPool" :key="`trial-${stock.ts_code}`" class="action-card action-card-trial">
                  <div class="action-card-top">
                    <div>
                      <div class="action-stock">{{ stock.stock_name }}</div>
                      <div class="action-meta">{{ stock.ts_code }} · {{ stock.sector_name || '无方向' }}</div>
                    </div>
                    <span class="action-type-badge action-type-badge-trial">进攻试错</span>
                  </div>
                  <div class="action-state-row">
                    <span class="action-state-chip">{{ stock.stock_strength_tag || '强弱待定' }}</span>
                    <span class="action-state-chip">{{ stock.structure_state_tag || '结构待定' }}</span>
                    <span class="action-state-chip">{{ stock.direction_signal_tag || '强化中' }}</span>
                  </div>
                  <div class="action-judgement">{{ executionJudgementLine(stock) }}</div>
                  <div class="action-grid">
                    <div class="action-block">
                      <span class="action-block-label">执行方式</span>
                      <strong>{{ executionMethodLabel(stock) }}</strong>
                    </div>
                    <div class="action-block">
                      <span class="action-block-label">仓位提示</span>
                      <strong>试错仓 / 小仓</strong>
                    </div>
                  </div>
                  <div class="action-reason">{{ stock.pool_entry_reason || stock.why_this_pool || '方向强，但位置不完美，只保留试错资格。' }}</div>
                  <div class="action-risk">{{ trialRiskLine(stock) }}</div>
                  <div class="stock-inline-actions">
                    <el-button class="buy-analysis-btn" size="small" @click="openBuyAnalysis(stock)">买点详解</el-button>
                  </div>
                </article>
              </section>

              <section v-if="defenseTrialPool.length" class="execution-lane execution-lane-defense">
                <div class="lane-head">
                  <div class="lane-title-wrap">
                    <div class="lane-title">防守试错</div>
                    <div class="lane-caption">防守日仅保留极少数最强核心股轻仓试错</div>
                  </div>
                  <span class="lane-badge lane-badge-defense">{{ defenseTrialPool.length }} 只</span>
                </div>
                <article v-for="stock in defenseTrialPool" :key="`def-${stock.ts_code}`" class="action-card action-card-defense">
                  <div class="action-card-top">
                    <div>
                      <div class="action-stock">{{ stock.stock_name }}</div>
                      <div class="action-meta">{{ stock.ts_code }} · {{ stock.sector_name || '无方向' }}</div>
                    </div>
                    <span class="action-type-badge action-type-badge-defense">防守试错</span>
                  </div>
                  <div class="action-state-row">
                    <span class="action-state-chip">{{ stock.stock_strength_tag || '强弱待定' }}</span>
                    <span class="action-state-chip">{{ stock.structure_state_tag || '结构待定' }}</span>
                    <span class="action-state-chip">{{ stock.direction_signal_tag || '防守保留' }}</span>
                  </div>
                  <div class="action-judgement">{{ executionJudgementLine(stock) }}</div>
                  <div class="action-grid">
                    <div class="action-block">
                      <span class="action-block-label">执行方式</span>
                      <strong>{{ executionMethodLabel(stock) }}</strong>
                    </div>
                    <div class="action-block">
                      <span class="action-block-label">仓位提示</span>
                      <strong>{{ executionPositionLabel(stock) }}</strong>
                    </div>
                  </div>
                  <div class="action-reason">{{ stock.pool_entry_reason || stock.why_this_pool || '防守环境下只保留极少数轻仓试错资格。' }}</div>
                  <div class="action-risk">{{ trialRiskLine(stock) }}</div>
                  <div class="stock-inline-actions">
                    <el-button class="buy-analysis-btn" size="small" @click="openBuyAnalysis(stock)">买点详解</el-button>
                  </div>
                </article>
              </section>
              </div>
              <div v-if="executionEmptyStates.length" class="execution-empty-strip">
                <article
                  v-for="state in executionEmptyStates"
                  :key="state.key"
                  class="execution-empty-card"
                  :class="`execution-empty-card-${state.tone}`"
                >
                  <div class="execution-empty-head">
                    <div>
                      <div class="execution-empty-title">{{ state.title }}</div>
                      <div class="execution-empty-caption">{{ state.caption }}</div>
                    </div>
                    <span class="execution-empty-badge">0 只</span>
                  </div>
                  <div class="execution-empty-reason">{{ state.reason }}</div>
                </article>
              </div>
            </div>
          </article>

          <article class="priority-panel">
            <div class="priority-panel-head">
              <div>
                <div class="section-kicker">模块 B</div>
                <div class="section-title">市场最强观察池</div>
                <div class="priority-panel-desc">先看市场在围绕哪些方向交易，再决定哪些票值得继续盯。</div>
                <div v-if="isRadarMode" class="priority-panel-meta">
                  前排代表 {{ marketPool.length }} 只
                  <span v-if="marketWatchCandidateCount"> / 候选全集 {{ marketWatchCandidateCount }} 只</span>
                </div>
              </div>
              <el-button text type="primary" @click="activateTab('market', { scroll: true })">查看详细清单</el-button>
            </div>
            <div v-if="!marketDirectionGroups.length" class="priority-empty">当前没有需要重点盯的市场最强方向。</div>
            <div v-else class="watch-group-grid">
              <section v-for="group in marketDirectionGroups" :key="group.name" class="watch-group-card">
                <div class="watch-group-head">
                  <div>
                    <div class="watch-group-title">{{ group.name }}</div>
                    <div class="watch-group-state">{{ group.state }}</div>
                  </div>
                  <span class="watch-group-count">{{ group.items.length }} 只</span>
                </div>
                <div class="watch-group-insight">{{ group.summary }}</div>
                <div class="watch-group-list">
                  <div v-for="stock in group.items" :key="stock.ts_code" class="watch-group-item">
                    <strong>{{ stock.stock_name }}</strong>
                    <span>{{ watchRoleLabel(stock) }}</span>
                    <em>{{ watchKeyLine(stock) }}</em>
                    <div class="stock-inline-actions">
                      <el-button class="buy-analysis-btn" size="small" @click="openBuyAnalysis(stock)">买点详解</el-button>
                    </div>
                  </div>
                </div>
              </section>
            </div>
            <div v-if="showRadarWatchExpansion" class="watch-candidate-panel">
              <div class="watch-candidate-head">
                <div>
                  <div class="watch-candidate-title">候选补充</div>
                  <div class="watch-candidate-desc">这些票还在观察候选全集里，适合扩展盯盘范围，但不替代前排代表票。</div>
                </div>
                <el-button text type="primary" @click="watchCandidatesExpanded = !watchCandidatesExpanded">
                  {{ watchCandidatesExpanded ? '收起候选' : `展开候选（还有 ${marketRadarExtraCandidates.length} 只）` }}
                </el-button>
              </div>
              <div class="watch-candidate-grid">
                <article v-for="stock in marketRadarExtraVisible" :key="stock.ts_code" class="watch-candidate-card">
                  <div class="watch-candidate-card-top">
                    <div>
                      <strong>{{ stock.stock_name }}</strong>
                      <span>{{ stock.ts_code }}</span>
                    </div>
                    <em :class="pctClass(stock.change_pct)">{{ formatSignedPct(stock.change_pct) }}</em>
                  </div>
                  <div class="watch-candidate-card-meta">{{ stock.sector_name || '无板块信息' }} / {{ stock.candidate_source_tag || '候选补充' }}</div>
                  <div class="watch-candidate-card-copy">{{ watchKeyLine(stock) }}</div>
                  <div class="stock-inline-actions">
                    <el-button class="buy-analysis-btn" size="small" @click="openBuyAnalysis(stock)">买点详解</el-button>
                  </div>
                </article>
              </div>
            </div>
          </article>

        </section>

        <el-card ref="detailCardRef" class="detail-card">
          <template #header>
            <div class="priority-panel-head">
              <div>
                <div class="section-kicker">详细清单</div>
                <div class="section-title">展开看每只票的完整判断和条件</div>
              </div>
            </div>
          </template>

        <el-tabs v-model="activeTab">
          <el-tab-pane name="market">
            <template #label>
              <span>市场最强观察池 <em class="tab-count">{{ marketPool.length }}</em></span>
            </template>
            <el-empty v-if="!marketCount" :description="emptyPoolText('market')" />
            <div v-else class="signal-grid">
              <article
                v-for="stock in marketPool"
                :key="stock.ts_code"
                :class="['signal-card', 'signal-card-market', { 'signal-card-focused': matchesFocusSector(stock) }]"
              >
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ stock.stock_name }}</div>
                    <div class="signal-code">{{ stock.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" type="primary">{{ stock.candidate_bucket_tag || '观察补充' }}</el-tag>
                    <el-tag v-if="stock.direction_signal_tag" size="small" type="warning">
                      {{ stock.direction_signal_tag }}
                    </el-tag>
                    <el-tag v-if="stock.representative_role_tag" size="small" type="danger">
                      {{ stock.representative_role_tag }}
                    </el-tag>
                    <el-tooltip v-if="stock.review_bias_label" :content="stock.review_bias_reason || stock.review_bias_label" placement="top">
                      <el-tag size="small" :type="reviewBiasTagType(stock.review_bias_label)">
                        {{ stock.review_bias_label }}
                      </el-tag>
                    </el-tooltip>
                    <el-tag size="small" type="info">{{ stock.stock_core_tag }}</el-tag>
                  </div>
                </div>

                <div class="signal-meta">
                  <span>{{ stock.sector_name || '无板块信息' }}</span>
                  <span>{{ stock.candidate_source_tag || '无来源标记' }}</span>
                </div>
                <div v-if="stock.representative_role_tag" class="sample-role-line">
                  {{ representativeRoleLine(stock) }}
                </div>

                <div class="signal-intent signal-intent-market">
                  {{ marketActionLine(stock) }}
                </div>
                <div class="hard-filter-strip" :class="{ 'hard-filter-warn': (stock.hard_filter_failed_count || 0) > 0 }">
                  {{ hardFilterLine(stock) }}
                </div>

                <div class="quote-strip">
                  <div class="quote-main">
                    <span class="quote-label">最新价</span>
                    <strong class="quote-price">{{ formatPrice(stock.close) }}</strong>
                    <span :class="['quote-change', pctClass(stock.change_pct)]">
                      {{ formatSignedPct(stock.change_pct) }}
                    </span>
                    <span class="quote-source" :class="{ 'quote-source-live': isRealtimeSource(stock.data_source) }">
                      {{ quoteMetaLine(stock.data_source, stock.quote_time, poolsData.resolved_trade_date || displayDate) }}
                    </span>
                  </div>
                  <div class="quote-side">
                    <span class="quote-pair">
                      市场分
                      <strong>{{ formatScore(stock.market_strength_score) }}</strong>
                    </span>
                    <span class="quote-pair">
                      执行分
                      <strong>{{ formatScore(stock.execution_opportunity_score) }}</strong>
                    </span>
                    <span class="quote-pair">
                      量比
                      <strong>{{ formatRatio(stock.vol_ratio) }}</strong>
                    </span>
                  </div>
                </div>

                <div class="price-strip">
                  <div class="metric-card">
                    <span class="metric-label">强弱</span>
                    <strong class="metric-value">{{ stock.stock_strength_tag }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">连续性</span>
                    <strong class="metric-value">{{ stock.stock_continuity_tag }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">交易性</span>
                    <strong class="metric-value">{{ stock.stock_tradeability_tag }}</strong>
                  </div>
                </div>

                <div class="profile-section">
                  <div class="section-kicker">五项画像</div>
                  <div class="profile-tags">
                    <span v-for="tag in stockProfileTags(stock)" :key="tag" class="profile-tag">
                      {{ tag }}
                    </span>
                  </div>
                </div>

                <div class="decision-section">
                  <div class="decision-card">
                    <div class="decision-title">进池原因</div>
                    <div class="decision-copy">{{ stock.why_this_pool || stock.pool_decision_summary || stock.stock_comment || '因为它能代表当天最强偏好。' }}</div>
                  </div>
                  <div class="decision-card">
                    <div class="decision-title">暂不执行原因</div>
                    <div class="decision-copy">{{ watchOnlyReasonLine(stock) }}</div>
                  </div>
                </div>
                <div v-if="stock.miss_risk_note" class="sample-role-line">
                  机会提醒：{{ stock.miss_risk_note }}
                </div>

                <div class="condition-section">
                  <div class="section-kicker">观察清单</div>
                  <div class="condition-panel-grid condition-panel-grid-watch">
                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">先看</div>
                          <div class="panel-subtitle">这只票为什么值得盯</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.stock_comment || '先看板块和量能是否继续强化。' }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-invalid">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">证伪</div>
                          <div class="panel-subtitle">出现这个信号就降级观察</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.llm_risk_note || stock.stock_falsification_cond || '结构破坏或量能转弱时不再优先观察。' }}</div>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ marketFooterLine(stock) }}</span>
                  <div class="footer-actions">
                    <span class="footer-flag">只观察，不直接执行</span>
                    <el-button class="buy-analysis-btn" size="small" @click="openBuyAnalysis(stock)">买点详解</el-button>
                    <el-button type="primary" link size="small" @click="openCheckup(stock, '观察型')">全面体检</el-button>
                  </div>
                </div>
              </article>
            </div>
            <section v-if="showRadarWatchExpansion" class="watch-candidate-detail-panel">
              <div class="watch-candidate-head">
                <div>
                  <div class="watch-candidate-title">观察候选展开区</div>
                  <div class="watch-candidate-desc">代表票之外的候选补充，适合扩展盯盘范围，不直接等同于前排优先级。</div>
                </div>
                <div class="watch-candidate-summary">
                  候选全集 {{ marketWatchCandidateCount }} 只 / 当前可见代表票 {{ marketPool.length }} 只
                </div>
              </div>
              <div class="signal-grid signal-grid-candidate">
                <article
                  v-for="stock in marketRadarExtraVisible"
                  :key="`extra-${stock.ts_code}`"
                  :class="['signal-card', 'signal-card-market', 'signal-card-candidate', { 'signal-card-focused': matchesFocusSector(stock) }]"
                >
                  <div class="signal-card-header">
                    <div>
                      <div class="signal-stock">{{ stock.stock_name }}</div>
                      <div class="signal-code">{{ stock.ts_code }}</div>
                    </div>
                    <div class="signal-badges">
                      <el-tag size="small" type="info">候选补充</el-tag>
                      <el-tag v-if="stock.direction_signal_tag" size="small" type="warning">
                        {{ stock.direction_signal_tag }}
                      </el-tag>
                      <el-tag v-if="stock.representative_role_tag" size="small" type="danger">
                        {{ stock.representative_role_tag }}
                      </el-tag>
                    </div>
                  </div>
                  <div class="signal-meta">
                    <span>{{ stock.sector_name || '无板块信息' }}</span>
                    <span>{{ stock.candidate_source_tag || '候选补充' }}</span>
                  </div>
                  <div class="signal-intent signal-intent-market">
                    {{ marketActionLine(stock) }}
                  </div>
                  <div class="decision-section">
                    <div class="decision-card">
                      <div class="decision-title">观察理由</div>
                      <div class="decision-copy">{{ watchKeyLine(stock) }}</div>
                    </div>
                    <div class="decision-card">
                      <div class="decision-title">暂不排前</div>
                      <div class="decision-copy">{{ watchOnlyReasonLine(stock) }}</div>
                    </div>
                  </div>
                  <div class="signal-footer">
                    <span>先扩展盯盘，不直接上升为前排代表票。</span>
                    <div class="footer-actions">
                      <el-button class="buy-analysis-btn" size="small" @click="openBuyAnalysis(stock)">买点详解</el-button>
                    </div>
                  </div>
                </article>
              </div>
              <div v-if="marketRadarHiddenCount > 0" class="watch-candidate-more">
                <el-button text type="primary" @click="watchCandidatesExpanded = true">
                  还有 {{ marketRadarHiddenCount }} 只候选未展开
                </el-button>
              </div>
            </section>
          </el-tab-pane>

          <el-tab-pane name="account">
            <template #label>
              <span>账户可参与池 <em class="tab-count">{{ accountPool.length }}</em></span>
            </template>
            <el-empty
              v-if="!accountCount"
              :description="emptyPoolText('account')"
            />
            <div v-else class="account-group-stack">
              <section v-for="group in accountPoolGroups" :key="group.key" class="account-group">
                <div class="account-group-head">
                  <div>
                    <div class="account-group-title">{{ group.title }}</div>
                    <div class="account-group-desc">{{ group.desc }}</div>
                  </div>
                  <div class="account-group-meta">{{ group.items.length }} 只</div>
                </div>

                <div class="signal-grid">
                  <article
                    v-for="stock in group.items"
                    :key="stock.ts_code"
                    :class="['signal-card', 'signal-card-account', { 'signal-card-focused': matchesFocusSector(stock) }]"
                  >
                    <div class="signal-card-header">
                      <div>
                        <div class="signal-stock">{{ stock.stock_name }}</div>
                        <div class="signal-code">{{ stock.ts_code }}</div>
                      </div>
                      <div class="signal-badges">
                        <el-tag size="small" type="success">{{ stock.candidate_bucket_tag || '可参与' }}</el-tag>
                        <el-tag v-if="stock.direction_signal_tag" size="small" type="warning">
                          {{ stock.direction_signal_tag }}
                        </el-tag>
                        <el-tag v-if="stock.representative_role_tag" size="small" type="danger">
                          {{ stock.representative_role_tag }}
                        </el-tag>
                        <el-tooltip v-if="stock.review_bias_label" :content="stock.review_bias_reason || stock.review_bias_label" placement="top">
                          <el-tag size="small" :type="reviewBiasTagType(stock.review_bias_label)">
                            {{ stock.review_bias_label }}
                          </el-tag>
                        </el-tooltip>
                        <el-tag size="small" :type="accountEntryTagType(stock)">{{ accountEntryTag(stock) }}</el-tag>
                        <el-tag v-if="stock.execution_proximity_tag" size="small" :type="executionProximityTagType(stock)">
                          {{ stock.execution_proximity_tag }}
                        </el-tag>
                      </div>
                    </div>

                    <div class="signal-meta">
                      <span>{{ stock.sector_name || '无板块信息' }}</span>
                      <span>{{ stock.candidate_source_tag || '无来源标记' }}</span>
                    </div>
                    <div v-if="stock.representative_role_tag" class="sample-role-line">
                      {{ representativeRoleLine(stock) }}
                    </div>

                    <div class="signal-intent signal-intent-account">
                      {{ accountActionLine(stock) }}
                    </div>
                    <div v-if="stock.execution_proximity_note" class="execution-proximity-strip" :class="executionProximityStripClass(stock)">
                      {{ stock.execution_proximity_note }}
                    </div>
                    <div class="hard-filter-strip" :class="{ 'hard-filter-warn': (stock.hard_filter_failed_count || 0) > 0 }">
                      {{ hardFilterLine(stock) }}
                    </div>

                    <div class="quote-strip">
                      <div class="quote-main">
                        <span class="quote-label">最新价</span>
                        <strong class="quote-price">{{ formatPrice(stock.close) }}</strong>
                        <span :class="['quote-change', pctClass(stock.change_pct)]">
                          {{ formatSignedPct(stock.change_pct) }}
                        </span>
                        <span class="quote-source" :class="{ 'quote-source-live': isRealtimeSource(stock.data_source) }">
                          {{ quoteMetaLine(stock.data_source, stock.quote_time, poolsData.resolved_trade_date || displayDate) }}
                        </span>
                      </div>
                      <div class="quote-side">
                        <span class="quote-pair">
                          市场分
                          <strong>{{ formatScore(stock.market_strength_score) }}</strong>
                        </span>
                        <span class="quote-pair">
                          执行分
                          <strong>{{ formatScore(stock.execution_opportunity_score) }}</strong>
                        </span>
                        <span class="quote-pair">
                          账户分
                          <strong>{{ formatScore(stock.account_entry_score) }}</strong>
                        </span>
                        <span v-if="stock.execution_reference_gap_pct !== null && stock.execution_reference_gap_pct !== undefined" class="quote-pair">
                          距执行位
                          <strong :class="executionGapClass(stock)">{{ formatSignedPct(stock.execution_reference_gap_pct) }}</strong>
                        </span>
                      </div>
                    </div>

                    <div class="price-strip">
                      <div class="metric-card">
                        <span class="metric-label">强弱</span>
                        <strong class="metric-value">{{ stock.stock_strength_tag }}</strong>
                      </div>
                      <div class="metric-card">
                        <span class="metric-label">连续性</span>
                        <strong class="metric-value">{{ stock.stock_continuity_tag }}</strong>
                      </div>
                      <div class="metric-card">
                        <span class="metric-label">交易性</span>
                        <strong class="metric-value">{{ stock.stock_tradeability_tag }}</strong>
                      </div>
                    </div>

                    <div class="profile-section">
                      <div class="section-kicker">五项画像</div>
                      <div class="profile-tags">
                        <span v-for="tag in stockProfileTags(stock)" :key="tag" class="profile-tag">
                          {{ tag }}
                        </span>
                      </div>
                    </div>

                    <div class="decision-section">
                      <div class="decision-card">
                        <div class="decision-title">进池原因</div>
                        <div class="decision-copy">{{ stock.why_this_pool || stock.pool_entry_reason || stock.stock_comment || '满足账户可执行条件。' }}</div>
                      </div>
                      <div class="decision-card">
                        <div class="decision-title">未进其他池</div>
                        <div class="decision-copy">{{ notOtherPoolsLine(stock) }}</div>
                      </div>
                    </div>

                    <div class="condition-section">
                      <div class="section-kicker">执行清单</div>
                      <div class="condition-panel-grid condition-panel-grid-watch">
                        <section class="condition-panel condition-panel-trigger">
                          <div class="panel-head">
                            <span class="panel-step">1</span>
                            <div>
                              <div class="panel-title">为什么能进池</div>
                              <div class="panel-subtitle">先看账户和结构是否匹配</div>
                            </div>
                          </div>
                          <div class="panel-body">
                            <div class="condition-title">{{ stock.pool_entry_reason || stock.stock_comment || '满足常规开仓条件。' }}</div>
                          </div>
                        </section>

                        <section class="condition-panel condition-panel-confirm">
                          <div class="panel-head">
                            <span class="panel-step">2</span>
                            <div>
                          <div class="panel-title">仓位提示</div>
                          <div class="panel-subtitle">执行前先按提示控制仓位</div>
                        </div>
                      </div>
                      <div class="panel-body">
                            <div class="condition-title">{{ stock.execution_proximity_note || stock.llm_risk_note || stock.position_hint || '按计划仓位执行，不要超配。' }}</div>
                      </div>
                    </section>
                      </div>
                    </div>

                    <div class="signal-footer">
                      <span>{{ stock.stock_comment || '可参与不代表立刻追价，仍要等买点页确认。' }}</span>
                      <div class="footer-actions">
                        <span class="footer-flag">{{ accountFooterFlag(stock) }}</span>
                        <el-button class="buy-analysis-btn" size="small" @click="openBuyAnalysis(stock)">买点详解</el-button>
                        <el-button type="primary" link size="small" @click="openCheckup(stock, '交易型')">全面体检</el-button>
                      </div>
                    </div>
                  </article>
                </div>
              </section>
            </div>
          </el-tab-pane>

          <el-tab-pane name="holding">
            <template #label>
              <span>持仓处理池 <em class="tab-count">{{ holdingPool.length }}</em></span>
            </template>
            <el-empty v-if="!holdingCount" description="暂无持仓或持仓未进入当日行情" />
            <div v-else class="signal-grid">
              <article
                v-for="stock in holdingPool"
                :key="stock.ts_code"
                class="signal-card signal-card-holding"
              >
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ stock.stock_name }}</div>
                    <div class="signal-code">{{ stock.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" :type="sellTagType(stock.sell_signal_tag)">{{ stock.sell_signal_tag || '观察' }}</el-tag>
                    <el-tag size="small" :type="priorityTagType(stock.sell_priority)">{{ `${stock.sell_priority || '低'}优先` }}</el-tag>
                  </div>
                </div>

                <div class="signal-meta">
                  <span>{{ stock.sector_name || '无板块信息' }}</span>
                  <span>{{ stock.holding_reason || '无买入理由记录' }}</span>
                </div>

                <div class="signal-intent signal-intent-holding">
                  {{ holdingActionLine(stock) }}
                </div>

                <div class="quote-strip">
                  <div class="quote-main">
                    <span class="quote-label">现价 / 成本</span>
                    <strong class="quote-price">{{ formatPrice(stock.close) }} / {{ formatPrice(stock.cost_price) }}</strong>
                    <span :class="['quote-change', pctClass(stock.pnl_pct)]">
                      {{ formatSignedPct(stock.pnl_pct) }}
                    </span>
                    <span class="quote-source" :class="{ 'quote-source-live': isRealtimeSource(stock.data_source) }">
                      {{ quoteMetaLine(stock.data_source, stock.quote_time, displayDate) }}
                    </span>
                  </div>
                  <div class="quote-side">
                    <span class="quote-pair">
                      持仓
                      <strong>{{ formatQty(stock.holding_qty) }}</strong>
                    </span>
                    <span class="quote-pair">
                      市值
                      <strong>{{ formatMoney(stock.holding_market_value) }}</strong>
                    </span>
                  </div>
                </div>

                <div class="price-strip">
                  <div class="metric-card">
                    <span class="metric-label">持有天数</span>
                    <strong class="metric-value">{{ formatDays(stock.holding_days) }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">可卖状态</span>
                    <strong class="metric-value">{{ stock.can_sell_today ? '今日可卖' : 'T+1锁定' }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">交易性</span>
                    <strong class="metric-value">{{ stock.stock_tradeability_tag }}</strong>
                  </div>
                </div>

                <div class="condition-section">
                  <div class="section-kicker">处理清单</div>
                  <div class="condition-panel-grid">
                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">动作</div>
                          <div class="panel-subtitle">先明确该持有、减仓还是卖出</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.sell_reason || stock.sell_comment || '当前没有明确动作建议。' }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-confirm">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">动手条件</div>
                          <div class="panel-subtitle">到了这个条件再执行动作</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.sell_trigger_cond || '继续跟踪盘中强弱和板块共振。' }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-invalid">
                      <div class="panel-head">
                        <span class="panel-step">3</span>
                        <div>
                          <div class="panel-title">买入前提</div>
                          <div class="panel-subtitle">回头对照原来的持仓逻辑是否还成立</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.llm_risk_note || stock.stock_falsification_cond || '若买入逻辑失效，就不要继续硬扛。' }}</div>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ stock.llm_risk_note || stock.sell_comment || stock.stock_comment || '-' }}</span>
                  <div class="footer-actions">
                    <span class="footer-flag">{{ holdingFooterFlag(stock) }}</span>
                    <el-button class="sell-analysis-btn" size="small" @click="openSellAnalysis(stock)">卖点详解</el-button>
                    <el-button type="primary" link size="small" @click="openCheckup(stock, '持仓型')">全面体检</el-button>
                  </div>
                </div>
              </article>
            </div>
          </el-tab-pane>
        </el-tabs>
        </el-card>
      </template>
    </el-card>
    <StockCheckupDrawer
      v-model="checkupVisible"
      :ts-code="checkupStock.tsCode"
      :stock-name="checkupStock.stockName"
      :default-target="checkupStock.defaultTarget"
      :trade-date="displayDate"
    />
    <BuyAnalysisDrawer
      v-model="buyAnalysisVisible"
      :ts-code="buyAnalysisStock.tsCode"
      :stock-name="buyAnalysisStock.stockName"
      :trade-date="buyAnalysisTradeDate"
      :source-pool-tag="buyAnalysisStock.sourcePoolTag"
      :current-price="buyAnalysisStock.currentPrice"
      :current-change-pct="buyAnalysisStock.currentChangePct"
    />
    <SellAnalysisDrawer
      v-model="sellAnalysisVisible"
      :ts-code="sellAnalysisStock.tsCode"
      :stock-name="sellAnalysisStock.stockName"
      :trade-date="displayDate"
      :current-price="sellAnalysisStock.currentPrice"
      :current-pnl-pct="sellAnalysisStock.currentPnlPct"
    />
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { stockApi, decisionApi } from '../api'
import { ElMessage } from 'element-plus'
import StockCheckupDrawer from '../components/StockCheckupDrawer.vue'
import BuyAnalysisDrawer from '../components/BuyAnalysisDrawer.vue'
import SellAnalysisDrawer from '../components/SellAnalysisDrawer.vue'
import DataFreshnessBar from '../components/DataFreshnessBar.vue'
import { formatLocalDateTime, formatLocalTime } from '../utils/datetime'

const loading = ref(false)
const activeTab = ref('holding')
const displayDate = ref('')
const detailCardRef = ref(null)
const poolsData = ref({
  market_watch_pool: [],
  market_watch_candidates: [],
  market_watch_candidate_count: 0,
  account_executable_pool: [],
  holding_process_pool: [],
  resolved_trade_date: '',
  sector_scan_trade_date: '',
  sector_scan_resolved_trade_date: '',
  market_env: null,
  mainline_sectors: [],
  sub_mainline_sectors: [],
  global_trade_gate: null,
  mode: 'stable',
  is_realtime: false,
  radar_generated_at: '',
})
const checkupVisible = ref(false)
const checkupStock = ref({ tsCode: '', stockName: '', defaultTarget: '观察型' })
const buyAnalysisVisible = ref(false)
const buyAnalysisStock = ref({ tsCode: '', stockName: '', sourcePoolTag: '', currentPrice: null, currentChangePct: null })
const sellAnalysisVisible = ref(false)
const sellAnalysisStock = ref({ tsCode: '', stockName: '', currentPrice: null, currentPnlPct: null })
const reviewStatsData = ref(null)
const loadError = ref('')
const POOLS_TIMEOUT = 90000
const REVIEW_STATS_TIMEOUT = 90000
const POOLS_REFRESH_POLL_MS = 2500
const RADAR_AUTO_REFRESH_MS = 30000
const route = useRoute()
const router = useRouter()
const focusOnly = ref(false)
const poolMode = ref(String(route.query.mode || 'stable').trim() === 'radar' ? 'radar' : 'stable')
let refreshPollTimer = null
let radarAutoRefreshTimer = null
const waitingForRefreshResult = ref(false)
const watchCandidatesExpanded = ref(false)

const focusSector = computed(() => String(route.query.focus_sector || '').trim())
const reviewBucketFilter = computed(() => String(route.query.review_bucket || '').trim())
const reviewSourceFilter = computed(() => String(route.query.review_source || '').trim())
const isRadarMode = computed(() => poolMode.value === 'radar')
const poolsFreshnessItems = computed(() => [
  {
    label: '模式',
    value: isRadarMode.value ? '实时雷达' : '稳定模式',
    tone: isRadarMode.value ? 'strong' : 'muted',
  },
  {
    label: '请求日',
    value: displayDate.value || '-',
    tone: 'strong',
  },
  {
    label: '候选口径',
    value: poolsData.value.stale_snapshot && poolsData.value.refresh_in_progress && poolsData.value.resolved_trade_date
      ? `旧快照 ${poolsData.value.resolved_trade_date}（后台刷新中）`
      : (poolsData.value.candidate_data_status && poolsData.value.candidate_data_status !== 'ok'
          ? '当日候选异常'
          : (poolsData.value.resolved_trade_date
              ? (poolsData.value.resolved_trade_date === displayDate.value
                  ? '当日候选'
                  : `回退到 ${poolsData.value.resolved_trade_date}`)
              : '待加载')),
    tone: (poolsData.value.stale_snapshot && poolsData.value.refresh_in_progress)
      || (poolsData.value.candidate_data_status && poolsData.value.candidate_data_status !== 'ok')
      || poolsData.value.resolved_trade_date !== displayDate.value
      ? 'warn'
      : 'strong',
  },
  {
    label: '板块口径',
    value: poolsData.value.stale_snapshot && poolsData.value.refresh_in_progress && poolsData.value.sector_scan_resolved_trade_date
      ? `旧快照 ${poolsData.value.sector_scan_resolved_trade_date}（后台刷新中）`
      : (poolsData.value.sector_scan_resolved_trade_date
          ? (poolsData.value.sector_scan_resolved_trade_date === displayDate.value
              ? '当日扫描'
              : `回退到 ${poolsData.value.sector_scan_resolved_trade_date}`)
          : '待加载'),
    tone: ((poolsData.value.stale_snapshot && poolsData.value.refresh_in_progress)
      || poolsData.value.sector_scan_resolved_trade_date !== displayDate.value)
      ? 'warn'
      : 'strong',
  },
])
const poolsFreshnessNote = computed(() => (
  isRadarMode.value
    ? '实时雷达适合盯盘，但看到异动后仍要回买点或卖点页确认触发条件。'
    : (
        poolsData.value.snapshot_status_message
        || poolsData.value.candidate_data_message
        || '稳定模式优先看最近稳定结论，更适合盘前和盘后判断。'
      )
))
const buyAnalysisTradeDate = computed(() => (
  isRadarMode.value
    ? displayDate.value
    : (poolsData.value.resolved_trade_date || displayDate.value)
))

const marketCount = computed(() => poolsData.value.market_watch_pool?.length || 0)
const marketWatchCandidateCount = computed(() => (
  Number(poolsData.value.market_watch_candidate_count || 0) || (poolsData.value.market_watch_candidates?.length || 0)
))
const accountCount = computed(() => poolsData.value.account_executable_pool?.length || 0)
const holdingCount = computed(() => poolsData.value.holding_process_pool?.length || 0)
const globalTradeGate = computed(() => poolsData.value.global_trade_gate || {
  status: '允许试错',
  allow_new_positions: true,
  dominant_reason: '等待规则结果',
  reasons: [],
  account_pool_limit: 3,
})
const refreshButtonLoading = computed(() => loading.value || Boolean(poolsData.value.refresh_in_progress))
const todayMarketEnv = computed(() => poolsData.value.market_env || {
  market_env_tag: '中性',
  market_env_profile: '',
  breakout_allowed: false,
  risk_level: '中',
  market_comment: '',
  market_headline: '',
  market_subheadline: '',
  trading_tempo_label: '',
  dominant_factor_label: '',
})
const marketEnvironmentTagLabel = computed(() => (
  todayMarketEnv.value.market_env_profile || todayMarketEnv.value.market_env_tag || '中性'
))
const radarModeBanner = computed(() => {
  const generatedAt = poolsData.value.radar_generated_at
    ? `最新生成于 ${formatLocalDateTime(poolsData.value.radar_generated_at, { assumeUtc: true })}`
    : '盘中结果会变化'
  return `${generatedAt}。观察池更偏实时雷达，账户池仍应以纪律和买点确认优先；页面每 30 秒自动更新一次。`
})

const stopRefreshPolling = () => {
  if (!refreshPollTimer) return
  window.clearTimeout(refreshPollTimer)
  refreshPollTimer = null
}

const stopRadarAutoRefresh = () => {
  if (!radarAutoRefreshTimer) return
  window.clearTimeout(radarAutoRefreshTimer)
  radarAutoRefreshTimer = null
}

const scheduleRefreshPolling = () => {
  if (refreshPollTimer) return
  refreshPollTimer = window.setTimeout(async () => {
    refreshPollTimer = null
    await loadData({ polling: true })
  }, POOLS_REFRESH_POLL_MS)
}

const scheduleRadarAutoRefresh = () => {
  if (!isRadarMode.value || document.hidden) return
  if (radarAutoRefreshTimer) return
  radarAutoRefreshTimer = window.setTimeout(async () => {
    radarAutoRefreshTimer = null
    if (!isRadarMode.value || document.hidden) return
    await loadData({ polling: true, radarAuto: true })
  }, RADAR_AUTO_REFRESH_MS)
}

const matchesFocusSector = (stock) => {
  if (!focusSector.value) return false
  return String(stock.sector_name || '').includes(focusSector.value)
}

const sortByFocusSector = (rows = []) => {
  const sorted = [...rows].sort((a, b) => Number(matchesFocusSector(b)) - Number(matchesFocusSector(a)))
  if (focusSector.value && focusOnly.value) {
    return sorted.filter((item) => matchesFocusSector(item))
  }
  return sorted
}

const executionProximityRank = (stock) => {
  const tag = String(stock?.execution_proximity_tag || '')
  if (tag === '接近执行位') return 0
  if (tag === '已过确认位') return 1
  if (tag === '待突破') return 2
  if (tag === '待回踩' || tag === '待低吸') return 3
  if (tag === '待深回踩') return 4
  return 5
}

const compareAccountExecutionPriority = (a, b) => {
  const modeDiff = (
    (accountEntryMode(a) === 'standard' ? 0 : accountEntryMode(a) === 'aggressive_trial' ? 1 : 2) -
    (accountEntryMode(b) === 'standard' ? 0 : accountEntryMode(b) === 'aggressive_trial' ? 1 : 2)
  )
  if (modeDiff !== 0) return modeDiff

  const proximityDiff = executionProximityRank(a) - executionProximityRank(b)
  if (proximityDiff !== 0) return proximityDiff

  const accountScoreDiff = Number(b.account_entry_score || 0) - Number(a.account_entry_score || 0)
  if (accountScoreDiff !== 0) return accountScoreDiff

  const executionScoreDiff = Number(b.execution_opportunity_score || 0) - Number(a.execution_opportunity_score || 0)
  if (executionScoreDiff !== 0) return executionScoreDiff

  return Number(b.market_strength_score || 0) - Number(a.market_strength_score || 0)
}

const matchesReviewBucket = (stock) => {
  if (!reviewBucketFilter.value) return true
  return String(stock.candidate_bucket_tag || '').trim() === reviewBucketFilter.value
}

const applyPoolFilters = (rows = []) => sortByFocusSector(rows).filter(matchesReviewBucket)

const marketPool = computed(() => applyPoolFilters(poolsData.value.market_watch_pool || []))
const marketWatchCandidates = computed(() => applyPoolFilters(poolsData.value.market_watch_candidates || []))
const marketVisibleCodeSet = computed(() => new Set((marketPool.value || []).map((stock) => String(stock.ts_code || '').trim())))
const marketRadarExtraCandidates = computed(() => (
  marketWatchCandidates.value.filter((stock) => !marketVisibleCodeSet.value.has(String(stock.ts_code || '').trim()))
))
const marketRadarExtraVisible = computed(() => (
  watchCandidatesExpanded.value ? marketRadarExtraCandidates.value : marketRadarExtraCandidates.value.slice(0, 6)
))
const marketRadarHiddenCount = computed(() => Math.max(0, marketRadarExtraCandidates.value.length - marketRadarExtraVisible.value.length))
const showRadarWatchExpansion = computed(() => isRadarMode.value && marketRadarExtraCandidates.value.length > 0)
const accountPool = computed(() => applyPoolFilters(poolsData.value.account_executable_pool || []).sort(compareAccountExecutionPriority))
const focusMatches = computed(() => ({
  market: (poolsData.value.market_watch_pool || []).filter((stock) => matchesFocusSector(stock)).length,
  account: (poolsData.value.account_executable_pool || []).filter((stock) => matchesFocusSector(stock)).length,
}))
const accountEmptyReason = computed(() => {
  if (accountCount.value) return ''

  const rawReasons = [...marketPool.value]
    .flatMap((stock) => stock.not_other_pools || [])
    .map((reason) => String(reason || '').trim())
    .filter((reason) => (
      reason.includes('账户可参与池') ||
      reason.includes('账户条件') ||
      reason.includes('先处理旧仓') ||
      reason.includes('舒服买点') ||
      reason.includes('不直接执行')
    ))

  const normalizedReasons = []
  rawReasons.forEach((reason) => {
    const normalized = reason.replace(/^未进账户可参与池：/, '').trim()
    if (normalized && !normalizedReasons.includes(normalized)) {
      normalizedReasons.push(normalized)
    }
  })

  if (!normalizedReasons.length) {
    return holdingCount.value
      ? '先处理持仓风险；当前没有满足账户准入的新标的。'
      : '当前没有满足账户准入的新标的。'
  }

  const prefix = holdingCount.value ? '先处理持仓风险；' : ''
  return `${prefix}当前没有满足账户准入的新标的，主要因为：${normalizedReasons.slice(0, 2).join('；')}`
})

const accountEntryMode = (stock) => {
  const mode = String(stock?.account_entry_mode || '').trim().toLowerCase()
  if (['standard', 'aggressive_trial', 'defense_trial'].includes(mode)) return mode
  if (mode === 'trial') {
    return String(stock?.pool_entry_reason || '').includes('防守') ? 'defense_trial' : 'aggressive_trial'
  }
  const reason = String(stock?.pool_entry_reason || '')
  if (reason.includes('防守') && reason.includes('试错')) return 'defense_trial'
  if (reason.includes('试错')) return 'aggressive_trial'
  return 'standard'
}

const isAggressiveTrialExecution = (stock) => accountEntryMode(stock) === 'aggressive_trial'
const isDefenseTrialExecution = (stock) => accountEntryMode(stock) === 'defense_trial'
const standardExecutionPool = computed(() => accountPool.value.filter((stock) => accountEntryMode(stock) === 'standard'))
const readyStandardExecutionPool = computed(() => standardExecutionPool.value.filter((stock) => stock.execution_proximity_tag === '接近执行位'))
const waitingStandardExecutionPool = computed(() => standardExecutionPool.value.filter((stock) => stock.execution_proximity_tag !== '接近执行位'))
const aggressiveTrialPool = computed(() => accountPool.value.filter((stock) => isAggressiveTrialExecution(stock)))
const defenseTrialPool = computed(() => accountPool.value.filter((stock) => isDefenseTrialExecution(stock)))

const getEnvTagType = (tag) => {
  if (tag === '进攻') return 'success'
  if (tag === '中性') return 'warning'
  return 'danger'
}

const marketEnvironmentHeadline = computed(() => {
  if (todayMarketEnv.value.market_headline) return todayMarketEnv.value.market_headline
  if (todayMarketEnv.value.market_env_tag === '进攻') return '市场允许更主动，但依旧先分清标准候选和试错票。'
  if (todayMarketEnv.value.market_env_tag === '防守') return '今天先控仓和处理旧仓，新开仓只看极少数确认机会。'
  return '市场处于中性切换期，优先看回踩确认，不要把观察票当执行票。'
})

const marketEnvironmentCopy = computed(() => (
  todayMarketEnv.value.market_subheadline ||
  todayMarketEnv.value.market_comment ||
  (todayMarketEnv.value.breakout_allowed
    ? '允许做确认后的主动出手，但更适合先做计划内执行。'
    : '更适合等确认、看承接和控制仓位。')
))

const directionStateLabel = (sector) => {
  if (sector?.sector_rotation_tag) return sector.sector_rotation_tag
  if (sector?.sector_mainline_tag === '主线') return '稳定主线'
  if (sector?.sector_mainline_tag === '次主线') return '次主线'
  return '观察中'
}

const directionMainlineLabel = (sector) => {
  if (sector?.sector_mainline_tag) return sector.sector_mainline_tag
  return '主线'
}

const directionActionBadgeClass = (actionHint) => {
  if (actionHint === '可执行') return 'direction-badge-action-success'
  if (actionHint === '只观察') return 'direction-badge-action-warning'
  return 'direction-badge-action-muted'
}

const directionStateBadgeClass = (state) => {
  if (state === '强化中' || state === '盘中强化') return 'direction-badge-state-strong'
  if (state === '切换中') return 'direction-badge-state-rotating'
  if (state === '稳定主线') return 'direction-badge-state-stable'
  if (state === '衰减中') return 'direction-badge-state-weakening'
  return 'direction-badge-state-neutral'
}

const summarizedMainlineSectors = computed(() => {
  const mainline = (poolsData.value.mainline_sectors || []).slice(0, 3)
  if (mainline.length >= 3) return mainline
  const strengtheningSubs = (poolsData.value.sub_mainline_sectors || [])
    .filter((sector) => ['强化中', '切换中', '盘中强化', '稳定主线'].includes(directionStateLabel(sector)))
    .slice(0, Math.max(0, 3 - mainline.length))
  return [...mainline, ...strengtheningSubs]
})

const primaryDirectionItems = computed(() => summarizedMainlineSectors.value.map((sector) => ({
  name: sector.sector_name,
  changePct: Number(sector.sector_change_pct || 0),
  state: directionStateLabel(sector),
  mainlineTag: directionMainlineLabel(sector),
  tier: String(sector.sector_tier || '').trim(),
  actionHint: String(sector.sector_action_hint || '').trim(),
  subtitle: String(sector.sector_news_summary || '').trim(),
  reason: sector.sector_summary_reason || sector.sector_rotation_reason || sector.sector_comment || '先盯联动是否延续，再决定要不要往执行层下钻。',
})))

const directionHeadline = computed(() => {
  const lead = primaryDirectionItems.value[0]
  if (!lead) return '按正式板块扫描判断主线'
  const suffix = primaryDirectionItems.value.length > 1 ? `，带看 ${primaryDirectionItems.value.length} 个方向` : ''
  return `${lead.name} 领看${suffix}`
})

const directionOverviewCopy = computed(() => {
  const mainline = poolsData.value.mainline_sectors || []
  const leadSector = mainline[0]
  const secondaryNames = primaryDirectionItems.value.slice(1).map((item) => item.name)
  if (leadSector?.sector_summary_reason) {
    if (!secondaryNames.length) return leadSector.sector_summary_reason
    return `${leadSector.sector_summary_reason}；同时留意 ${secondaryNames.join('、')}。`
  }
  if (leadSector?.sector_comment) {
    if (!secondaryNames.length) return leadSector.sector_comment
    return `${leadSector.sector_comment}；同时留意 ${secondaryNames.join('、')}。`
  }
  if (!primaryDirectionItems.value.length) return '当前没有足够清晰的主线板块，优先看账户和持仓约束。'
  if (secondaryNames.length) return `优先看 ${primaryDirectionItems.value[0].name}，同时留意 ${secondaryNames.join('、')}。`
  return `今天先围绕 ${primaryDirectionItems.value[0].name} 这个方向做取舍。`
})

const goToSectors = (sectorName = '') => {
  if (sectorName) {
    router.push({ path: '/sectors', query: { focus_sector: sectorName } })
    return
  }
  router.push('/sectors')
}

const primaryDecisionStep = computed(() => decisionSteps.value[0] || null)

const executionGuidanceTitle = computed(() => {
  if (holdingCount.value) return '先处理持仓，再看新机会'
  if (globalTradeGate.value.status === '优先处理持仓，不建议新开') return '先处理持仓风险，不建议新开'
  if (globalTradeGate.value.status === '以防守为主') return '以防守为主，只保留极少数试错'
  if (readyStandardExecutionPool.value.length) return '优先看接近执行位的标准候选'
  if (standardExecutionPool.value.length) return '先看标准候选里的待触发票'
  if (aggressiveTrialPool.value.length) return '允许小仓试错，但别当标准模式'
  if (defenseTrialPool.value.length) return '防守环境仅保留轻仓试错'
  return '今天以观察和跟踪为主'
})

const executionGuidanceCopy = computed(() => {
  if (holdingCount.value) return '旧仓优先级最高；先把卖、减、持处理清楚，再决定是否看新票。'
  if (globalTradeGate.value.dominant_reason) return globalTradeGate.value.dominant_reason
  if (readyStandardExecutionPool.value.length && !aggressiveTrialPool.value.length) return '今天有接近执行位的标准候选，优先看这批；其余待触发票先别急着算成当前机会。'
  if (readyStandardExecutionPool.value.length && aggressiveTrialPool.value.length) return '先看接近执行位的标准候选；进攻试错只给强化方向前排的小仓资格，其他标准票仍要等触发。'
  if (standardExecutionPool.value.length && !aggressiveTrialPool.value.length) return '今天有通过账户准入的标准候选，但大多还在待触发区，仍要回买点页确认，不要被观察池分散注意力。'
  if (standardExecutionPool.value.length && aggressiveTrialPool.value.length) return '先看标准候选里的待触发票；进攻试错只给强化方向前排的小仓资格，两类都要回买点页确认执行位。'
  if (aggressiveTrialPool.value.length) return '今天没有太舒服的标准位，若要出手，只能在强化方向里做更快确认的试错仓。'
  if (defenseTrialPool.value.length) return '当前环境偏防守，只保留极少数最强核心股的轻仓试错资格，不要把它当进攻信号。'
  return '当前更适合先看观察池，等更清晰的确认条件。'
})

const executionEmptyStates = computed(() => {
  const states = []
  if (!standardExecutionPool.value.length) {
    states.push({
      key: 'standard',
      title: '标准候选',
      caption: '今天没有明确的计划内舒服位',
      reason: '当前账户可参与池更偏试错或防守保留，真正执行前更要依赖盘中确认。',
      tone: 'standard',
    })
  }
  if (!aggressiveTrialPool.value.length) {
    states.push({
      key: 'aggressive_trial',
      title: '进攻试错',
      caption: '当前没有需要额外放宽的小仓试错票',
      reason: standardExecutionPool.value.length
        ? '今天已有通过账户准入的标准候选，系统没有再额外放出高风险进攻试错。'
        : '今天没有命中“方向强但位置不完美”的试错分支，先别硬找强行出手点。',
      tone: 'trial',
    })
  }
  if (!defenseTrialPool.value.length) {
    states.push({
      key: 'defense_trial',
      title: '防守试错',
      caption: '防守保留模式今天没有触发',
      reason: todayMarketEnv.value.market_env_tag === '防守'
        ? '虽然是防守环境，但没有强到值得单列保留的最强核心股。'
        : '当前不是防守环境，这一栏通常保持为空，不需要额外关注。',
      tone: 'defense',
    })
  }
  return states
})

const accountPoolGroups = computed(() => {
  return [
    {
      key: 'standard_ready',
      title: '标准候选 · 接近执行位',
      desc: '这批票既通过账户准入，当前价也已经靠近执行区，优先看这一组。',
      items: readyStandardExecutionPool.value,
    },
    {
      key: 'standard_waiting',
      title: '标准候选 · 待触发',
      desc: '这批票已通过账户准入，但现价离执行位还有距离，先跟计划，不要当成当前立刻可买。',
      items: waitingStandardExecutionPool.value,
    },
    {
      key: 'aggressive_trial',
      title: '进攻试错',
      desc: '方向强但位置不完美，只给强化方向前排小仓试错资格。',
      items: aggressiveTrialPool.value,
    },
    {
      key: 'defense_trial',
      title: '防守试错',
      desc: '防守日仅保留极少数最强核心股轻仓试错，不属于主动进攻模式。',
      items: defenseTrialPool.value,
    },
  ].filter((group) => group.items.length)
})
const holdingPool = computed(() =>
  [...(poolsData.value.holding_process_pool || [])].sort(compareHoldingPriority)
)
const marketDirectionGroups = computed(() => {
  const grouped = new Map()
  marketPool.value.forEach((stock) => {
    const name = String(stock.sector_name || '').trim() || '未标记方向'
    const entry = grouped.get(name) || { name, items: [], top: null }
    entry.items.push(stock)
    if (!entry.top || Number(stock.market_strength_score || 0) > Number(entry.top.market_strength_score || 0)) {
      entry.top = stock
    }
    grouped.set(name, entry)
  })
  return [...grouped.values()]
    .sort((a, b) => Number(b.top?.market_strength_score || 0) - Number(a.top?.market_strength_score || 0))
    .slice(0, 4)
    .map((group) => ({
      name: group.name,
      state: directionStateLabel(group.top),
      summary: group.top?.direction_signal_reason || group.top?.stock_comment || '方向还在观察期，重点看前排承接和一致性。',
      items: group.items.slice(0, 4),
    }))
})

const reviewSnapshotTypeLabel = (value) => {
  if (value === 'buy_available') return '买点-可买'
  if (value === 'buy_observe') return '买点-观察'
  if (value === 'buy_add') return '加仓候选'
  if (value === 'pool_account') return '三池-可参与池'
  if (value === 'pool_market') return '三池-观察池'
  return value || '-'
}

const reviewSourceLabel = computed(() => reviewSnapshotTypeLabel(reviewSourceFilter.value))

const resolveDefaultTab = () => {
  if (reviewSourceFilter.value === 'pool_account') {
    return accountCount.value ? 'account' : holdingCount.value ? 'holding' : 'market'
  }
  if (reviewSourceFilter.value === 'pool_market') {
    return marketCount.value ? 'market' : accountCount.value ? 'account' : 'holding'
  }
  if (holdingCount.value) return 'holding'
  if (accountCount.value) return 'account'
  return 'market'
}

const reviewRowLabel = (row) => `${reviewSnapshotTypeLabel(row.snapshot_type)} / ${row.candidate_bucket_tag || '未分层'}`

const reviewActionableRows = computed(() => (
  (reviewStatsData.value?.bucket_stats || [])
    .filter((row) => row.snapshot_type !== 'buy_add')
    .map((row) => ({
      ...row,
      shortLabel: reviewRowLabel(row),
      resolvedWeight: Number(row.resolved_5d_count || row.resolved_3d_count || row.resolved_1d_count || 0),
      qualityScore:
        Number(row.avg_return_5d || 0) * 0.6 +
        Number(row.win_rate_5d || 0) * 0.04 +
        Number(row.avg_return_3d || 0) * 0.25 +
        Number(row.win_rate_3d || 0) * 0.015 +
        Number(row.count || 0) * 0.03
    }))
    .filter((row) => row.resolvedWeight > 0 && Number(row.count || 0) >= 2)
    .sort((a, b) => Number(b.qualityScore || 0) - Number(a.qualityScore || 0))
))

const reviewInsight = computed(() => {
  const best = reviewActionableRows.value[0]
  const weakest = [...reviewActionableRows.value].sort((a, b) => Number(a.qualityScore || 0) - Number(b.qualityScore || 0))[0]
  const watch = reviewActionableRows.value.find((row) => row.snapshot_type === 'buy_observe' || row.snapshot_type === 'pool_market')
  if (!best && !weakest && !watch) return null

  return {
    doText: best
      ? `最近 ${best.shortLabel} 胜率和均值更强，今天在观察池和账户池里遇到同类结构时，可以更优先盯。`
      : '当前复盘样本还不够，今天先按当日盘面和账户准入为主。',
    watchText: watch
      ? `${watch.shortLabel} 更适合先当观察对象，先看承接和确认，不要因为进池就直接当执行信号。`
      : '观察池仍然只负责缩小范围，不负责替代买点确认。',
    avoidText: weakest
      ? `${weakest.shortLabel} 最近表现偏弱，今天即使进池也先降优先级，别因为题材热度就直接提高权重。`
      : '暂时没有明确需要整体降权的一类信号。'
  }
})

const overviewTitle = computed(() => {
  if (globalTradeGate.value.status === '优先处理持仓，不建议新开') return '先处理旧仓风险，今天不建议新增仓位'
  if (holdingCount.value) return '已有仓位优先，先把该卖、该减、该持有的动作排清楚'
  if (accountCount.value) return '当前有通过账户准入的新标的，先看账户可参与池，再回到买点页确认'
  if (marketCount.value) return '当前更适合先观察市场最强结构，不要把观察票当成执行票'
  return '今天几类观察池都比较清淡，先等新的结构和账户信号'
})

const overviewDesc = computed(() => {
  if (globalTradeGate.value.status === '优先处理持仓，不建议新开') return globalTradeGate.value.dominant_reason
  if (holdingCount.value) return '持仓处理池是今天优先级最高的区域；先处理旧仓风险，再决定是否看新票。'
  if (accountCount.value) return '账户可参与池说明系统已经过了账户准入这一步，但真正执行仍要结合买点和盘中确认。'
  if (marketCount.value) return '观察池的任务是帮你缩小盯盘范围，先看方向、板块和量能，不要直接下单。'
  return '当前没有明显需要处理的仓位，也没有通过准入的新标的，适合保持节奏。'
})

const operatorBarTitle = computed(() => overviewTitle.value)
const operatorBarDesc = computed(() => compactRuleSummary.value || overviewDesc.value)

const overviewRules = computed(() => {
  if (globalTradeGate.value.status === '优先处理持仓，不建议新开') {
    return ['先处理旧仓风险', '今天不建议新开仓', '观察池只负责跟踪，不负责下单']
  }
  if (holdingCount.value) {
    return ['先处理旧仓，再考虑新开仓', '动作建议优先看高优先级', '证伪条件到了就不要拖']
  }
  if (accountCount.value) {
    return ['先看进池理由', '仓位提示比题材更重要', '通过账户准入不等于现价立刻可买']
  }
  return ['观察池只负责缩小盯盘范围', '先看最强结构，再看账户是否允许', '没有执行确认就不要急着动']
})

const clearReviewFilter = () => {
  const query = { ...route.query }
  delete query.review_bucket
  delete query.review_source
  router.replace({ query })
}

const compactRuleSummary = computed(() => overviewRules.value.slice(0, 2).join(' · '))

const decisionSteps = computed(() => {
  const steps = []
  if (holdingCount.value) {
    steps.push({
      key: 'holding',
      rank: 1,
      tab: 'holding',
      tone: 'holding',
      title: '先处理持仓',
      desc: '先把已有仓位的卖、减、持动作排清楚，再决定要不要开新仓。',
      countLabel: `${holdingCount.value} 只待处理`,
      rule: '旧仓优先',
      hint: '高优先级和明确卖减信号先处理',
    })
  }

  if (accountCount.value) {
    steps.push({
      key: 'account',
      rank: steps.length + 1,
      tab: 'account',
      tone: 'account',
      title: '再看账户可参与',
      desc: '这批票已经通过账户准入，但真正执行还要回买点页等确认。',
      countLabel: `${accountCount.value} 只可参与`,
      rule: '过准入但别急追',
      hint: '先看进池理由，再回买点页看执行位',
    })
  }
  steps.push({
    key: 'market',
    rank: steps.length + 1,
    tab: 'market',
    tone: 'market',
    title: '最后回观察池',
    desc: '观察池负责缩小范围和校准方向，不负责替代买点确认。',
    countLabel: `${marketCount.value} 只观察票`,
    rule: '只观察',
    hint: '先看最强结构和板块一致性',
  })

  return steps.slice(0, 3)
})

const activateTab = async (tab, options = {}) => {
  activeTab.value = tab
  if (!options.scroll) return
  await nextTick()
  const target = detailCardRef.value?.$el || detailCardRef.value
  if (!target || typeof target.scrollIntoView !== 'function') return
  target.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const focusItemTab = (item) => {
  if (item?.poolKey === 'holding') return 'holding'
  if (item?.poolKey === 'account') return 'account'
  return 'market'
}

const focusItemPoolLabel = (item) => {
  if (item?.poolKey === 'holding') return '持仓处理池'
  if (item?.poolKey === 'account') return '账户可参与池'
  return '市场观察池'
}

const openFocusAnalysis = (item) => {
  if (!item?.stock) return
  if (item.poolKey === 'holding') {
    openSellAnalysis(item.stock)
    return
  }
  openBuyAnalysis(item.stock)
}

const focusSummary = computed(() => {
  if (!focusSector.value) return ''
  if (focusMatches.value.account) {
    return `${focusSector.value} 已经有 ${focusMatches.value.account} 只进入账户可参与池，可以先看账户池，再去买点页确认执行位。`
  }
  if (focusMatches.value.market) {
    return `${focusSector.value} 目前更多停留在市场观察池，说明这条线还在观察期，先看板块一致性和量能。`
  }
  return `${focusSector.value} 当前没有明显命中三池核心候选，说明这条线今天暂时不是主执行方向。`
})

const topFocusItems = computed(() => {
  const items = []

  holdingPool.value.slice(0, 2).forEach((stock) => {
    items.push({
      poolKey: 'holding',
      stock,
      ts_code: stock.ts_code,
      stock_name: stock.stock_name,
      focus: stock.sell_trigger_cond || stock.sell_reason || stock.sell_comment || '继续跟踪盘中变化',
      meta: `${stock.sell_signal_tag || '观察'} / ${stock.sell_priority || '低'}优先 / ${formatSignedPct(stock.pnl_pct)}`,
      orderLabel: holdingOrderLabel(items.length),
    })
  })

  if (accountPool.value.length) {
    const stock = readyStandardExecutionPool.value[0] || accountPool.value[0]
    items.push({
      poolKey: 'account',
      stock,
      ts_code: stock.ts_code,
      stock_name: stock.stock_name,
      focus: stock.execution_proximity_note || stock.pool_entry_reason || stock.position_hint || stock.stock_comment || '等待买点确认',
      meta: `可参与 / ${stock.execution_proximity_tag || stock.candidate_bucket_tag || '未分层'} / ${formatSignedPct(stock.change_pct)}`,
      orderLabel: items.length ? '再看 ' : '先看 ',
    })
  } else if (marketPool.value.length) {
    const stock = marketPool.value[0]
    items.push({
      poolKey: 'market',
      stock,
      ts_code: stock.ts_code,
      stock_name: stock.stock_name,
      focus: stock.stock_comment || stock.stock_falsification_cond || '先看板块和量能',
      meta: `观察池 / ${stock.candidate_bucket_tag || '未分层'} / ${formatSignedPct(stock.change_pct)}`,
      orderLabel: items.length ? '再盯 ' : '先盯 ',
    })
  }

  return items.slice(0, 3).map((item, index) => ({
    ...item,
    rank: index + 1,
    orderLabel: index === 0 ? item.orderLabel : index === 1 ? item.orderLabel.replace(/^先/, '再') : item.orderLabel.replace(/^先|^再/, '最后'),
  }))
})

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const formatPrice = (value) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(2)
}

const formatScore = (value) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(1)
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

const formatSignedNumber = (value, suffix = '') => {
  if (value === null || value === undefined) return '-'
  return `${Number(value).toFixed(1)}${suffix}`
}

const formatQty = (value) => {
  if (value === null || value === undefined) return '-'
  return `${value}股`
}

const formatMoney = (value) => {
  if (value === null || value === undefined) return '-'
  return `${Number(value).toFixed(0)}元`
}

const formatDays = (value) => {
  if (value === null || value === undefined) return '-'
  return `${value}天`
}

const pctClass = (value) => {
  if (value === null || value === undefined) return ''
  if (Number(value) > 0) return 'text-red'
  if (Number(value) < 0) return 'text-green'
  return 'text-neutral'
}

const executionProximityTagType = (stock) => {
  const tag = String(stock?.execution_proximity_tag || '')
  if (tag === '接近执行位') return 'success'
  if (tag === '已过确认位') return 'warning'
  if (tag === '待回踩' || tag === '待低吸' || tag === '待突破') return 'info'
  if (tag === '待深回踩') return 'danger'
  return 'info'
}

const executionProximityChipClass = (stock) => {
  const tag = String(stock?.execution_proximity_tag || '')
  if (tag === '接近执行位') return 'action-state-chip-success'
  if (tag === '已过确认位') return 'action-state-chip-warning'
  if (tag === '待深回踩') return 'action-state-chip-danger'
  return 'action-state-chip-info'
}

const executionProximityStripClass = (stock) => {
  const tag = String(stock?.execution_proximity_tag || '')
  if (tag === '接近执行位') return 'execution-proximity-strip-success'
  if (tag === '已过确认位') return 'execution-proximity-strip-warning'
  if (tag === '待深回踩') return 'execution-proximity-strip-danger'
  return 'execution-proximity-strip-info'
}

const executionProximityNoteClass = (stock) => {
  const tag = String(stock?.execution_proximity_tag || '')
  if (tag === '接近执行位') return 'action-proximity-success'
  if (tag === '已过确认位') return 'action-proximity-warning'
  if (tag === '待深回踩') return 'action-proximity-danger'
  return 'action-proximity-info'
}

const executionGapClass = (stock) => {
  const tag = String(stock?.execution_proximity_tag || '')
  if (tag === '接近执行位') return 'text-accent-success'
  if (tag === '已过确认位') return 'text-accent-warning'
  if (tag === '待深回踩') return 'text-accent-danger'
  return 'text-accent-info'
}

const reviewBiasTagType = (label) => {
  if (label === '复盘加分') return 'success'
  if (label === '复盘降权') return 'danger'
  return 'info'
}

const isRealtimeSource = (source) => String(source || '').startsWith('realtime_')

const quoteSourceLabel = (source) => {
  if (!source) return '日线回退'
  if (String(source).startsWith('realtime_')) return '盘中实时'
  if (source === 'mock') return '模拟数据'
  return '日线回退'
}

const quoteMetaLine = (source, quoteTime, fallbackDate) => {
  const label = quoteSourceLabel(source)
  if (quoteTime) return `${label} ${formatLocalTime(quoteTime)}`
  if (fallbackDate) return `${label} ${fallbackDate}`
  return label
}

const sellTagType = (value) => {
  if (value === '卖出') return 'danger'
  if (value === '减仓') return 'warning'
  if (value === '持有') return 'success'
  return 'info'
}

const priorityTagType = (value) => {
  if (value === '高') return 'danger'
  if (value === '中') return 'warning'
  return 'info'
}

const accountEntryTag = (stock) => {
  if (accountEntryMode(stock) === 'defense_trial') return '防守试错'
  if (accountEntryMode(stock) === 'aggressive_trial') return '进攻试错'
  return '通过准入'
}

const accountEntryTagType = (stock) => {
  if (accountEntryMode(stock) === 'defense_trial') return 'warning'
  if (accountEntryMode(stock) === 'aggressive_trial') return 'danger'
  return 'success'
}

const stockProfileTags = (stock) => [
  stock.sector_profile_tag,
  stock.representative_role_tag,
  stock.stock_role_tag,
  stock.day_strength_tag,
  stock.structure_state_tag,
  stock.next_tradeability_tag,
].filter(Boolean)

const representativeRoleLine = (stock) => `主线样本：${stock.representative_role_tag}，用于代表这条线的结构和跟踪价值。`

const notOtherPoolsLine = (stock) => {
  const reasons = stock.not_other_pools || []
  if (!reasons.length) return '当前没有额外降级说明。'
  return reasons.join(' ')
}

const watchOnlyReasonLine = (stock) => (
  stock.why_not_executable_but_should_watch ||
  notOtherPoolsLine(stock)
)

const emptyPoolText = (poolKey) => {
  if (poolKey === 'account') {
    return accountEmptyReason.value
  }
  if (poolKey === 'trend') {
    return '暂无结构清晰、值得持续盯的趋势锚。'
  }
  return '暂无需要观察的强势候选'
}

const marketActionLine = (stock) => stock.direction_signal_reason || stock.stock_comment || '先观察这只票是否继续保持强势结构。'
const marketFooterLine = (stock) => `${stock.stock_strength_tag || '中'}强度 / 市场分${formatScore(stock.market_strength_score)} / 执行分${formatScore(stock.execution_opportunity_score)}`
const trendActionLine = (stock) => stock.direction_signal_reason || stock.why_this_pool || '这只票更适合盯结构和承接，不急着看日内最炸。'
const trendFooterLine = (stock) => `${stock.structure_state_tag || '结构'} / ${stock.next_tradeability_tag || '待确认'} / 执行分${formatScore(stock.execution_opportunity_score)}`
const accountActionLine = (stock) => stock.pool_entry_reason || stock.stock_comment || '这只票已通过账户准入，但现价是否能做仍要回买点页确认。'
const accountFooterFlag = (stock) => {
  if (accountEntryMode(stock) === 'defense_trial') return '防守仓先行'
  if (accountEntryMode(stock) === 'aggressive_trial') return '试错仓先行'
  return '回买点页确认'
}
const holdingActionLine = (stock) => `${stock.sell_signal_tag || '观察'}：${stock.sell_reason || stock.sell_comment || '继续跟踪。'}`
const holdingFooterFlag = (stock) => (stock.can_sell_today ? '今日可卖' : 'T+1锁定')
const hardFilterLine = (stock) => stock.hard_filter_summary || '硬过滤状态未返回'

const sellSignalRank = (value) => {
  if (value === '卖出') return 0
  if (value === '减仓') return 1
  if (value === '持有') return 2
  return 3
}

const priorityRank = (value) => {
  if (value === '高') return 0
  if (value === '中') return 1
  return 2
}

const compareHoldingPriority = (a, b) => {
  const signalDiff = sellSignalRank(a.sell_signal_tag) - sellSignalRank(b.sell_signal_tag)
  if (signalDiff !== 0) return signalDiff
  const priorityDiff = priorityRank(a.sell_priority) - priorityRank(b.sell_priority)
  if (priorityDiff !== 0) return priorityDiff
  return Math.abs(Number(b.pnl_pct || 0)) - Math.abs(Number(a.pnl_pct || 0))
}

const holdingOrderLabel = (index) => {
  if (index === 0) return '先处理 '
  if (index === 1) return '再处理 '
  return '最后处理 '
}

const executionMethodLabel = (stock) => {
  if (['低吸预备', '有低吸点'].includes(stock.next_tradeability_tag)) return '低吸'
  if (['回踩确认', '有回踩确认点'].includes(stock.next_tradeability_tag)) return '回踩确认'
  if (['突破确认', '有突破点'].includes(stock.next_tradeability_tag)) return '突破确认'
  if (accountEntryMode(stock) === 'defense_trial') return '轻仓确认 / 不追高'
  if (accountEntryMode(stock) === 'aggressive_trial') return '分歧转强 / 放量确认'
  return '观察'
}

const executionPositionLabel = (stock) => {
  if (accountEntryMode(stock) === 'defense_trial') return '防守仓 / 更小仓'
  if (accountEntryMode(stock) === 'aggressive_trial') return '试错仓 / 小仓'
  return '计划仓 / 待确认'
}

const executionJudgementLine = (stock) => {
  if (accountEntryMode(stock) === 'defense_trial') {
    return stock.why_not_executable_but_should_watch || '防守环境下只保留最强核心股的轻仓试错，不可当成主动进攻机会。'
  }
  if (accountEntryMode(stock) === 'aggressive_trial') {
    return stock.why_not_executable_but_should_watch || '方向强度够，但位置不够舒服，只适合小仓试错。'
  }
  return stock.pool_entry_reason || stock.stock_comment || '已通过账户准入，但是否当前可做仍要回买点页看触发位。'
}

const executionRiskLine = (stock) => (
  stock.stock_falsification_cond
    ? `失效条件：${stock.stock_falsification_cond}`
    : '风险提示：确认失败就不要硬扛。'
)

const trialRiskLine = (stock) => (
  stock.miss_risk_note || (
    accountEntryMode(stock) === 'defense_trial'
      ? '风险提示：防守环境下只做轻仓确认，若承接转弱或环境继续恶化应更快撤退。'
      : '风险提示：若次日不继续强化，容易直接回落；不可当成标准候选就直接重仓处理。'
  )
)

const watchRoleLabel = (stock) => stock.representative_role_tag || stock.stock_role_tag || '代表票'
const watchKeyLine = (stock) => stock.stock_comment || stock.direction_signal_reason || '先看方向一致性和承接。'
const trendUpgradeLine = (stock) => (
  stock.miss_risk_note || stock.why_not_executable_but_should_watch || '若后续出现更清晰的方向确认或买点确认，可升级为执行票。'
)

const openCheckup = (stock, defaultTarget = '观察型') => {
  checkupStock.value = {
    tsCode: stock.ts_code,
    stockName: stock.stock_name || stock.ts_code,
    defaultTarget
  }
  checkupVisible.value = true
}

const openBuyAnalysis = (stock) => {
  buyAnalysisStock.value = {
    tsCode: stock.ts_code,
    stockName: stock.stock_name || stock.ts_code,
    sourcePoolTag: String(stock.stock_pool_tag || ''),
    currentPrice: stock.close ?? null,
    currentChangePct: stock.change_pct ?? null,
  }
  buyAnalysisVisible.value = true
}

const openSellAnalysis = (stock) => {
  sellAnalysisStock.value = {
    tsCode: stock.ts_code,
    stockName: stock.stock_name || stock.ts_code,
    currentPrice: stock.close ?? null,
    currentPnlPct: stock.pnl_pct ?? null,
  }
  sellAnalysisVisible.value = true
}

const handleRefresh = async () => {
  stopRadarAutoRefresh()
  await loadData({ refresh: true })
}

const clearFocusSector = () => {
  const query = { ...route.query }
  delete query.focus_sector
  router.replace({ query })
}

const loadData = async (options = {}) => {
  if (!options.polling) {
    loading.value = true
  }
  try {
    const tradeDate = getLocalDate()
    displayDate.value = tradeDate
    if (!options.polling) {
      loadError.value = ''
    }
    const res = await stockApi.pools(tradeDate, 50, { ...options, mode: poolMode.value, timeout: POOLS_TIMEOUT })
    const payload = res.data.data || {
      global_trade_gate: null,
      market_watch_pool: [],
      market_watch_candidates: [],
      market_watch_candidate_count: 0,
      account_executable_pool: [],
      holding_process_pool: [],
      resolved_trade_date: '',
      sector_scan_trade_date: '',
      sector_scan_resolved_trade_date: '',
      market_env: null,
      mainline_sectors: [],
      sub_mainline_sectors: [],
      refresh_in_progress: false,
      refresh_requested: false,
      stale_snapshot: false,
      candidate_data_status: '',
      candidate_data_message: '',
      snapshot_status_message: '',
      mode: poolMode.value,
      is_realtime: poolMode.value === 'radar',
      radar_generated_at: '',
    }
    poolsData.value = payload
    if (!isRadarMode.value) {
      watchCandidatesExpanded.value = false
    }
    activeTab.value = resolveDefaultTab()
    if (payload.refresh_in_progress) {
      scheduleRefreshPolling()
    } else {
      stopRefreshPolling()
      if (waitingForRefreshResult.value) {
        ElMessage.success('三池结果已刷新完成。')
        waitingForRefreshResult.value = false
      }
    }
    if (isRadarMode.value) {
      scheduleRadarAutoRefresh()
    } else {
      stopRadarAutoRefresh()
    }
    if (options.refresh) {
      if (payload.refresh_requested) {
        waitingForRefreshResult.value = true
        ElMessage.success('已触发后台刷新，当前先展示已有三池结果。')
      } else if (payload.refresh_in_progress) {
        waitingForRefreshResult.value = true
        ElMessage.info('三池后台刷新仍在进行中，当前先展示已有结果。')
      }
    }
  } catch (error) {
    stopRefreshPolling()
    stopRadarAutoRefresh()
    loadError.value = error?.code === 'ECONNABORTED'
      ? '三池分类加载超时，后端仍在重算候选池，请稍后刷新。'
      : `三池分类加载失败：${error?.message || '未知错误'}`
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

const loadReviewInsight = async () => {
  try {
    const res = await decisionApi.reviewStats(10, { timeout: REVIEW_STATS_TIMEOUT })
    reviewStatsData.value = res.data.data || null
  } catch (error) {
    reviewStatsData.value = null
  }
}

onMounted(() => {
  displayDate.value = getLocalDate()
  loadData()
  loadReviewInsight()
})

watch(poolMode, async (nextMode) => {
  stopRadarAutoRefresh()
  const query = { ...route.query }
  if (nextMode === 'radar') {
    query.mode = 'radar'
  } else {
    delete query.mode
  }
  await router.replace({ query })
  loadData({ refresh: true })
})

onUnmounted(() => {
  stopRefreshPolling()
  stopRadarAutoRefresh()
})

watch(reviewSourceFilter, () => {
  activeTab.value = resolveDefaultTab()
})

watch(
  () => route.query.mode,
  (value) => {
    const normalized = String(value || 'stable').trim() === 'radar' ? 'radar' : 'stable'
    if (poolMode.value !== normalized) {
      poolMode.value = normalized
    }
  }
)

const handleVisibilityChange = () => {
  if (document.hidden) {
    stopRadarAutoRefresh()
    return
  }
  if (isRadarMode.value) {
    loadData({ polling: true, radarAuto: true })
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<style scoped>
.pools-view {
  min-height: 100%;
}

.page-alert {
  margin-bottom: 16px;
}

.command-center {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(0, 1.3fr) minmax(300px, 0.95fr);
  gap: 14px;
  margin-bottom: 18px;
  align-items: stretch;
}

.summary-card {
  display: grid;
  gap: 12px;
  padding: 18px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.08), transparent 38%),
    linear-gradient(155deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02));
}

.ops-toolbar {
  display: grid;
  gap: 14px;
  margin-bottom: 18px;
  padding: 18px;
  border-radius: 20px;
  border: 1px solid rgba(113, 170, 255, 0.12);
  background:
    radial-gradient(circle at top right, rgba(103, 165, 255, 0.14), transparent 36%),
    linear-gradient(145deg, rgba(18, 25, 42, 0.95), rgba(13, 17, 29, 0.98));
}

.ops-toolbar-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.ops-toolbar-copy {
  display: grid;
  gap: 6px;
}

.ops-toolbar-title {
  font-size: 1.08rem;
  font-weight: 800;
  line-height: 1.35;
  color: #fff;
}

.ops-toolbar-desc {
  max-width: 900px;
  font-size: 13px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.78);
}

.ops-toolbar-context,
.ops-toolbar-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}

.ops-context-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.88);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.ops-step-button {
  appearance: none;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  cursor: pointer;
  transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
}

.ops-step-button:hover,
.ops-step-button:focus-visible {
  transform: translateY(-1px);
  border-color: rgba(145, 196, 255, 0.24);
  background: rgba(255, 255, 255, 0.06);
}

.ops-step-button-holding {
  box-shadow: inset 0 0 0 1px rgba(243, 157, 86, 0.1);
}

.ops-step-button-account {
  box-shadow: inset 0 0 0 1px rgba(47, 207, 154, 0.1);
}

.ops-step-button-market {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.1);
}

.ops-step-rank {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #587cff, #78b0ff);
}

.ops-step-copy {
  display: grid;
  gap: 2px;
  text-align: left;
}

.ops-step-copy strong {
  font-size: 13px;
  color: #fff;
}

.ops-step-copy em {
  font-size: 12px;
  color: var(--color-text-sec);
  font-style: normal;
}

.summary-card-decision {
  background:
    radial-gradient(circle at top right, rgba(255, 187, 92, 0.18), transparent 36%),
    radial-gradient(circle at bottom left, rgba(54, 194, 117, 0.14), transparent 34%),
    linear-gradient(155deg, rgba(65, 39, 12, 0.92), rgba(24, 29, 18, 0.98));
}

.summary-card-direction {
  background:
    radial-gradient(circle at top right, rgba(80, 156, 255, 0.18), transparent 36%),
    linear-gradient(155deg, rgba(14, 42, 77, 0.9), rgba(12, 24, 46, 0.97));
}

.summary-card-account {
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.08), transparent 40%),
    linear-gradient(155deg, rgba(42, 44, 57, 0.92), rgba(23, 24, 31, 0.98));
}

.summary-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.66);
}

.summary-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.summary-card-head-direction :deep(.el-button) {
  padding-inline: 0;
  color: #9cc7ff;
}

.decision-priority-pill {
  display: grid;
  gap: 2px;
  min-width: 112px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.decision-priority-pill span {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.66);
}

.decision-priority-pill strong {
  font-size: 14px;
  color: #fff;
}

.summary-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.summary-headline {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.35;
  color: #fff;
}

.summary-headline-action {
  font-size: 20px;
}

.summary-copy {
  font-size: 13px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.78);
}

.summary-chip-row,
.direction-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.summary-chip,
.direction-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.88);
  font-size: 12px;
}

.summary-chip strong,
.direction-pill strong {
  font-weight: 700;
}

.direction-pill em {
  font-style: normal;
  color: rgba(255, 255, 255, 0.64);
}

.direction-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.direction-card {
  appearance: none;
  display: grid;
  gap: 10px;
  width: 100%;
  padding: 14px;
  text-align: left;
  border-radius: 16px;
  border: 1px solid rgba(129, 180, 255, 0.14);
  background:
    radial-gradient(circle at top right, rgba(109, 171, 255, 0.14), transparent 40%),
    rgba(255, 255, 255, 0.04);
  color: inherit;
  cursor: pointer;
  transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
}

.direction-card-lead {
  grid-column: 1 / -1;
}

.direction-card:hover,
.direction-card:focus-visible {
  transform: translateY(-1px);
  border-color: rgba(150, 201, 255, 0.28);
  background:
    radial-gradient(circle at top right, rgba(109, 171, 255, 0.2), transparent 40%),
    rgba(255, 255, 255, 0.06);
}

.direction-card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.direction-card-title-group {
  display: grid;
  gap: 4px;
}

.direction-card-top strong {
  font-size: 16px;
  font-weight: 700;
  color: #fff;
}

.direction-card-subtitle {
  font-size: 12px;
  line-height: 1.5;
  color: rgba(167, 206, 255, 0.84);
}

.direction-card-change {
  font-size: 13px;
  font-weight: 700;
}

.direction-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.direction-badge {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.9);
  background: rgba(255, 255, 255, 0.08);
}

.direction-badge-mainline {
  background: rgba(95, 170, 255, 0.16);
  color: #d6e8ff;
}

.direction-badge-tier {
  background: rgba(255, 193, 102, 0.16);
  color: #ffe2af;
}

.direction-badge-action-success {
  background: rgba(54, 194, 117, 0.18);
  color: #cffff0;
}

.direction-badge-action-warning {
  background: rgba(255, 188, 84, 0.18);
  color: #ffe1ae;
}

.direction-badge-action-muted {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.82);
}

.direction-badge-state-strong {
  background: rgba(76, 180, 255, 0.18);
  color: #d9eeff;
}

.direction-badge-state-rotating {
  background: rgba(184, 133, 255, 0.18);
  color: #ead8ff;
}

.direction-badge-state-stable {
  background: rgba(83, 214, 147, 0.18);
  color: #d4ffe8;
}

.direction-badge-state-weakening {
  background: rgba(255, 132, 132, 0.16);
  color: #ffd6d6;
}

.direction-badge-state-neutral {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.8);
}

.direction-card-copy {
  font-size: 13px;
  line-height: 1.65;
  color: rgba(255, 255, 255, 0.78);
}

.decision-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.decision-summary-panel {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.decision-summary-label {
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.62);
}

.decision-summary-value {
  font-size: 18px;
  line-height: 1.4;
  color: #fff;
}

.decision-summary-text {
  font-size: 13px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.76);
}

.decision-step-inline-list {
  display: grid;
  gap: 10px;
}

.decision-step-inline {
  appearance: none;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.035);
  color: inherit;
  cursor: pointer;
  transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
}

.decision-step-inline:hover,
.decision-step-inline:focus-visible {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.055);
}

.decision-step-inline-holding {
  box-shadow: inset 0 0 0 1px rgba(243, 157, 86, 0.1);
}

.decision-step-inline-account {
  box-shadow: inset 0 0 0 1px rgba(47, 207, 154, 0.1);
}

.decision-step-inline-market {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.1);
}

.decision-step-inline-rank {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #f39d56, #ffbf66);
}

.decision-step-inline-copy {
  display: grid;
  gap: 2px;
  text-align: left;
}

.decision-step-inline-copy strong {
  font-size: 13px;
  color: #fff;
}

.decision-step-inline-copy em {
  font-size: 12px;
  color: var(--color-text-sec);
  font-style: normal;
}

.priority-stack {
  display: grid;
  gap: 18px;
  margin-bottom: 20px;
}

.priority-panel,
.detail-card {
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
}

.priority-panel-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.priority-panel-desc {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-sec);
}

.priority-empty,
.lane-empty {
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.035);
  color: var(--color-text-sec);
}

.execution-lane-stack {
  display: grid;
  gap: 14px;
}

.execution-dual-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.execution-lane {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.execution-lane-standard {
  background: linear-gradient(180deg, rgba(18, 78, 48, 0.28), rgba(20, 29, 25, 0.45));
}

.execution-lane-trial {
  background: linear-gradient(180deg, rgba(116, 58, 12, 0.3), rgba(39, 24, 13, 0.48));
}

.execution-lane-defense {
  background: linear-gradient(180deg, rgba(107, 76, 17, 0.28), rgba(39, 33, 12, 0.46));
}

.execution-empty-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.execution-empty-card {
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(255, 255, 255, 0.025);
}

.execution-empty-card-standard {
  box-shadow: inset 0 0 0 1px rgba(45, 197, 104, 0.08);
}

.execution-empty-card-trial {
  box-shadow: inset 0 0 0 1px rgba(255, 161, 59, 0.08);
}

.execution-empty-card-defense {
  box-shadow: inset 0 0 0 1px rgba(245, 204, 96, 0.08);
}

.execution-empty-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.execution-empty-title {
  font-size: 15px;
  font-weight: 700;
  color: #fff;
}

.execution-empty-caption {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-sec);
}

.execution-empty-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 52px;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  font-weight: 700;
}

.execution-empty-reason {
  font-size: 13px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.76);
}

.lane-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.lane-title {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
}

.lane-caption {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.72);
}

.lane-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 58px;
  height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(45, 197, 104, 0.18);
  color: #aef2c8;
  font-size: 12px;
  font-weight: 700;
}

.lane-badge-trial {
  background: rgba(255, 161, 59, 0.2);
  color: #ffd6a2;
}

.lane-badge-defense {
  background: rgba(245, 204, 96, 0.2);
  color: #ffe39d;
}

.action-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(9, 10, 13, 0.28);
}

.action-card-standard {
  box-shadow: inset 0 1px 0 rgba(132, 255, 184, 0.06);
}

.action-card-trial {
  box-shadow: inset 0 1px 0 rgba(255, 189, 120, 0.08);
}

.action-card-defense {
  box-shadow: inset 0 1px 0 rgba(255, 223, 120, 0.08);
}

.action-card-top,
.trend-preview-top,
.watch-group-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.action-stock,
.watch-group-title {
  font-size: 17px;
  font-weight: 700;
  color: #fff;
}

.action-meta,
.watch-group-state {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-sec);
}

.action-type-badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.action-type-badge-standard {
  background: rgba(57, 181, 74, 0.16);
  color: #aef2c8;
}

.action-type-badge-trial {
  background: rgba(255, 161, 59, 0.2);
  color: #ffd6a2;
}

.action-type-badge-defense {
  background: rgba(245, 204, 96, 0.2);
  color: #ffe39d;
}

.action-type-badge-watch {
  background: rgba(80, 156, 255, 0.18);
  color: #b8d7ff;
}

.action-state-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.action-state-chip {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  font-size: 12px;
  color: rgba(255, 255, 255, 0.86);
}

.action-state-chip-success {
  background: rgba(47, 207, 154, 0.18);
  color: #cffff0;
}

.action-state-chip-warning {
  background: rgba(255, 186, 82, 0.18);
  color: #ffe1b0;
}

.action-state-chip-danger {
  background: rgba(255, 120, 120, 0.16);
  color: #ffd0d0;
}

.action-state-chip-info {
  background: rgba(88, 176, 255, 0.14);
  color: #dceeff;
}

.action-judgement,
.watch-group-insight {
  font-size: 14px;
  line-height: 1.8;
  color: rgba(255, 255, 255, 0.9);
}

.action-proximity {
  font-size: 13px;
  line-height: 1.6;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.action-proximity-success {
  color: #dffdf1;
  background: rgba(30, 145, 103, 0.12);
}

.action-proximity-warning {
  color: #ffe5ba;
  background: rgba(214, 149, 45, 0.12);
}

.action-proximity-danger {
  color: #ffd5d5;
  background: rgba(191, 78, 78, 0.12);
}

.action-proximity-info {
  color: #dceeff;
  background: rgba(68, 116, 184, 0.12);
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.action-block {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
}

.action-block-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.action-block strong {
  color: #fff;
  font-size: 14px;
}

.action-reason,
.action-risk {
  font-size: 13px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.76);
}

.priority-panel-meta {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.62);
}

.watch-group-grid,
.trend-preview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.watch-group-card,
.trend-preview-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.025);
}

.watch-group-count {
  font-size: 12px;
  color: var(--color-text-sec);
}

.watch-group-list {
  display: grid;
  gap: 10px;
}

.watch-group-item {
  display: grid;
  gap: 2px;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.watch-group-item strong {
  color: #fff;
  font-size: 14px;
}

.watch-group-item span,
.watch-group-item em {
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-sec);
  font-style: normal;
}

.watch-candidate-panel,
.watch-candidate-detail-panel {
  display: grid;
  gap: 12px;
  margin-top: 16px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(126, 171, 255, 0.12);
  background:
    radial-gradient(circle at top right, rgba(86, 145, 255, 0.12), transparent 36%),
    rgba(255, 255, 255, 0.028);
}

.watch-candidate-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.watch-candidate-title {
  font-size: 15px;
  font-weight: 700;
  color: #fff;
}

.watch-candidate-desc,
.watch-candidate-summary {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.68);
}

.watch-candidate-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.watch-candidate-card {
  display: grid;
  gap: 8px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.watch-candidate-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.watch-candidate-card-top strong {
  display: block;
  font-size: 14px;
  color: #fff;
}

.watch-candidate-card-top span,
.watch-candidate-card-meta,
.watch-candidate-card-copy {
  font-size: 12px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.68);
}

.watch-candidate-card-top em {
  font-style: normal;
  font-size: 12px;
  font-weight: 700;
}

.signal-grid-candidate {
  margin-top: 0;
}

.signal-card-candidate {
  box-shadow: inset 0 0 0 1px rgba(126, 171, 255, 0.08);
}

.watch-candidate-more {
  display: flex;
  justify-content: center;
}

.stock-inline-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.buy-analysis-btn.el-button {
  --el-button-bg-color: rgba(58, 173, 255, 0.18);
  --el-button-border-color: rgba(88, 189, 255, 0.5);
  --el-button-text-color: #d8f1ff;
  --el-button-hover-bg-color: rgba(76, 188, 255, 0.28);
  --el-button-hover-border-color: rgba(120, 208, 255, 0.7);
  --el-button-hover-text-color: #f4fbff;
  --el-button-active-bg-color: rgba(48, 153, 226, 0.32);
  --el-button-active-border-color: rgba(110, 203, 255, 0.74);
  --el-button-active-text-color: #ffffff;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  box-shadow: inset 0 0 0 1px rgba(132, 217, 255, 0.12), 0 6px 16px rgba(31, 111, 176, 0.18);
  font-weight: 700;
  letter-spacing: 0.01em;
}

.buy-analysis-btn.el-button:hover,
.buy-analysis-btn.el-button:focus-visible {
  transform: translateY(-1px);
}

.sell-analysis-btn.el-button {
  --el-button-bg-color: rgba(255, 118, 102, 0.18);
  --el-button-border-color: rgba(255, 141, 126, 0.48);
  --el-button-text-color: #ffd9d2;
  --el-button-hover-bg-color: rgba(255, 128, 112, 0.28);
  --el-button-hover-border-color: rgba(255, 161, 148, 0.68);
  --el-button-hover-text-color: #fff3f0;
  --el-button-active-bg-color: rgba(230, 97, 82, 0.34);
  --el-button-active-border-color: rgba(255, 163, 148, 0.74);
  --el-button-active-text-color: #ffffff;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  box-shadow: inset 0 0 0 1px rgba(255, 172, 160, 0.12), 0 6px 16px rgba(140, 57, 46, 0.16);
  font-weight: 700;
  letter-spacing: 0.01em;
}

.sell-analysis-btn.el-button:hover,
.sell-analysis-btn.el-button:focus-visible {
  transform: translateY(-1px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.mode-switch {
  flex-shrink: 0;
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
  gap: 16px;
  margin-bottom: 24px;
  padding: 20px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(88, 176, 255, 0.12), transparent 34%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.04));
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.overview-mini-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.overview-mini-stat {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.38);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.overview-mini-stat-holding {
  box-shadow: inset 0 0 0 1px rgba(243, 157, 86, 0.12);
}

.overview-mini-stat-account {
  box-shadow: inset 0 0 0 1px rgba(47, 207, 154, 0.12);
}

.overview-mini-stat-trend {
  box-shadow: inset 0 0 0 1px rgba(198, 140, 255, 0.12);
}

.overview-mini-stat-market {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.12);
}

.overview-mini-stat-defense {
  box-shadow: inset 0 0 0 1px rgba(245, 204, 96, 0.12);
}

.overview-mini-label,
.overview-mini-tip {
  font-size: 12px;
  color: var(--color-text-sec);
}

.overview-mini-value {
  font-size: 1.35rem;
  line-height: 1;
}

.section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.section-title {
  font-size: 1rem;
  font-weight: 700;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.section-head-support {
  margin-bottom: 2px;
}

.decision-support-shell {
  display: grid;
  gap: 14px;
}

.focus-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(84, 210, 164, 0.08);
  border: 1px solid rgba(84, 210, 164, 0.16);
}

.focus-context-copy {
  font-size: 13px;
  color: var(--color-text-main);
}

.focus-context-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.decision-support-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.22fr) minmax(320px, 0.78fr);
  gap: 14px;
}

.support-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.support-card-focus,
.support-card-insight {
  align-content: start;
}

.support-card-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.top-focus-list {
  display: grid;
  gap: 12px;
}

.top-focus-item {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 12px;
  align-items: flex-start;
}

.top-focus-rank {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #f1606c, #ff8f72);
}

.top-focus-content {
  display: grid;
  gap: 10px;
}

.top-focus-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.top-focus-main,
.top-focus-trigger {
  display: grid;
  gap: 4px;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.top-focus-main {
  flex: 1;
}

.top-focus-main strong {
  font-size: 1.05rem;
  line-height: 1.35;
  color: #fff;
}

.top-focus-pool {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: #cfe3ff;
  background: rgba(95, 142, 255, 0.12);
  border: 1px solid rgba(126, 171, 255, 0.16);
}

.top-focus-meta,
.top-focus-trigger-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.top-focus-trigger-text {
  line-height: 1.55;
  color: var(--color-text-main);
}

.top-focus-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.focus-hit-inline {
  display: grid;
  gap: 10px;
}

.focus-hit-inline-title {
  font-size: 13px;
  font-weight: 700;
}

.focus-hit-inline-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.focus-hit-inline-item {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.focus-hit-inline-item span {
  font-size: 12px;
  color: var(--color-text-sec);
}

.focus-hit-inline-item strong {
  font-size: 1.15rem;
  line-height: 1;
}

.focus-hit-summary {
  line-height: 1.6;
  color: var(--color-text-main);
  font-size: 13px;
}

.review-compact {
  display: grid;
  gap: 10px;
}

.review-compact-row {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.review-compact-row-do {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.08);
}

.review-compact-row-watch {
  box-shadow: inset 0 0 0 1px rgba(255, 196, 64, 0.08);
}

.review-compact-row-avoid {
  box-shadow: inset 0 0 0 1px rgba(255, 120, 120, 0.08);
}

.review-compact-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.review-compact-text {
  line-height: 1.6;
  color: var(--color-text-main);
  font-size: 13px;
}

@media (max-width: 1200px) {
  .command-center,
  .watch-group-grid,
  .trend-preview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .summary-card-decision {
    grid-column: 1 / -1;
  }

  .direction-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .decision-support-grid,
  .focus-hit-inline-grid,
  .watch-candidate-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .ops-toolbar-main,
  .ops-toolbar-actions,
  .ops-toolbar-context {
    align-items: flex-start;
  }

  .command-center,
  .execution-dual-grid,
  .watch-group-grid,
  .trend-preview-grid,
  .decision-support-grid,
  .top-focus-item,
  .watch-candidate-grid {
    grid-template-columns: 1fr;
  }

  .overview-mini-stats,
  .direction-grid,
  .decision-summary-grid,
  .focus-hit-inline-grid {
    grid-template-columns: 1fr;
  }

  .direction-card-lead {
    grid-column: auto;
  }

  .top-focus-item {
    display: grid;
  }

  .top-focus-head,
  .top-focus-actions {
    justify-content: flex-start;
  }
}

.tab-count {
  font-style: normal;
  color: var(--color-text-sec);
}

.signal-grid {
  display: grid;
  gap: 16px;
  margin-top: 8px;
}

.account-group-stack {
  display: grid;
  gap: 20px;
  margin-top: 8px;
}

.account-group {
  display: grid;
  gap: 10px;
}

.account-group-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.account-group-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-main);
}

.account-group-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-sec);
}

.account-group-meta {
  font-size: 12px;
  color: var(--color-text-sec);
}

.signal-card {
  display: grid;
  gap: 16px;
  padding: 18px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.03));
}

.signal-card-market {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.08);
}

.signal-card-account {
  box-shadow: inset 0 0 0 1px rgba(47, 207, 154, 0.08);
}

.signal-card-trend {
  box-shadow: inset 0 0 0 1px rgba(198, 140, 255, 0.08);
}

.signal-card-holding {
  box-shadow: inset 0 0 0 1px rgba(243, 157, 86, 0.08);
}

.signal-card-focused {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.24);
  border-color: rgba(84, 210, 164, 0.26);
}

.signal-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.signal-stock {
  font-size: 1.55rem;
  font-weight: 800;
  line-height: 1.1;
}

.signal-code {
  font-size: 13px;
  color: var(--color-text-sec);
  letter-spacing: 0.04em;
}

.signal-badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.signal-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--color-text-sec);
  font-size: 13px;
}

.signal-meta span {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
}

.sample-role-line {
  font-size: 12px;
  color: var(--color-text-sec);
}

.signal-intent {
  padding: 18px 20px;
  border-radius: 20px;
  font-size: clamp(1rem, 1.4vw, 1.15rem);
  line-height: 1.65;
  font-weight: 700;
}

.signal-intent-market {
  color: #dbe9ff;
  background: rgba(76, 116, 211, 0.16);
  border: 1px solid rgba(103, 165, 255, 0.18);
}

.signal-intent-account {
  color: #dffdf1;
  background: rgba(30, 145, 103, 0.16);
  border: 1px solid rgba(47, 207, 154, 0.18);
}

.signal-intent-trend {
  color: #f0e6ff;
  background: rgba(156, 108, 245, 0.16);
  border: 1px solid rgba(198, 140, 255, 0.2);
}

.signal-intent-holding {
  color: #fff2df;
  background: rgba(204, 107, 40, 0.16);
  border: 1px solid rgba(243, 157, 86, 0.18);
}

.hard-filter-strip {
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-sec);
  background: rgba(255, 255, 255, 0.035);
  border: 1px dashed rgba(255, 255, 255, 0.08);
}

.execution-proximity-strip {
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 12px;
  line-height: 1.55;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.execution-proximity-strip-success {
  color: #dffdf1;
  background: rgba(30, 145, 103, 0.12);
}

.execution-proximity-strip-warning {
  color: #ffe5ba;
  background: rgba(214, 149, 45, 0.12);
}

.execution-proximity-strip-danger {
  color: #ffd5d5;
  background: rgba(191, 78, 78, 0.12);
}

.execution-proximity-strip-info {
  color: #dceeff;
  background: rgba(68, 116, 184, 0.12);
}

.hard-filter-warn {
  color: #f3c24d;
  background: rgba(243, 194, 77, 0.08);
  border-color: rgba(243, 194, 77, 0.2);
}

.profile-section,
.decision-section {
  display: grid;
  gap: 10px;
}

.profile-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.profile-tag {
  padding: 7px 11px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--color-text-main);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.decision-section {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.decision-card {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.decision-title {
  font-size: 12px;
  color: var(--color-text-sec);
}

.decision-copy {
  line-height: 1.65;
  color: var(--color-text-main);
}

.quote-strip,
.price-strip {
  display: grid;
  gap: 12px;
}

.quote-strip {
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  align-items: stretch;
}

.quote-main,
.quote-side,
.metric-card {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.quote-main {
  align-content: center;
}

.quote-label,
.metric-label {
  font-size: 12px;
  color: var(--color-text-sec);
}

.quote-price,
.metric-value {
  font-size: 1.15rem;
  font-weight: 700;
}

.quote-change {
  font-size: 14px;
  font-weight: 600;
}

.quote-source {
  font-size: 12px;
  color: var(--color-text-sec);
}

.quote-source-live {
  color: #54d2a4;
}

.quote-side {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.quote-pair {
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-sec);
}

.quote-pair strong {
  color: var(--color-text-main);
  font-size: 1rem;
}

.price-strip {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.condition-section {
  display: grid;
  gap: 12px;
}

.section-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-sec);
}

.condition-panel-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.condition-panel-grid-watch {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.condition-panel {
  display: grid;
  gap: 14px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.condition-panel-trigger {
  box-shadow: inset 0 0 0 1px rgba(90, 182, 146, 0.08);
}

.condition-panel-confirm {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.08);
}

.condition-panel-invalid {
  box-shadow: inset 0 0 0 1px rgba(255, 143, 114, 0.08);
}

.panel-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.panel-step {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-text-main);
  font-weight: 700;
}

.panel-title {
  font-weight: 700;
}

.panel-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-sec);
  line-height: 1.45;
}

.panel-body {
  color: var(--color-text-main);
  line-height: 1.7;
}

.condition-title {
  font-size: 0.98rem;
}

.signal-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--color-text-sec);
  font-size: 13px;
  line-height: 1.6;
}

.footer-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.footer-flag {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-text-main);
  white-space: nowrap;
}

.text-red {
  color: #ff7b86;
}

.text-green {
  color: #35c48b;
}

.text-neutral {
  color: var(--color-text-main);
}

.text-accent-success {
  color: #35c48b;
}

.text-accent-warning {
  color: #ffbf66;
}

.text-accent-danger {
  color: #ff8f97;
}

.text-accent-info {
  color: #7fb6ff;
}

@media (max-width: 1024px) {
  .action-card-top,
  .watch-group-head,
  .priority-panel-head,
  .signal-card-header,
  .signal-footer {
    flex-direction: column;
    align-items: flex-start;
  }

  .action-grid,
  .overview-stats,
  .price-strip,
  .condition-panel-grid,
  .condition-panel-grid-watch,
  .quote-side {
    grid-template-columns: 1fr;
  }

  .quote-strip,
  .top-focus-item {
    grid-template-columns: 1fr;
  }

  .top-focus-rank {
    display: none;
  }
}
</style>
