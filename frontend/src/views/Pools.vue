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
            <el-button @click="loadData({ refresh: true })" :loading="loading">刷新</el-button>
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
        <div class="decision-overview">
          <div v-if="focusSector" class="focus-context">
            <div class="focus-context-copy">
              当前按 <strong>{{ focusSector }}</strong> 方向查看三池，相关标的会优先排到前面。
            </div>
            <div class="focus-context-actions">
              <el-switch v-model="focusOnly" size="small" inline-prompt active-text="只看当前方向" inactive-text="全部" />
              <el-button link type="primary" size="small" @click="clearFocusSector">清除方向</el-button>
            </div>
          </div>
          <div class="overview-hero">
            <div class="overview-main">
              <div class="overview-badge" :class="overviewBadgeClass">
                {{ overviewBadge }}
              </div>
              <div class="overview-copy">
                <div class="overview-title">{{ overviewTitle }}</div>
                <div class="overview-desc">{{ overviewDesc }}</div>
              </div>
            </div>
            <aside class="overview-side">
              <div class="overview-side-head">
                <span class="section-kicker">快速判断</span>
                <span class="overview-side-caption">{{ compactRuleSummary }}</span>
              </div>
              <div class="overview-mini-stats">
                <div v-for="item in compactStatItems" :key="item.key" class="overview-mini-stat" :class="`overview-mini-stat-${item.key}`">
                  <span class="overview-mini-label">{{ item.label }}</span>
                  <strong class="overview-mini-value">{{ item.value }}</strong>
                  <span class="overview-mini-tip">{{ item.tip }}</span>
                </div>
              </div>
              <div class="overview-side-actions">
                <el-button v-if="focusSector" text @click="router.push('/sectors')">回板块扫描</el-button>
                <el-button text type="primary" @click="router.push({ path: '/buy-point', query: focusSector ? { focus_sector: focusSector } : {} })">
                  去买点分析
                </el-button>
              </div>
            </aside>
          </div>

          <div class="decision-rail">
            <div class="section-head">
              <div>
                <div class="section-kicker">今日流程</div>
                <div class="section-title">先按这个顺序处理三池</div>
              </div>
            </div>
            <div class="decision-rail-grid">
              <article
                v-for="step in decisionSteps"
                :key="step.key"
                class="decision-step-card"
                :class="[`decision-step-card-${step.tone}`, { 'decision-step-card-active': activeTab === step.tab }]"
              >
                <div class="decision-step-head">
                  <span class="decision-step-rank">{{ step.rank }}</span>
                  <div class="decision-step-copy">
                    <div class="decision-step-title">{{ step.title }}</div>
                    <div class="decision-step-desc">{{ step.desc }}</div>
                  </div>
                </div>
                <div class="decision-step-meta">
                  <span class="decision-step-chip">{{ step.countLabel }}</span>
                  <span class="decision-step-chip">{{ step.rule }}</span>
                </div>
                <div class="decision-step-actions">
                  <el-button size="small" @click="activeTab = step.tab">查看这一池</el-button>
                  <span class="decision-step-hint">{{ step.hint }}</span>
                </div>
              </article>
            </div>
          </div>
          <div v-if="topFocusItems.length || reviewInsight || focusSector" class="decision-support-grid">
            <section v-if="topFocusItems.length" class="support-card support-card-focus">
              <div class="support-card-head">
                <div>
                  <div class="section-kicker">优先名单</div>
                  <div class="section-title">今天先盯这些票</div>
                </div>
              </div>
              <div class="top-focus-list">
                <div v-for="item in topFocusItems" :key="`${item.poolKey}-${item.ts_code}`" class="top-focus-item">
                  <span class="top-focus-rank">{{ item.rank }}</span>
                  <div class="top-focus-main">
                    <strong>{{ item.orderLabel }}{{ item.stock_name }}</strong>
                    <span class="top-focus-meta">{{ item.meta }}</span>
                  </div>
                  <div class="top-focus-trigger">
                    <span class="top-focus-trigger-label">重点</span>
                    <span class="top-focus-trigger-text">{{ item.focus }}</span>
                  </div>
                </div>
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
                    <span>趋势池</span>
                    <strong>{{ focusMatches.trend }}</strong>
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
        </div>

        <el-tabs v-model="activeTab">
          <el-tab-pane name="market">
            <template #label>
              <span>市场最强观察池 <em class="tab-count">{{ marketCount }}</em></span>
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
                      综合分
                      <strong>{{ formatScore(stock.stock_score) }}</strong>
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
                    <div class="decision-title">未进其他池</div>
                    <div class="decision-copy">{{ notOtherPoolsLine(stock) }}</div>
                  </div>
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
                    <el-button type="primary" link size="small" @click="openCheckup(stock, '观察型')">全面体检</el-button>
                  </div>
                </div>
              </article>
            </div>
          </el-tab-pane>

          <el-tab-pane name="trend">
            <template #label>
              <span>趋势辨识度观察池 <em class="tab-count">{{ trendCount }}</em></span>
            </template>
            <el-empty v-if="!trendCount" :description="emptyPoolText('trend')" />
            <div v-else class="signal-grid">
              <article
                v-for="stock in trendPool"
                :key="stock.ts_code"
                :class="['signal-card', 'signal-card-trend', { 'signal-card-focused': matchesFocusSector(stock) }]"
              >
                <div class="signal-card-header">
                  <div>
                    <div class="signal-stock">{{ stock.stock_name }}</div>
                    <div class="signal-code">{{ stock.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag v-if="stock.representative_role_tag" size="small" type="danger">
                      {{ stock.representative_role_tag }}
                    </el-tag>
                    <el-tag size="small" type="warning">{{ stock.structure_state_tag || '结构观察' }}</el-tag>
                    <el-tooltip v-if="stock.review_bias_label" :content="stock.review_bias_reason || stock.review_bias_label" placement="top">
                      <el-tag size="small" :type="reviewBiasTagType(stock.review_bias_label)">
                        {{ stock.review_bias_label }}
                      </el-tag>
                    </el-tooltip>
                    <el-tag size="small" type="info">{{ stock.stock_role_tag || stock.stock_core_tag }}</el-tag>
                  </div>
                </div>

                <div class="signal-meta">
                  <span>{{ stock.sector_name || '无板块信息' }}</span>
                  <span>{{ stock.candidate_source_tag || '无来源标记' }}</span>
                </div>
                <div v-if="stock.representative_role_tag" class="sample-role-line">
                  {{ representativeRoleLine(stock) }}
                </div>

                <div class="signal-intent signal-intent-trend">
                  {{ trendActionLine(stock) }}
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
                      执行分
                      <strong>{{ formatScore(stock.account_entry_score) }}</strong>
                    </span>
                    <span class="quote-pair">
                      综合分
                      <strong>{{ formatScore(stock.stock_score) }}</strong>
                    </span>
                  </div>
                </div>

                <div class="price-strip">
                  <div class="metric-card">
                    <span class="metric-label">结构</span>
                    <strong class="metric-value">{{ stock.structure_state_tag }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">次日交易性</span>
                    <strong class="metric-value">{{ stock.next_tradeability_tag }}</strong>
                  </div>
                  <div class="metric-card">
                    <span class="metric-label">连续性</span>
                    <strong class="metric-value">{{ stock.stock_continuity_tag }}</strong>
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
                    <div class="decision-title">为什么值得长期盯</div>
                    <div class="decision-copy">{{ stock.why_this_pool || stock.pool_decision_summary || '结构更耐打，适合持续跟踪。' }}</div>
                  </div>
                  <div class="decision-card">
                    <div class="decision-title">为什么不是别的池</div>
                    <div class="decision-copy">{{ notOtherPoolsLine(stock) }}</div>
                  </div>
                </div>

                <div class="condition-section">
                  <div class="section-kicker">趋势清单</div>
                  <div class="condition-panel-grid condition-panel-grid-watch">
                    <section class="condition-panel condition-panel-trigger">
                      <div class="panel-head">
                        <span class="panel-step">1</span>
                        <div>
                          <div class="panel-title">盯结构</div>
                          <div class="panel-subtitle">看承接、趋势和分歧修复</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.pool_decision_summary || stock.stock_comment || '重点看趋势是否继续保持清晰。' }}</div>
                      </div>
                    </section>

                    <section class="condition-panel condition-panel-invalid">
                      <div class="panel-head">
                        <span class="panel-step">2</span>
                        <div>
                          <div class="panel-title">失效点</div>
                          <div class="panel-subtitle">结构破坏就不再当趋势锚</div>
                        </div>
                      </div>
                      <div class="panel-body">
                        <div class="condition-title">{{ stock.llm_risk_note || stock.stock_falsification_cond || '承接转弱或关键位失守时降级。' }}</div>
                      </div>
                    </section>
                  </div>
                </div>

                <div class="signal-footer">
                  <span>{{ trendFooterLine(stock) }}</span>
                  <div class="footer-actions">
                    <span class="footer-flag">看结构，不急着追</span>
                    <el-button type="primary" link size="small" @click="openCheckup(stock, '观察型')">全面体检</el-button>
                  </div>
                </div>
              </article>
            </div>
          </el-tab-pane>

          <el-tab-pane name="account">
            <template #label>
              <span>账户可参与池 <em class="tab-count">{{ accountCount }}</em></span>
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
                        <el-tag v-if="stock.representative_role_tag" size="small" type="danger">
                          {{ stock.representative_role_tag }}
                        </el-tag>
                        <el-tooltip v-if="stock.review_bias_label" :content="stock.review_bias_reason || stock.review_bias_label" placement="top">
                          <el-tag size="small" :type="reviewBiasTagType(stock.review_bias_label)">
                            {{ stock.review_bias_label }}
                          </el-tag>
                        </el-tooltip>
                        <el-tag size="small" :type="accountEntryTagType(stock)">{{ accountEntryTag(stock) }}</el-tag>
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
                          执行分
                          <strong>{{ formatScore(stock.account_entry_score) }}</strong>
                        </span>
                        <span class="quote-pair">
                          综合分
                          <strong>{{ formatScore(stock.stock_score) }}</strong>
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
                            <div class="condition-title">{{ stock.llm_risk_note || stock.position_hint || '按计划仓位执行，不要超配。' }}</div>
                          </div>
                        </section>
                      </div>
                    </div>

                    <div class="signal-footer">
                      <span>{{ stock.stock_comment || '可参与不代表立刻追价，仍要等买点页确认。' }}</span>
                      <div class="footer-actions">
                        <span class="footer-flag">{{ accountFooterFlag(stock) }}</span>
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
              <span>持仓处理池 <em class="tab-count">{{ holdingCount }}</em></span>
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
                    <el-button type="primary" link size="small" @click="openCheckup(stock, '持仓型')">全面体检</el-button>
                  </div>
                </div>
              </article>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-card>
    <StockCheckupDrawer
      v-model="checkupVisible"
      :ts-code="checkupStock.tsCode"
      :stock-name="checkupStock.stockName"
      :default-target="checkupStock.defaultTarget"
      :trade-date="displayDate"
    />
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { stockApi, decisionApi } from '../api'
import { ElMessage } from 'element-plus'
import StockCheckupDrawer from '../components/StockCheckupDrawer.vue'

const loading = ref(false)
const activeTab = ref('holding')
const displayDate = ref('')
const poolsData = ref({
  market_watch_pool: [],
  trend_recognition_pool: [],
  account_executable_pool: [],
  holding_process_pool: [],
  resolved_trade_date: '',
  sector_scan_trade_date: '',
  sector_scan_resolved_trade_date: '',
})
const checkupVisible = ref(false)
const checkupStock = ref({ tsCode: '', stockName: '', defaultTarget: '观察型' })
const reviewStatsData = ref(null)
const loadError = ref('')
const POOLS_TIMEOUT = 90000
const REVIEW_STATS_TIMEOUT = 90000
const route = useRoute()
const router = useRouter()
const focusOnly = ref(false)

const focusSector = computed(() => String(route.query.focus_sector || '').trim())

const marketCount = computed(() => poolsData.value.market_watch_pool?.length || 0)
const trendCount = computed(() => poolsData.value.trend_recognition_pool?.length || 0)
const accountCount = computed(() => poolsData.value.account_executable_pool?.length || 0)
const holdingCount = computed(() => poolsData.value.holding_process_pool?.length || 0)

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

const marketPool = computed(() => sortByFocusSector(poolsData.value.market_watch_pool || []))
const trendPool = computed(() => sortByFocusSector(poolsData.value.trend_recognition_pool || []))
const accountPool = computed(() => sortByFocusSector(poolsData.value.account_executable_pool || []))
const focusMatches = computed(() => ({
  market: (poolsData.value.market_watch_pool || []).filter((stock) => matchesFocusSector(stock)).length,
  trend: (poolsData.value.trend_recognition_pool || []).filter((stock) => matchesFocusSector(stock)).length,
  account: (poolsData.value.account_executable_pool || []).filter((stock) => matchesFocusSector(stock)).length,
}))
const accountEmptyReason = computed(() => {
  if (accountCount.value) return ''

  const rawReasons = [...marketPool.value, ...trendPool.value]
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

const isComfortableAccountEntry = (stock) => ['回踩确认', '低吸预备'].includes(stock.next_tradeability_tag)
const accountPoolGroups = computed(() => {
  const comfortable = accountPool.value.filter((stock) => isComfortableAccountEntry(stock))
  const breakthrough = accountPool.value.filter((stock) => stock.next_tradeability_tag === '突破确认')
  const other = accountPool.value.filter(
    (stock) => !isComfortableAccountEntry(stock) && stock.next_tradeability_tag !== '突破确认'
  )

  return [
    {
      key: 'comfortable',
      title: '回踩 / 低吸可参与',
      desc: '更偏舒服买点，优先看承接和确认，不急着追。',
      items: comfortable,
    },
    {
      key: 'breakthrough',
      title: '突破确认可参与',
      desc: '更偏强势跟随，重点看放量过位和站稳，不做盲追。',
      items: breakthrough,
    },
    {
      key: 'other',
      title: '其他可参与',
      desc: '账户允许参与，但需要你回到买点页结合盘中再细看。',
      items: other,
    },
  ].filter((group) => group.items.length)
})
const holdingPool = computed(() =>
  [...(poolsData.value.holding_process_pool || [])].sort(compareHoldingPriority)
)

const reviewSnapshotTypeLabel = (value) => {
  if (value === 'buy_available') return '可买'
  if (value === 'buy_observe') return '观察'
  if (value === 'pool_account') return '可参与池'
  if (value === 'pool_market') return '观察池'
  return value || '-'
}

const reviewRowLabel = (row) => `${reviewSnapshotTypeLabel(row.snapshot_type)} / ${row.candidate_bucket_tag || '未分层'}`

const reviewActionableRows = computed(() => (
  (reviewStatsData.value?.bucket_stats || [])
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

const overviewBadge = computed(() => {
  if (holdingCount.value) return '先处理持仓'
  if (accountCount.value) return '看可参与'
  if (trendCount.value) return '先看趋势锚'
  return '先看观察池'
})

const overviewBadgeClass = computed(() => {
  if (holdingCount.value) return 'badge-holding'
  if (accountCount.value) return 'badge-account'
  if (trendCount.value) return 'badge-trend'
  return 'badge-market'
})

const overviewTitle = computed(() => {
  if (holdingCount.value) return '已有仓位优先，先把该卖、该减、该持有的动作排清楚'
  if (accountCount.value) return '当前有能执行的新标的，先看账户可参与池，再回到买点页确认'
  if (trendCount.value) return '今天更值得盯结构清晰的趋势锚，不必只追最热那一笔'
  if (marketCount.value) return '当前更适合先观察市场最强结构，不要把观察票当成执行票'
  return '今天几类观察池都比较清淡，先等新的结构和账户信号'
})

const overviewDesc = computed(() => {
  if (holdingCount.value) return '持仓处理池是今天优先级最高的区域；先处理旧仓风险，再决定是否看新票。'
  if (accountCount.value) return '账户可参与池说明系统已经过了账户准入这一步，但真正执行仍要结合买点和盘中确认。'
  if (trendCount.value) return '趋势辨识度池更关注结构、承接和连续性，适合盯真正能当锚的票。'
  if (marketCount.value) return '观察池的任务是帮你缩小盯盘范围，先看方向、板块和量能，不要直接下单。'
  return '当前没有明显需要处理的仓位，也没有通过准入的新标的，适合保持节奏。'
})

const overviewRules = computed(() => {
  if (holdingCount.value) {
    return ['先处理旧仓，再考虑新开仓', '动作建议优先看高优先级', '证伪条件到了就不要拖']
  }
  if (accountCount.value) {
    return ['先看进池理由', '仓位提示比题材更重要', '可参与不等于立刻追价']
  }
  if (trendCount.value) {
    return ['看谁最耐打，不看谁最响', '趋势锚优先盯承接和修复', '结构清晰比日内最强更重要']
  }
  return ['观察池只负责缩小盯盘范围', '先看最强结构，再看账户是否允许', '没有执行确认就不要急着动']
})

const compactRuleSummary = computed(() => overviewRules.value.slice(0, 2).join(' · '))

const compactStatItems = computed(() => [
  { key: 'holding', label: '持仓处理', value: holdingCount.value, tip: '先清旧仓动作' },
  { key: 'account', label: '账户可参与', value: accountCount.value, tip: '能做但仍要确认' },
  { key: 'trend', label: '趋势辨识', value: trendCount.value, tip: '看结构锚' },
  { key: 'market', label: '市场观察', value: marketCount.value, tip: '看方向样本' },
])

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
      rule: '能做但别急追',
      hint: '先看进池理由和仓位提示',
    })
  } else if (trendCount.value) {
    steps.push({
      key: 'trend',
      rank: steps.length + 1,
      tab: 'trend',
      tone: 'trend',
      title: '先盯趋势锚',
      desc: '今天暂无直接可执行票，先看结构最耐打的趋势锚，不要急着抬手。',
      countLabel: `${trendCount.value} 只趋势锚`,
      rule: '盯结构',
      hint: '重点看承接、修复和连续性',
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

const focusSummary = computed(() => {
  if (!focusSector.value) return ''
  if (focusMatches.value.account) {
    return `${focusSector.value} 已经有 ${focusMatches.value.account} 只进入账户可参与池，可以先看账户池，再去买点页确认。`
  }
  if (focusMatches.value.trend) {
    return `${focusSector.value} 还没走到可执行，但已经有 ${focusMatches.value.trend} 只在趋势池里，可以先盯结构，不要急着下手。`
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
      ts_code: stock.ts_code,
      stock_name: stock.stock_name,
      focus: stock.sell_trigger_cond || stock.sell_reason || stock.sell_comment || '继续跟踪盘中变化',
      meta: `${stock.sell_signal_tag || '观察'} / ${stock.sell_priority || '低'}优先 / ${formatSignedPct(stock.pnl_pct)}`,
      orderLabel: holdingOrderLabel(items.length),
    })
  })

  if (accountPool.value.length) {
    const stock = accountPool.value[0]
    items.push({
      poolKey: 'account',
      ts_code: stock.ts_code,
      stock_name: stock.stock_name,
      focus: stock.pool_entry_reason || stock.position_hint || stock.stock_comment || '等待买点确认',
      meta: `可参与 / ${stock.candidate_bucket_tag || '未分层'} / ${formatSignedPct(stock.change_pct)}`,
      orderLabel: items.length ? '再看 ' : '先看 ',
    })
  } else if (trendPool.value.length) {
    const stock = trendPool.value[0]
    items.push({
      poolKey: 'trend',
      ts_code: stock.ts_code,
      stock_name: stock.stock_name,
      focus: stock.why_this_pool || stock.pool_decision_summary || stock.stock_comment || '先盯结构与承接',
      meta: `趋势池 / ${stock.structure_state_tag || '结构'} / ${formatSignedPct(stock.change_pct)}`,
      orderLabel: items.length ? '再盯 ' : '先盯 ',
    })
  } else if (marketPool.value.length) {
    const stock = marketPool.value[0]
    items.push({
      poolKey: 'market',
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
  if (quoteTime) return `${label} ${quoteTime.slice(11, 19)}`
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
  if ((stock.pool_entry_reason || '').includes('防守')) return '防守试错'
  return '满足准入'
}

const accountEntryTagType = (stock) => {
  if ((stock.pool_entry_reason || '').includes('防守')) return 'warning'
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

const emptyPoolText = (poolKey) => {
  if (poolKey === 'account') {
    return accountEmptyReason.value
  }
  if (poolKey === 'trend') {
    return '暂无结构清晰、值得持续盯的趋势锚。'
  }
  return '暂无需要观察的强势候选'
}

const marketActionLine = (stock) => stock.stock_comment || '先观察这只票是否继续保持强势结构。'
const marketFooterLine = (stock) => `${stock.stock_strength_tag || '中'}强度，${stock.stock_continuity_tag || '可观察'}，继续等确认。`
const trendActionLine = (stock) => stock.why_this_pool || '这只票更适合盯结构和承接，不急着看日内最炸。'
const trendFooterLine = (stock) => `${stock.structure_state_tag || '结构'} / ${stock.next_tradeability_tag || '待确认'}，更适合做趋势锚。`
const accountActionLine = (stock) => stock.pool_entry_reason || stock.stock_comment || '这只票已通过账户准入，但仍要等买点确认。'
const accountFooterFlag = (stock) => ((stock.pool_entry_reason || '').includes('防守') ? '轻仓试错' : '等待买点页确认')
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

const openCheckup = (stock, defaultTarget = '观察型') => {
  checkupStock.value = {
    tsCode: stock.ts_code,
    stockName: stock.stock_name || stock.ts_code,
    defaultTarget
  }
  checkupVisible.value = true
}

const clearFocusSector = () => {
  const query = { ...route.query }
  delete query.focus_sector
  router.replace({ query })
}

const loadData = async (options = {}) => {
  loading.value = true
  try {
    const tradeDate = getLocalDate()
    displayDate.value = tradeDate
    loadError.value = ''
    const res = await stockApi.pools(tradeDate, 50, { ...options, timeout: POOLS_TIMEOUT })
    const payload = res.data.data || {
      market_watch_pool: [],
      trend_recognition_pool: [],
      account_executable_pool: [],
      holding_process_pool: [],
      resolved_trade_date: '',
      sector_scan_trade_date: '',
      sector_scan_resolved_trade_date: '',
    }
    poolsData.value = payload
    if (holdingCount.value) activeTab.value = 'holding'
    else if (accountCount.value) activeTab.value = 'account'
    else if (trendCount.value) activeTab.value = 'trend'
    else activeTab.value = 'market'
    if (options.refresh) {
      if (payload.refresh_requested) {
        ElMessage.success('已触发后台刷新，当前先展示已有三池结果。')
      } else if (payload.refresh_in_progress) {
        ElMessage.info('三池后台刷新仍在进行中，当前先展示已有结果。')
      }
    }
  } catch (error) {
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
</script>

<style scoped>
.pools-view {
  min-height: 100%;
}

.page-alert {
  margin-bottom: 16px;
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
  gap: 10px;
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
  gap: 16px;
  margin-bottom: 24px;
  padding: 20px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(88, 176, 255, 0.12), transparent 34%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.04));
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.overview-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.95fr);
  gap: 14px;
  align-items: stretch;
}

.overview-main {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.overview-side {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.overview-side-head {
  display: grid;
  gap: 6px;
}

.overview-side-caption {
  font-size: 12px;
  color: var(--color-text-sec);
  line-height: 1.5;
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

.overview-mini-label,
.overview-mini-tip {
  font-size: 12px;
  color: var(--color-text-sec);
}

.overview-mini-value {
  font-size: 1.35rem;
  line-height: 1;
}

.overview-side-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
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

.decision-rail {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.decision-rail-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.decision-step-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.decision-step-card-active {
  box-shadow: inset 0 0 0 1px rgba(104, 158, 255, 0.22);
}

.decision-step-card-holding {
  box-shadow: inset 0 0 0 1px rgba(243, 157, 86, 0.12);
}

.decision-step-card-account {
  box-shadow: inset 0 0 0 1px rgba(47, 207, 154, 0.12);
}

.decision-step-card-trend {
  box-shadow: inset 0 0 0 1px rgba(198, 140, 255, 0.12);
}

.decision-step-card-market {
  box-shadow: inset 0 0 0 1px rgba(103, 165, 255, 0.12);
}

.decision-step-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.decision-step-rank {
  width: 30px;
  height: 30px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #f1606c, #ff8f72);
}

.decision-step-copy {
  display: grid;
  gap: 4px;
}

.decision-step-title {
  font-size: 15px;
  font-weight: 700;
}

.decision-step-desc {
  line-height: 1.55;
  color: var(--color-text-sec);
  font-size: 13px;
}

.decision-step-meta,
.decision-step-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.decision-step-chip {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--color-text-main);
  background: rgba(255, 255, 255, 0.05);
}

.decision-step-hint {
  font-size: 12px;
  color: var(--color-text-sec);
}

.overview-badge {
  min-width: 124px;
  padding: 16px 18px;
  border-radius: 18px;
  font-size: 1.1rem;
  font-weight: 800;
  text-align: center;
  letter-spacing: 0.05em;
  color: #fff;
}

.badge-holding {
  background: linear-gradient(135deg, #cc6b28, #f39d56);
}

.badge-account {
  background: linear-gradient(135deg, #1d8b6f, #2fcf9a);
}

.badge-trend {
  background: linear-gradient(135deg, #9c6cf5, #c68cff);
}

.badge-market {
  background: linear-gradient(135deg, #4f76d9, #67a5ff);
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
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
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

.support-card-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.top-focus-list {
  display: grid;
  gap: 8px;
}

.top-focus-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) minmax(240px, 1fr);
  gap: 12px;
  align-items: stretch;
}

.top-focus-rank {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #f1606c, #ff8f72);
}

.top-focus-main,
.top-focus-trigger {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
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
  .overview-hero,
  .decision-support-grid,
  .decision-rail-grid,
  .focus-hit-inline-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .overview-hero,
  .decision-support-grid,
  .overview-main,
  .top-focus-item {
    grid-template-columns: 1fr;
  }

  .overview-main {
    flex-direction: column;
    align-items: flex-start;
  }

  .overview-mini-stats,
  .decision-rail-grid,
  .focus-hit-inline-grid {
    grid-template-columns: 1fr;
  }

  .top-focus-item {
    display: grid;
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

@media (max-width: 1024px) {
  .overview-main,
  .signal-card-header,
  .signal-footer {
    flex-direction: column;
    align-items: flex-start;
  }

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
