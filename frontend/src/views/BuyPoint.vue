<template>
  <div class="buy-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="card-header-title">
            <span>买点分析</span>
            <span v-if="displayDate" class="header-date">{{ displayDate }}</span>
          </div>
          <div class="header-actions">
            <div class="style-switch-wrap">
              <span class="style-switch-label">候选风格</span>
              <el-radio-group v-model="strategyStyle" size="small" class="style-switch">
                <el-radio-button label="balanced">均衡</el-radio-button>
                <el-radio-button label="left">偏左侧</el-radio-button>
                <el-radio-button label="right">偏右侧</el-radio-button>
              </el-radio-group>
            </div>
            <el-button @click="loadData({ refresh: true })" :loading="loading">刷新</el-button>
          </div>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="8" animated />
      <template v-else>
        <div v-if="loadError" class="load-error">
          {{ loadError }}
        </div>
        <DataFreshnessBar
          :items="buyFreshnessItems"
          :note="buyFreshnessNote"
        />
        <div v-if="buyData.market_env_tag" class="decision-overview">
          <div v-if="reviewSourceFilter || reviewBucketFilter" class="focus-context focus-context-review">
            <div class="focus-context-copy">
              当前从复盘统计跳转而来，
              <template v-if="reviewSourceFilter">默认定位到 <strong>{{ reviewSourceLabel }}</strong>；</template>
              <template v-if="activeBucketFilter">当前优先查看 <strong>{{ activeBucketFilter }}</strong> 结构。</template>
              执行时仍先按 <strong>可买 / 观察</strong> 阶段，再在同阶段内按结构排序。
            </div>
            <div class="focus-context-actions">
              <el-button v-if="activeBucketFilter" link type="primary" size="small" @click="clearBucketFilter">看全部结构</el-button>
              <el-button link type="primary" size="small" @click="clearReviewFilter">清除筛选</el-button>
            </div>
          </div>
          <div v-if="focusSector" class="focus-context">
            <div class="focus-context-copy">
              当前按 <strong>{{ focusSectorLabel }}</strong><strong>{{ focusSector }}</strong> 方向查看买点，相关机会会优先排到前面。
            </div>
            <div class="focus-context-actions">
              <el-switch v-model="focusOnly" size="small" inline-prompt active-text="只看当前方向" inactive-text="全部" />
              <el-button link type="primary" size="small" @click="clearFocusSector">清除方向</el-button>
            </div>
          </div>
          <div class="overview-main">
            <div class="market-mode-chip" :class="envChipClass(displayEnvProfile)">
              {{ displayEnvProfile }}
            </div>
            <div class="overview-copy">
              <div class="overview-title">{{ envHeadline(displayEnvProfile) }}</div>
              <div class="overview-desc">{{ envGuidance(displayEnvProfile) }}</div>
            </div>
          </div>
          <div v-if="buyDirectionItems.length" class="overview-rules overview-rules-direction">
            <div v-for="item in buyDirectionItems" :key="`${item.label}-${item.name}`" class="rule-chip">
              {{ item.label }} {{ item.name }}
            </div>
          </div>

            <div class="overview-stats">
              <div class="stat-card stat-buy">
              <span class="stat-label">主执行</span>
              <strong class="stat-value">{{ primaryAvailablePoints.length }}</strong>
              <span class="stat-tip">今天优先盯这几只</span>
              </div>
              <div class="stat-card stat-watch">
              <span class="stat-label">备选可买</span>
              <strong class="stat-value">{{ backupAvailablePoints.length }}</strong>
              <span class="stat-tip">有空位再看</span>
              </div>
              <div class="stat-card stat-skip">
              <span class="stat-label">不买</span>
              <strong class="stat-value">{{ notBuyPoints.length }}</strong>
              <span class="stat-tip">今天先放弃</span>
            </div>
          </div>

          <div class="overview-rules">
            <div v-for="rule in envChecklist(displayEnvProfile)" :key="rule" class="rule-chip">
              {{ rule }}
            </div>
          </div>
          <div v-if="reviewInsight" class="review-bridge">
            <div class="review-bridge-head">
              <div>
                <div class="review-bridge-title">复盘怎么影响今天买点选择</div>
                <div class="review-bridge-subtitle">{{ reviewInsight.summary }}</div>
              </div>
              <div class="review-bridge-summary-chip">复盘只调优先级，不替代触发确认</div>
            </div>
            <div class="review-bridge-grid">
              <div
                v-for="card in reviewInsight.cards"
                :key="card.label"
                :class="['review-bridge-card', card.cardClass]"
              >
                <div class="review-bridge-card-head">
                  <div class="review-bridge-label">{{ card.label }}</div>
                  <div class="review-bridge-metric">{{ card.metric }}</div>
                </div>
                <div class="review-bridge-card-title">{{ card.title }}</div>
                <div class="review-bridge-card-action">{{ card.action }}</div>
                <div class="review-bridge-card-note">{{ card.note }}</div>
              </div>
            </div>
          </div>

          <div v-if="structureBucketOptions.length" class="bucket-filter">
            <div class="bucket-filter-head">
              <div>
                <div class="bucket-filter-title">结构标签筛选</div>
                <div class="bucket-filter-desc">先按执行阶段看，再在当前阶段里切结构标签；复盘不会把观察票直接抬到可买票前面。</div>
              </div>
              <div class="bucket-filter-summary">当前：{{ activeBucketFilter || '全部结构' }}</div>
            </div>
            <div class="bucket-filter-chip-row">
              <button
                type="button"
                :class="['bucket-filter-chip', { 'bucket-filter-chip-active': !activeBucketFilter }]"
                @click="clearBucketFilter"
              >
                全部结构 {{ structureFilterBaseCount }}
              </button>
              <button
                v-for="item in structureBucketOptions"
                :key="item.label"
                type="button"
                :class="['bucket-filter-chip', { 'bucket-filter-chip-active': activeBucketFilter === item.label }]"
                @click="setBucketFilter(item.label)"
              >
                {{ item.label }} {{ item.count }}
              </button>
            </div>
          </div>
        </div>

        <el-tabs v-model="activeTab">
          <el-tab-pane name="available">
            <template #label>
              <span>可买 <em class="tab-count">{{ primaryAvailablePoints.length }}/{{ availablePoints.length }}</em></span>
            </template>
            <section v-if="!availablePoints.length" class="no-trade-state">
              <div class="no-trade-kicker">今日不开新仓</div>
              <div class="no-trade-title">
                {{ buyData.market_env_tag === '防守' ? '当前是防守环境，先处理旧仓和风险。' : displayEnvProfile === '弱中性' ? '当前环境偏弱，没有足够舒服的开仓条件。' : '当前没有满足执行条件的开仓标的。' }}
              </div>
              <div class="no-trade-copy">{{ buyFreshnessNote }}</div>
              <div class="no-trade-actions">
                <el-button type="primary" plain @click="router.push('/sell')">先看卖点分析</el-button>
                <el-button plain @click="goToPoolsPage()">回三池分类</el-button>
                <el-button plain @click="router.push('/review')">看复盘证据</el-button>
              </div>
            </section>
            <template v-else>
              <div class="available-group-head">
                <div>
                  <div class="available-group-title">主执行名单</div>
                  <div class="available-group-desc">
                    按市场环境、板块分散和买法拥挤度压缩后，默认只保留最该下手的 {{ primaryAvailablePoints.length }} 只。
                  </div>
                </div>
                <div class="available-group-meta">总可买 {{ availablePoints.length }} 只</div>
              </div>
              <div class="type-group-stack">
                <section
                  v-for="group in primaryAvailableGroups"
                  :key="`primary-${group.key}`"
                  class="type-group"
                >
                  <div class="type-group-head">
                    <div>
                      <div class="type-group-title">{{ group.title }}</div>
                      <div class="type-group-desc">{{ group.desc }}</div>
                    </div>
                    <div class="type-group-meta">{{ group.items.length }} 只</div>
                  </div>
                  <div class="signal-grid">
		              <article
		                v-for="point in group.items"
		                :key="point.ts_code"
		                :class="['signal-card', 'signal-card-buy', entryModeCardClass(point), { 'signal-card-focused': matchesFocusSector(point), 'signal-card-review-focused': matchesReviewFocus(point, 'buy_available') }]"
	              >
                <div class="signal-card-header">
                  <div class="signal-title-wrap">
                    <div class="signal-stock">{{ point.stock_name }}</div>
                    <div class="signal-code">{{ point.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" type="primary">{{ point.buy_display_type || point.buy_point_type }}</el-tag>
                    <el-tag v-if="point.buy_execution_context" size="small" type="info">{{ point.buy_execution_context }}</el-tag>
                    <el-tag v-if="isInvalidationWatchActive(point)" size="small" type="danger">失效观察期</el-tag>
                    <el-tag v-if="entryModeBadgeLabel(point)" size="small" :type="entryModeBadgeType(point)">{{ entryModeBadgeLabel(point) }}</el-tag>
                    <el-tag size="small" :type="riskTagType(point.buy_risk_level)">{{ point.buy_risk_level }}风险</el-tag>
                    <el-tag size="small" :type="accountFitType(point.buy_account_fit)">{{ point.buy_account_fit }}</el-tag>
	                    <el-tooltip v-if="point.review_bias_label" :content="point.review_bias_reason || point.review_bias_label" placement="top">
                      <el-tag size="small" :type="reviewBiasTagType(point.review_bias_label)">
                        {{ point.review_bias_label }}
                      </el-tag>
                    </el-tooltip>
                  </div>
                </div>

	                <div class="signal-meta">
	                  <span v-if="directionMatchLabel(point)">{{ directionMatchLabel(point) }}</span>
	                  <span>{{ poolContextLabel(point) }}</span>
	                  <span v-if="point.execution_proximity_tag" :class="['signal-meta-chip', executionProximityMetaClass(point)]">
	                    {{ point.execution_proximity_tag }}
	                  </span>
	                  <span>{{ point.candidate_bucket_tag || '未分层' }}</span>
	                  <span>{{ point.candidate_source_tag || '无来源标记' }}</span>
	                </div>

                <div class="signal-intent">
                  {{ primaryActionLine(point, displayEnvProfile) }}
                </div>
	                <div v-if="isInvalidationWatchActive(point)" class="signal-watch-alert">
                    <div class="signal-watch-alert-title">已跌破失效价，先看能否拉回</div>
                    <div class="signal-watch-alert-copy">{{ invalidationWatchLine(point) }}</div>
                  </div>
	                <div v-if="buySizingLine(point)" :class="['signal-sizing', entryModeSizingClass(point)]">
	                  {{ buySizingLine(point) }}
	                </div>
                <div class="hard-filter-strip" :class="{ 'hard-filter-warn': (point.hard_filter_failed_count || 0) > 0 }">
                  {{ hardFilterLine(point) }}
                </div>

                <div class="quote-strip">
                  <div class="quote-main">
                    <span class="quote-label">最新价</span>
                    <strong class="quote-price">{{ formatPrice(point.buy_current_price) }}</strong>
                    <span :class="['quote-change', priceClass(point.buy_current_change_pct)]">
                      {{ formatSignedPct(point.buy_current_change_pct) }}
                    </span>
                    <span class="quote-source" :class="{ 'quote-source-live': isRealtimeSource(point.buy_data_source) }">
                      {{ quoteMetaLine(point.buy_data_source, point.buy_quote_time, displayDate) }}
                    </span>
                  </div>
                  <div class="quote-side">
                    <span class="quote-pair">
                      {{ executionGapLabel(point) }}
                      <strong :class="priceClass(executionGapValue(point))">{{ formatGap(executionGapValue(point)) }}</strong>
                    </span>
                    <span class="quote-pair">
                      距失效
                      <strong :class="invalidGapClass(point.buy_invalid_gap_pct)">{{ formatGap(point.buy_invalid_gap_pct) }}</strong>
                    </span>
                  </div>
                </div>

	                  <div class="price-strip">
	                  <div class="metric-card">
	                    <span class="metric-label">{{ executionReferenceLabel(point) }}</span>
	                    <strong class="metric-value">{{ formatPrice(executionReferencePrice(point)) }}</strong>
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
	                  <div
	                    v-if="!isCardExpanded(cardKey(point, 'available'))"
	                    class="condition-summary-grid"
	                  >
	                    <section class="condition-summary-card condition-summary-trigger">
	                      <div class="summary-card-head">
	                        <span class="panel-step">1</span>
	                        <div class="summary-card-copy">
	                          <div class="panel-title">触发</div>
	                          <div class="panel-subtitle">先到这个位置再开始盯盘</div>
	                        </div>
	                      </div>
	                      <div class="summary-card-body">{{ point.buy_trigger_cond }}</div>
	                    </section>

	                    <section class="condition-summary-card condition-summary-confirm">
	                      <div class="summary-card-head">
	                        <span class="panel-step">2</span>
	                        <div class="summary-card-copy">
	                          <div class="panel-title">确认</div>
	                          <div class="panel-subtitle">条件没到齐，不算信号成立</div>
	                        </div>
	                        <span class="summary-count">{{ splitCond(point.buy_confirm_cond).length }}条</span>
	                      </div>
	                      <div class="summary-card-body">{{ summarizeCond(point.buy_confirm_cond) }}</div>
	                    </section>

	                    <section class="condition-summary-card condition-summary-invalid">
	                      <div class="summary-card-head">
	                        <span class="panel-step">3</span>
	                        <div class="summary-card-copy">
	                          <div class="panel-title">失效</div>
	                          <div class="panel-subtitle">先记住最先认错的位置</div>
	                        </div>
	                        <span class="summary-count">{{ splitCond(point.buy_invalid_cond).length }}条</span>
	                      </div>
	                      <div class="summary-card-body">{{ summarizeCond(point.buy_invalid_cond) }}</div>
	                    </section>
	                  </div>

	                  <div class="condition-expand-bar">
	                    <el-button
	                      type="primary"
	                      link
	                      size="small"
	                      @click="toggleCardDetails(cardKey(point, 'available'))"
	                    >
	                      {{ isCardExpanded(cardKey(point, 'available')) ? '收起执行细节' : '展开执行细节' }}
	                    </el-button>
	                  </div>

	                  <div
	                    v-if="isCardExpanded(cardKey(point, 'available'))"
	                    class="condition-panel-grid"
	                  >
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
                  <div class="footer-actions">
                    <span v-if="point.buy_requires_sector_resonance" class="footer-flag">{{ resonanceLabel(point) }}</span>
                    <el-button type="primary" link size="small" @click="openBuyAnalysis(point)">买点详解</el-button>
                    <el-button type="primary" link size="small" @click="openCheckup(point)">全面体检</el-button>
                  </div>
                </div>
              </article>
                  </div>
                </section>
              </div>
              <div v-if="backupAvailablePoints.length" class="available-group-head available-group-head-secondary">
                <div>
                  <div class="available-group-title">备选可买</div>
                  <div class="available-group-desc">这些票仍符合可买条件，但优先级低于主执行名单，不必同时盯满。</div>
                </div>
                <div class="available-group-meta">{{ backupAvailablePoints.length }} 只</div>
              </div>
              <div v-if="backupAvailablePoints.length" class="type-group-stack type-group-stack-secondary">
                <section
                  v-for="group in backupAvailableGroups"
                  :key="`backup-${group.key}`"
                  class="type-group type-group-secondary"
                >
                  <div class="type-group-head">
                    <div>
                      <div class="type-group-title">{{ group.title }}</div>
                      <div class="type-group-desc">{{ group.desc }}</div>
                    </div>
                    <div class="type-group-meta">{{ group.items.length }} 只</div>
                  </div>
                  <div class="signal-grid signal-grid-secondary">
	                <article
	                  v-for="point in group.items"
	                  :key="`backup-${point.ts_code}`"
	                  :class="['signal-card', 'signal-card-watch', entryModeCardClass(point), { 'signal-card-review-focused': matchesReviewFocus(point, 'buy_available') }]"
	                >
                  <div class="signal-card-header">
                    <div class="signal-title-wrap">
                      <div class="signal-stock">{{ point.stock_name }}</div>
                      <div class="signal-code">{{ point.ts_code }}</div>
                    </div>
                    <div class="signal-badges">
                      <el-tag size="small" type="warning">备选</el-tag>
                      <el-tag size="small" type="primary">{{ point.buy_display_type || point.buy_point_type }}</el-tag>
                      <el-tag v-if="point.buy_execution_context" size="small" type="info">{{ point.buy_execution_context }}</el-tag>
                      <el-tag v-if="isInvalidationWatchActive(point)" size="small" type="danger">失效观察期</el-tag>
                      <el-tag v-if="entryModeBadgeLabel(point)" size="small" :type="entryModeBadgeType(point)">{{ entryModeBadgeLabel(point) }}</el-tag>
                    </div>
	                  </div>

                  <div class="signal-meta">
                    <span v-if="directionMatchLabel(point)">{{ directionMatchLabel(point) }}</span>
                    <span>{{ poolContextLabel(point) }}</span>
                    <span v-if="point.execution_proximity_tag" :class="['signal-meta-chip', executionProximityMetaClass(point)]">
                      {{ point.execution_proximity_tag }}
                    </span>
                    <span>{{ point.candidate_bucket_tag || '未分层' }}</span>
                    <span>{{ point.candidate_source_tag || '无来源标记' }}</span>
                  </div>

                  <div class="signal-intent signal-intent-watch">
                    {{ primaryActionLine(point, displayEnvProfile) }}
                  </div>
                  <div v-if="isInvalidationWatchActive(point)" class="signal-watch-alert signal-watch-alert-watch">
                    <div class="signal-watch-alert-title">已跌破失效价，先看能否拉回</div>
                    <div class="signal-watch-alert-copy">{{ invalidationWatchLine(point) }}</div>
                  </div>
                  <div class="hard-filter-strip" :class="{ 'hard-filter-warn': (point.hard_filter_failed_count || 0) > 0 }">
                    {{ hardFilterLine(point) }}
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
                        {{ executionGapLabel(point) }}
                        <strong :class="priceClass(executionGapValue(point))">{{ formatGap(executionGapValue(point)) }}</strong>
                      </span>
                    </div>
                  </div>

                  <div class="signal-footer">
                    <span>{{ point.buy_comment || '优先级次于主执行名单。' }}</span>
                    <div class="footer-actions">
                      <el-button type="primary" link size="small" @click="openBuyAnalysis(point)">买点详解</el-button>
                    </div>
                  </div>
                </article>
                  </div>
                </section>
              </div>
            </template>
          </el-tab-pane>

          <el-tab-pane name="observe">
            <template #label>
              <span>观察 <em class="tab-count">{{ observePoints.length }}</em></span>
            </template>
            <el-empty v-if="!observePoints.length" description="暂无观察标的" />
            <div v-else class="type-group-stack">
              <section
                v-for="group in observeGroups"
                :key="`observe-${group.key}`"
                class="type-group"
              >
                <div class="type-group-head">
                  <div>
                    <div class="type-group-title">{{ group.title }}</div>
                    <div class="type-group-desc">{{ group.desc }}</div>
                  </div>
                  <div class="type-group-meta">{{ group.items.length }} 只</div>
                </div>
                <div class="signal-grid">
                  <article
                    v-for="point in group.items"
                    :key="point.ts_code"
                    :class="['signal-card', 'signal-card-watch', { 'signal-card-focused': matchesFocusSector(point), 'signal-card-review-focused': matchesReviewFocus(point, 'buy_observe') }]"
                  >
                <div class="signal-card-header">
                  <div class="signal-title-wrap">
                    <div class="signal-stock">{{ point.stock_name }}</div>
                    <div class="signal-code">{{ point.ts_code }}</div>
                  </div>
                  <div class="signal-badges">
                    <el-tag size="small" type="warning">{{ point.buy_display_type || point.buy_point_type }}</el-tag>
                    <el-tag v-if="point.buy_execution_context" size="small" type="info">{{ point.buy_execution_context }}</el-tag>
                    <el-tag size="small" :type="riskTagType(point.buy_risk_level)">{{ point.buy_risk_level }}风险</el-tag>
                    <el-tooltip v-if="point.review_bias_label" :content="point.review_bias_reason || point.review_bias_label" placement="top">
                      <el-tag size="small" :type="reviewBiasTagType(point.review_bias_label)">
                        {{ point.review_bias_label }}
                      </el-tag>
                    </el-tooltip>
                  </div>
                </div>

	                <div class="signal-meta">
	                  <span v-if="directionMatchLabel(point)">{{ directionMatchLabel(point) }}</span>
	                  <span>{{ poolContextLabel(point) }}</span>
	                  <span v-if="point.execution_proximity_tag" :class="['signal-meta-chip', executionProximityMetaClass(point)]">
	                    {{ point.execution_proximity_tag }}
	                  </span>
	                  <span>{{ point.candidate_bucket_tag || '未分层' }}</span>
	                  <span>{{ point.candidate_source_tag || '无来源标记' }}</span>
	                </div>

                <div class="signal-intent signal-intent-watch">
                  {{ observeActionLine(point, displayEnvProfile) }}
                </div>
                <div class="hard-filter-strip" :class="{ 'hard-filter-warn': (point.hard_filter_failed_count || 0) > 0 }">
                  {{ hardFilterLine(point) }}
                </div>

                <div class="quote-strip quote-strip-watch">
                  <div class="quote-main">
                    <span class="quote-label">最新价</span>
                    <strong class="quote-price">{{ formatPrice(point.buy_current_price) }}</strong>
                    <span :class="['quote-change', priceClass(point.buy_current_change_pct)]">
                      {{ formatSignedPct(point.buy_current_change_pct) }}
                    </span>
                    <span class="quote-source" :class="{ 'quote-source-live': isRealtimeSource(point.buy_data_source) }">
                      {{ quoteMetaLine(point.buy_data_source, point.buy_quote_time, displayDate) }}
                    </span>
                  </div>
                  <div class="quote-side">
                    <span class="quote-pair">
                      {{ observeTriggerGapLabel(point) }}
                      <strong :class="priceClass(executionGapValue(point))">{{ formatGap(executionGapValue(point)) }}</strong>
                    </span>
                  </div>
                </div>

	                  <div class="condition-section">
	                    <div class="section-kicker">观察重点</div>
		                  <div
		                    v-if="!isCardExpanded(cardKey(point, 'observe'))"
		                    class="condition-summary-grid condition-summary-grid-watch"
		                  >
		                    <section class="condition-summary-card condition-summary-trigger">
		                      <div class="summary-card-head">
		                        <span class="panel-step">1</span>
		                        <div class="summary-card-copy">
		                          <div class="panel-title">{{ observeFocusTitle(point) }}</div>
		                          <div class="panel-subtitle">{{ observeFocusSubtitle(point) }}</div>
		                        </div>
		                      </div>
		                      <div class="summary-card-body">{{ observeFocusBody(point) }}</div>
		                    </section>

		                    <section class="condition-summary-card condition-summary-confirm">
		                      <div class="summary-card-head">
		                        <span class="panel-step">2</span>
		                        <div class="summary-card-copy">
		                          <div class="panel-title">{{ observeConfirmTitle(point) }}</div>
		                          <div class="panel-subtitle">{{ observeConfirmSubtitle(point) }}</div>
		                        </div>
		                        <span class="summary-count">{{ splitCond(point.buy_confirm_cond).length }}条</span>
		                      </div>
		                      <div class="summary-card-body">{{ observeConfirmBody(point) }}</div>
		                    </section>
		                  </div>

	                  <div class="condition-expand-bar">
	                    <el-button
	                      type="primary"
	                      link
	                      size="small"
	                      @click="toggleCardDetails(cardKey(point, 'observe'))"
	                    >
	                      {{ isCardExpanded(cardKey(point, 'observe')) ? '收起观察细节' : '展开观察细节' }}
	                    </el-button>
	                  </div>

	                  <div
	                    v-if="isCardExpanded(cardKey(point, 'observe'))"
	                    class="condition-panel-grid condition-panel-grid-watch"
	                  >
		                    <section class="condition-panel condition-panel-trigger">
		                      <div class="panel-head">
		                        <span class="panel-step">1</span>
		                        <div>
		                          <div class="panel-title">{{ observeFocusTitle(point) }}</div>
		                          <div class="panel-subtitle">{{ observeFocusSubtitle(point) }}</div>
		                        </div>
		                      </div>
		                      <div class="panel-body">
		                        <div class="condition-title">{{ observeFocusBody(point) }}</div>
		                      </div>
		                    </section>

		                    <section class="condition-panel condition-panel-confirm">
		                      <div class="panel-head">
		                        <span class="panel-step">2</span>
		                        <div>
		                          <div class="panel-title">{{ observeConfirmTitle(point) }}</div>
		                          <div class="panel-subtitle">{{ observeConfirmSubtitle(point) }}</div>
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
                  <div class="footer-actions">
                    <span v-if="point.direction_match_note" class="footer-flag">{{ point.direction_match_note }}</span>
                    <span class="footer-flag">{{ observeFooterFlag(point) }}</span>
                    <el-button type="primary" link size="small" @click="openBuyAnalysis(point)">买点详解</el-button>
                    <el-button type="primary" link size="small" @click="openCheckup(point)">全面体检</el-button>
                  </div>
                </div>
              </article>
                </div>
              </section>
            </div>
          </el-tab-pane>

          <el-tab-pane name="skip">
            <template #label>
              <span>不买 <em class="tab-count">{{ notBuyPoints.length }}</em></span>
            </template>
            <el-empty v-if="!notBuyPoints.length" description="暂无明确放弃标的" />
            <div v-else class="skip-list">
              <div v-for="point in notBuyPoints" :key="point.ts_code" class="skip-row">
                <div class="skip-main">
	                  <strong>{{ point.stock_name }}</strong>
	                  <span class="signal-code">{{ point.ts_code }}</span>
	                  <span v-if="directionMatchLabel(point)" class="skip-meta">{{ directionMatchLabel(point) }}</span>
	                  <span class="skip-meta">{{ poolTagLabel(point.stock_pool_tag) }}</span>
	                  <span class="skip-meta">{{ point.candidate_bucket_tag || '未分层' }}</span>
	                  <span class="skip-meta">{{ point.buy_display_type || point.buy_point_type }}</span>
	                  <span v-if="point.buy_execution_context" class="skip-meta">{{ point.buy_execution_context }}</span>
	                </div>
                <div class="skip-quote">
                  <strong>{{ formatPrice(point.buy_current_price) }}</strong>
                  <span :class="priceClass(point.buy_current_change_pct)">{{ formatSignedPct(point.buy_current_change_pct) }}</span>
                </div>
                <div class="skip-reason">{{ skipReasonLine(point, displayEnvProfile) }}</div>
                <div class="skip-actions">
                  <el-button type="primary" link size="small" @click="openBuyAnalysis(point)">买点详解</el-button>
                  <el-button type="primary" link size="small" @click="openCheckup(point)">全面体检</el-button>
                </div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-card>
    <BuyAnalysisDrawer
      v-model="buyAnalysisVisible"
      :ts-code="buyAnalysisStock.tsCode"
      :stock-name="buyAnalysisStock.stockName"
      :trade-date="displayDate"
      :source-pool-tag="buyAnalysisStock.sourcePoolTag"
      :current-price="buyAnalysisStock.currentPrice"
      :current-change-pct="buyAnalysisStock.currentChangePct"
    />
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
import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { decisionApi } from '../api'
import { ElMessage } from 'element-plus'
import StockCheckupDrawer from '../components/StockCheckupDrawer.vue'
import BuyAnalysisDrawer from '../components/BuyAnalysisDrawer.vue'
import DataFreshnessBar from '../components/DataFreshnessBar.vue'
import { formatLocalTime } from '../utils/datetime'

const loading = ref(false)
const activeTab = ref('available')
const displayDate = ref('')
const buyData = ref({
  market_env_tag: '',
  theme_leaders: [],
  industry_leaders: [],
  available_buy_points: [],
  observe_buy_points: [],
  not_buy_points: [],
})
const buyAnalysisVisible = ref(false)
const buyAnalysisStock = ref({ tsCode: '', stockName: '', sourcePoolTag: '', currentPrice: null, currentChangePct: null })
const checkupVisible = ref(false)
const checkupStock = ref({ tsCode: '', stockName: '', defaultTarget: '交易型' })
const expandedCards = ref({})
const reviewStatsData = ref(null)
const REVIEW_STATS_TIMEOUT = 90000
const BUY_POINT_TIMEOUT = 90000
const loadError = ref('')
const route = useRoute()
const router = useRouter()
const normalizeStrategyStyle = (value) => {
  const normalized = String(value || 'balanced').trim().toLowerCase()
  if (normalized === 'left' || normalized === 'right') return normalized
  return 'balanced'
}

const strategyStyle = ref(normalizeStrategyStyle(route.query.strategy_style))
const focusSector = computed(() => String(route.query.focus_sector || '').trim())
const focusSectorSourceType = computed(() => String(route.query.focus_sector_source_type || '').trim())
const reviewBucketFilter = computed(() => String(route.query.review_bucket || '').trim())
const manualBucketFilter = computed(() => String(route.query.bucket || '').trim())
const reviewSourceFilter = computed(() => String(route.query.review_source || '').trim())
const notificationAction = computed(() => String(route.query.notification_action || '').trim())
const notificationTsCode = computed(() => String(route.query.ts_code || '').trim())
const notificationStockName = computed(() => String(route.query.stock_name || '').trim())
const focusOnly = ref(false)
const activeBucketFilter = computed(() => manualBucketFilter.value || reviewBucketFilter.value)
const normalizeSourceType = (value) => {
  const source = String(value || '').trim()
  if (source === 'limitup_industry') return 'industry'
  return source
}

const directionSourceLabel = (sourceType) => {
  const normalized = normalizeSourceType(sourceType)
  if (normalized === 'concept') return '主线题材'
  if (normalized === 'industry') return '承接行业'
  return '主线候选'
}

const focusSectorLabel = computed(() => (
  focusSectorSourceType.value ? `${directionSourceLabel(focusSectorSourceType.value)} ` : ''
))
const strategyStyleLabel = computed(() => {
  const style = normalizeStrategyStyle(buyData.value.strategy_style || strategyStyle.value)
  if (style === 'left') return '偏左侧'
  if (style === 'right') return '偏右侧'
  return '均衡'
})

const BUY_POINT_GROUP_ORDER = ['突破', '突破后回踩', '回踩承接', '低吸', '修复转强']
const BUY_POINT_GROUP_META = {
  突破: {
    title: '突破确认',
    desc: '这组更看放量站稳和分时确认，不做提前抢跑。',
  },
  突破后回踩: {
    title: '突破后回踩',
    desc: '原始结构是突破确认，但当前位置更适合等回踩承接，不直接追高。',
  },
  回踩承接: {
    title: '回踩承接',
    desc: '这组重点等回踩确认，不把现价附近直接当执行位。',
  },
  低吸: {
    title: '低吸试错',
    desc: '这组更偏靠近支撑试错，拉高后不追。',
  },
  修复转强: {
    title: '修复转强',
    desc: '这组先看关键位修复，再决定能否从观察转执行。',
  },
}

const matchesFocusSector = (point) => {
  if (!focusSector.value) return false
  const candidates = [
    String(point.direction_match_name || '').trim(),
    String(point.sector_name || '').trim(),
  ].filter(Boolean)
  const nameMatched = candidates.some((name) => name.includes(focusSector.value))
  if (!nameMatched) return false
  if (!focusSectorSourceType.value) return true
  return normalizeSourceType(point.direction_match_source_type) === normalizeSourceType(focusSectorSourceType.value)
}

const sortByFocusSector = (points = []) => {
  const sorted = [...points].sort((a, b) => Number(matchesFocusSector(b)) - Number(matchesFocusSector(a)))
  if (focusSector.value && focusOnly.value) {
    return sorted.filter((item) => matchesFocusSector(item))
  }
  return sorted
}

const matchesActiveBucket = (point) => {
  if (!activeBucketFilter.value) return true
  return String(point.candidate_bucket_tag || '').trim() === activeBucketFilter.value
}

const matchesReviewSource = (sourceType) => {
  if (!reviewSourceFilter.value) return true
  return reviewSourceFilter.value === sourceType
}

const matchesReviewFocus = (point, sourceType) => matchesReviewSource(sourceType) && matchesActiveBucket(point)

const applySourceAndFocusFilters = (points = [], sourceType = '') => {
  if (!matchesReviewSource(sourceType)) return []
  return sortByFocusSector(points)
}

const applyPageFilters = (points = [], sourceType = '') => applySourceAndFocusFilters(points, sourceType).filter(matchesActiveBucket)

const availablePoints = computed(() => applyPageFilters(buyData.value.available_buy_points || [], 'buy_available'))
const observePoints = computed(() => applyPageFilters(buyData.value.observe_buy_points || [], 'buy_observe'))
const notBuyPoints = computed(() => applyPageFilters(buyData.value.not_buy_points || [], 'buy_not'))
const structureFilterBasePoints = computed(() => ([
  ...applySourceAndFocusFilters(buyData.value.available_buy_points || [], 'buy_available'),
  ...applySourceAndFocusFilters(buyData.value.observe_buy_points || [], 'buy_observe'),
  ...applySourceAndFocusFilters(buyData.value.not_buy_points || [], 'buy_not'),
]))
const structureFilterBaseCount = computed(() => structureFilterBasePoints.value.length)

const displayBuyPointType = (point) => String(point?.buy_display_type || point?.buy_point_type || '').trim()
const normalizeBuyPointType = (value) => String(value || '').trim() || '其他'

const buyPointTypeRank = (value) => {
  const normalized = normalizeBuyPointType(value)
  const index = BUY_POINT_GROUP_ORDER.indexOf(normalized)
  return index >= 0 ? index : BUY_POINT_GROUP_ORDER.length
}

const buyPointGroupMeta = (value) => BUY_POINT_GROUP_META[normalizeBuyPointType(value)] || {
  title: normalizeBuyPointType(value),
  desc: '这组机会较少，执行前先回到卡片里的触发和确认条件。',
}

const groupBuyPoints = (points = []) => {
  const grouped = new Map()
  for (const point of points) {
    const key = normalizeBuyPointType(displayBuyPointType(point))
    if (!grouped.has(key)) grouped.set(key, [])
    grouped.get(key).push(point)
  }
  return [...grouped.entries()]
    .sort((a, b) => buyPointTypeRank(a[0]) - buyPointTypeRank(b[0]))
    .map(([key, items]) => {
      const meta = buyPointGroupMeta(key)
      return {
        key,
        title: meta.title,
        desc: meta.desc,
        items,
      }
    })
}

const reviewSourceLabel = computed(() => reviewSnapshotTypeLabel(reviewSourceFilter.value))

const primaryAvailableLimit = computed(() => {
  if (buyData.value.market_env_tag === '进攻') return 5
  if (buyData.value.market_env_tag === '中性') return 3
  return 2
})

const primaryAvailablePoints = computed(() => {
  const points = [...availablePoints.value]
  const limit = primaryAvailableLimit.value
  const maxSector = buyData.value.market_env_tag === '进攻' ? 2 : 1
  const maxBreakthrough = buyData.value.market_env_tag === '进攻' ? 2 : 1
  const selected = []
  const sectorCount = new Map()
  let breakthroughCount = 0
  const skipped = []

  for (const point of points) {
    const sector = point.direction_match_name || point.sector_name || point.candidate_source_tag || point.stock_name || point.ts_code
    const currentSectorCount = sectorCount.get(sector) || 0
    const type = displayBuyPointType(point)
    const isBreakthrough = ['突破', '突破后回踩'].includes(type)
    if (currentSectorCount >= maxSector || (isBreakthrough && breakthroughCount >= maxBreakthrough)) {
      skipped.push(point)
      continue
    }
    selected.push(point)
    sectorCount.set(sector, currentSectorCount + 1)
    if (isBreakthrough) breakthroughCount += 1
    if (selected.length >= limit) break
  }

  if (selected.length < limit) {
    for (const point of [...skipped, ...points]) {
      if (selected.find((item) => item.ts_code === point.ts_code)) continue
      selected.push(point)
      if (selected.length >= limit) break
    }
  }

  return selected
})

const backupAvailablePoints = computed(() => {
  const selectedCodes = new Set(primaryAvailablePoints.value.map((point) => point.ts_code))
  return availablePoints.value.filter((point) => !selectedCodes.has(point.ts_code))
})

const primaryAvailableGroups = computed(() => groupBuyPoints(primaryAvailablePoints.value))
const backupAvailableGroups = computed(() => groupBuyPoints(backupAvailablePoints.value))
const observeGroups = computed(() => groupBuyPoints(observePoints.value))

const reviewSnapshotTypeLabel = (value) => {
  if (value === 'buy_available') return '买点-可买'
  if (value === 'buy_observe') return '买点-观察'
  if (value === 'buy_add') return '加仓候选'
  if (value === 'pool_account') return '三池-可参与池'
  if (value === 'pool_market') return '三池-观察池'
  return value || '-'
}

const resolveDefaultTab = (payload) => {
  if (reviewSourceFilter.value === 'buy_available') {
    return payload?.available_buy_points?.length ? 'available' : payload?.observe_buy_points?.length ? 'observe' : 'skip'
  }
  if (reviewSourceFilter.value === 'buy_observe') {
    return payload?.observe_buy_points?.length ? 'observe' : payload?.available_buy_points?.length ? 'available' : 'skip'
  }
  if (payload?.available_buy_points?.length) return 'available'
  if (payload?.observe_buy_points?.length) return 'observe'
  return 'skip'
}

const resolveVisibleTab = () => {
  if (reviewSourceFilter.value === 'buy_available') {
    return availablePoints.value.length ? 'available' : observePoints.value.length ? 'observe' : 'skip'
  }
  if (reviewSourceFilter.value === 'buy_observe') {
    return observePoints.value.length ? 'observe' : availablePoints.value.length ? 'available' : 'skip'
  }
  if (availablePoints.value.length) return 'available'
  if (observePoints.value.length) return 'observe'
  return 'skip'
}

const buildReviewQualityScore = (row) => (
  Number(row.avg_return_5d || 0) * 0.6 +
  Number(row.win_rate_5d || 0) * 0.04 +
  Number(row.avg_return_3d || 0) * 0.25 +
  Number(row.win_rate_3d || 0) * 0.015 +
  Number(row.count || 0) * 0.03
)

const reviewBucketStats = computed(() => {
  const grouped = new Map()
  for (const row of (reviewStatsData.value?.bucket_stats || []).filter((item) => item.snapshot_type !== 'buy_add')) {
    const bucket = String(row.candidate_bucket_tag || '未分层').trim() || '未分层'
    if (!grouped.has(bucket)) {
      grouped.set(bucket, {
        bucket,
        count: 0,
        resolved_1d_count: 0,
        resolved_3d_count: 0,
        resolved_5d_count: 0,
        weighted_return_1d: 0,
        weighted_return_3d: 0,
        weighted_return_5d: 0,
        weighted_win_1d: 0,
        weighted_win_3d: 0,
        weighted_win_5d: 0,
      })
    }
    const current = grouped.get(bucket)
    const count = Number(row.count || 0)
    const resolved1d = Number(row.resolved_1d_count || 0)
    const resolved3d = Number(row.resolved_3d_count || 0)
    const resolved5d = Number(row.resolved_5d_count || 0)
    current.count += count
    current.resolved_1d_count += resolved1d
    current.resolved_3d_count += resolved3d
    current.resolved_5d_count += resolved5d
    current.weighted_return_1d += Number(row.avg_return_1d || 0) * resolved1d
    current.weighted_return_3d += Number(row.avg_return_3d || 0) * resolved3d
    current.weighted_return_5d += Number(row.avg_return_5d || 0) * resolved5d
    current.weighted_win_1d += Number(row.win_rate_1d || 0) * resolved1d
    current.weighted_win_3d += Number(row.win_rate_3d || 0) * resolved3d
    current.weighted_win_5d += Number(row.win_rate_5d || 0) * resolved5d
  }

  return [...grouped.values()]
    .map((row) => ({
      candidate_bucket_tag: row.bucket,
      count: row.count,
      resolved_1d_count: row.resolved_1d_count,
      resolved_3d_count: row.resolved_3d_count,
      resolved_5d_count: row.resolved_5d_count,
      avg_return_1d: row.resolved_1d_count ? row.weighted_return_1d / row.resolved_1d_count : 0,
      avg_return_3d: row.resolved_3d_count ? row.weighted_return_3d / row.resolved_3d_count : 0,
      avg_return_5d: row.resolved_5d_count ? row.weighted_return_5d / row.resolved_5d_count : 0,
      win_rate_1d: row.resolved_1d_count ? row.weighted_win_1d / row.resolved_1d_count : 0,
      win_rate_3d: row.resolved_3d_count ? row.weighted_win_3d / row.resolved_3d_count : 0,
      win_rate_5d: row.resolved_5d_count ? row.weighted_win_5d / row.resolved_5d_count : 0,
    }))
    .map((row) => ({
      ...row,
      resolvedWeight: Number(row.resolved_5d_count || row.resolved_3d_count || row.resolved_1d_count || 0),
      qualityScore: buildReviewQualityScore(row),
    }))
    .filter((row) => row.resolvedWeight > 0 && Number(row.count || 0) >= 2)
    .sort((a, b) => Number(b.qualityScore || 0) - Number(a.qualityScore || 0))
})

const resolveReviewWindow = (row) => {
  if (!row) return { days: 0, count: 0, avg: 0, winRate: 0 }
  if (Number(row.resolved_5d_count || 0) > 0) {
    return {
      days: 5,
      count: Number(row.resolved_5d_count || 0),
      avg: Number(row.avg_return_5d || 0),
      winRate: Number(row.win_rate_5d || 0)
    }
  }
  if (Number(row.resolved_3d_count || 0) > 0) {
    return {
      days: 3,
      count: Number(row.resolved_3d_count || 0),
      avg: Number(row.avg_return_3d || 0),
      winRate: Number(row.win_rate_3d || 0)
    }
  }
  if (Number(row.resolved_1d_count || 0) > 0) {
    return {
      days: 1,
      count: Number(row.resolved_1d_count || 0),
      avg: Number(row.avg_return_1d || 0),
      winRate: Number(row.win_rate_1d || 0)
    }
  }
  return { days: 0, count: 0, avg: 0, winRate: 0 }
}

const formatReviewMetric = (row) => {
  const metric = resolveReviewWindow(row)
  if (!metric.days || !metric.count) return '样本补齐中'
  return `${metric.days}日均值 ${metric.avg.toFixed(1)}% · 胜率 ${metric.winRate.toFixed(0)}% · ${metric.count}条`
}

const structureBucketOptions = computed(() => {
  const rankMap = new Map(reviewBucketStats.value.map((item, index) => [item.candidate_bucket_tag, index]))
  const grouped = new Map()
  for (const point of structureFilterBasePoints.value) {
    const bucket = String(point.candidate_bucket_tag || '未分层').trim() || '未分层'
    if (!grouped.has(bucket)) {
      grouped.set(bucket, { label: bucket, count: 0, rank: rankMap.has(bucket) ? rankMap.get(bucket) : Number.POSITIVE_INFINITY })
    }
    grouped.get(bucket).count += 1
  }
  return [...grouped.values()].sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank
    if (a.count !== b.count) return b.count - a.count
    return a.label.localeCompare(b.label, 'zh-CN')
  })
})

const reviewInsight = computed(() => {
  const best = reviewBucketStats.value[0]
  const weakest = reviewBucketStats.value.length > 1
    ? [...reviewBucketStats.value].sort((a, b) => Number(a.qualityScore || 0) - Number(b.qualityScore || 0))[0]
    : null
  if (!best && !weakest) return null

  return {
    summary: best
      ? '先按执行阶段看可买/观察/放弃，再在同一阶段里按复盘结构排序。'
      : '当前没有形成稳定样本，复盘只做辅助提醒，今天仍按买点条件本身执行。',
    cards: [
      {
        label: '先定阶段',
        cardClass: 'review-bridge-card-neutral',
        title: '可买先于观察，观察先于放弃',
        metric: '执行阶段不被复盘改写',
        action: '复盘只会调整同阶段里的先后顺序，不会把观察票直接抬到可买票前面，也不会把可买票自动打成不可买。',
        note: '先回到卡片里的触发、确认和失效位，再决定是否执行。'
      },
      {
        label: '同阶段优先',
        cardClass: 'review-bridge-card-do',
        title: best ? best.candidate_bucket_tag : '暂无稳定加分结构',
        metric: formatReviewMetric(best),
        action: best
          ? `在同一执行阶段里，先看 ${best.candidate_bucket_tag}；可买池里先排这类，可观察池里也先跟这类。`
          : '先按当日强弱和确认条件排序，不额外放大任何结构。',
        note: best
          ? '它是结构优先级更高，不是执行阶段更高。'
          : '复盘还没形成稳定偏好，不建议提前下注。'
      },
      {
        label: '同阶段谨慎',
        cardClass: 'review-bridge-card-avoid',
        title: weakest ? weakest.candidate_bucket_tag : '暂无明确弱项',
        metric: formatReviewMetric(weakest),
        action: weakest
          ? `即使它进了可买池，也要更重视量能、承接和失效位，不主动放大仓位。`
          : '暂时没有需要整体回避的结构，继续按规则筛选。',
        note: weakest
          ? '这是同阶段里的谨慎项，不是直接否掉整类机会。'
          : '没有明显拖后腿的一类结构。'
      }
    ]
  }
})

const getLocalDate = () => {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const applyBuyData = (payload) => {
  buyData.value = payload || {
    market_env_tag: '',
    theme_leaders: [],
    industry_leaders: [],
    available_buy_points: [],
    observe_buy_points: [],
    not_buy_points: [],
  }
  activeTab.value = resolveDefaultTab(buyData.value)
}

const scheduleReviewInsightLoad = () => {
  if (typeof window === 'undefined') {
    loadReviewInsight()
    return
  }
  window.setTimeout(() => {
    loadReviewInsight()
  }, 180)
}

const displayEnvProfile = computed(() => buyData.value.market_env_profile || buyData.value.market_env_tag || '')
const buyDirectionItems = computed(() => [
  ...(buyData.value.theme_leaders || []).slice(0, 1).map((sector) => ({ label: '主线题材', name: sector.sector_name })),
  ...(buyData.value.industry_leaders || []).slice(0, 1).map((sector) => ({ label: '承接行业', name: sector.sector_name })),
])

const envChipClass = (tag) => {
  if (['强进攻', '进攻', '中性偏强', '情绪修复'].includes(tag)) return 'chip-attack'
  if (['中性偏谨慎', '弱中性', '中性'].includes(tag)) return 'chip-neutral'
  return 'chip-defense'
}

const envHeadline = (tag) => {
  if (tag === '中性偏强') return '环境中性偏强，优先看主线确认和强势回踩'
  if (tag === '中性偏谨慎') return '环境中性偏谨慎，只做低吸和回踩确认'
  if (tag === '弱中性') return '环境偏弱，只保留最强分歧转强的观察位'
  if (tag === '进攻') return '环境偏进攻，优先看强势确认和突破延续'
  if (tag === '中性') return '环境中性，只做确认过的回踩承接'
  return '环境偏防守，只保留极少数轻仓试错机会'
}

const envGuidance = (tag) => {
  if (buyData.value.market_headline && tag === displayEnvProfile.value) {
    return buyData.value.market_subheadline || '先看市场节奏，再决定是观察还是执行。'
  }
  if (tag === '中性偏强') return '优先看主线和核心股的确认动作，观察票满足条件后可以更快转执行。'
  if (tag === '中性偏谨慎') return '先看观察池，只有回踩承接和量能确认到位才转执行，避免一致性追高。'
  if (tag === '弱中性') return '今天更适合少做，观察票也只保留最强核心方向，不把弱跟风当机会。'
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

const reviewBiasTagType = (label) => {
  if (label === '复盘加分') return 'success'
  if (label === '复盘降权') return 'danger'
  return 'info'
}

const entryModeBadgeLabel = (point) => {
  const mode = String(point?.account_entry_mode || '')
  if (mode === 'defense_trial') return '防守试错'
  if (mode === 'aggressive_trial') return '进攻试错'
  if (mode === 'standard') return '标准'
  return ''
}

const entryModeBadgeType = (point) => {
  const mode = String(point?.account_entry_mode || '')
  if (mode === 'defense_trial') return 'danger'
  if (mode === 'aggressive_trial') return 'warning'
  return 'success'
}

const entryModeCardClass = (point) => {
  const mode = String(point?.account_entry_mode || '')
  if (mode === 'defense_trial') return 'signal-card-defense-trial'
  if (mode === 'aggressive_trial') return 'signal-card-aggressive-trial'
  if (mode === 'standard') return 'signal-card-standard'
  return ''
}

const entryModeSizingClass = (point) => {
  const mode = String(point?.account_entry_mode || '')
  if (mode === 'defense_trial') return 'signal-sizing-defense-trial'
  if (mode === 'aggressive_trial') return 'signal-sizing-aggressive-trial'
  if (mode === 'standard') return 'signal-sizing-standard'
  return ''
}

const formatPrice = (value) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(2)
}

const formatMoney = (value) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

const formatShares = (value) => {
  if (value === null || value === undefined) return '-'
  return `${Number(value).toLocaleString('zh-CN')} 股`
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

const allBuyCandidates = computed(() => [
  ...(buyData.value.available_buy_points || []),
  ...(buyData.value.observe_buy_points || []),
  ...(buyData.value.not_buy_points || []),
])
const buyRealtimeCount = computed(() => allBuyCandidates.value.filter((point) => isRealtimeSource(point.buy_data_source)).length)
const buyFreshnessSummary = computed(() => {
  const total = allBuyCandidates.value.length
  if (!total) return '当前无候选'
  if (!buyRealtimeCount.value) return '全部为回退价格'
  if (buyRealtimeCount.value === total) return '全部为盘中实时'
  return `混合口径 ${buyRealtimeCount.value}/${total} 为盘中实时`
})
const buyFreshnessItems = computed(() => [
  { label: '分析日', value: displayDate.value || '-', tone: 'strong' },
  {
    label: '候选风格',
    value: strategyStyleLabel.value,
    tone: strategyStyle.value === 'balanced' ? 'strong' : 'warn',
  },
  {
    label: '价格口径',
    value: buyFreshnessSummary.value,
    tone: buyRealtimeCount.value ? 'strong' : 'warn',
  },
  {
    label: '候选状态',
    value: `可买 ${availablePoints.value.length} / 观察 ${observePoints.value.length} / 放弃 ${notBuyPoints.value.length}`,
    tone: availablePoints.value.length ? 'muted' : 'warn',
  },
])
const buyFreshnessNote = computed(() => {
  if (strategyStyle.value !== 'balanced') {
    return `当前按${strategyStyleLabel.value}候选口径分析，先和三池页保持同一风格，再判断是否执行。`
  }
  if (!availablePoints.value.length && !observePoints.value.length) {
    return '今天不建议开新仓，优先回三池和卖点页处理旧仓。'
  }
  if (!availablePoints.value.length) {
    return '当前没有直接执行票，先盯观察池，确认条件不到齐就不要抢先手。'
  }
  return '先看价格口径和触发位，再决定是观察还是动手。'
})

const poolTagLabel = (tag) => {
  if (tag === '账户可参与池') return '账户可参与池'
  if (tag === '市场最强观察池') return '市场最强观察池'
  if (tag === '持仓处理池') return '持仓处理池'
  return tag || '未入池'
}

const poolContextLabel = (point) => {
  const base = poolTagLabel(point?.stock_pool_tag)
  const proximity = String(point?.execution_proximity_tag || '').trim()
  if (!proximity || base !== '账户可参与池') return base
  return `${base} · ${proximity}`
}

const directionMatchLabel = (point) => {
  const name = String(point?.direction_match_name || '').trim()
  if (!name) return ''
  return `${directionSourceLabel(point?.direction_match_source_type)} ${name}`
}

const resonanceLabel = (point) => {
  const matchLabel = directionMatchLabel(point)
  if (matchLabel) return `需要${matchLabel}共振`
  return '需要板块共振'
}

const executionProximityMetaClass = (point) => {
  const tag = String(point?.execution_proximity_tag || '').trim()
  if (tag === '接近执行位') return 'signal-meta-chip-ready'
  if (tag === '已过确认位' || tag === '待突破') return 'signal-meta-chip-breakthrough'
  if (tag === '待深回踩') return 'signal-meta-chip-deep'
  return 'signal-meta-chip-wait'
}

const hasUnifiedExecutionReference = (point) => {
  if (!point) return false
  return point.execution_reference_price !== null && point.execution_reference_price !== undefined
}

const executionReferencePrice = (point) => (
  hasUnifiedExecutionReference(point) ? point.execution_reference_price : point?.buy_trigger_price
)

const executionGapValue = (point) => (
  hasUnifiedExecutionReference(point) ? point.execution_reference_gap_pct : point?.buy_trigger_gap_pct
)

const executionReferenceLabel = (point) => {
  if (!hasUnifiedExecutionReference(point)) return '执行位'
  const tag = String(point?.execution_proximity_tag || '').trim()
  if (tag === '待深回踩') return '深回踩位'
  return '执行位'
}

const executionGapLabel = (point) => {
  if (!hasUnifiedExecutionReference(point)) return '距执行位'
  const tag = String(point?.execution_proximity_tag || '').trim()
  if (tag === '待深回踩') return '距深回踩'
  return '距执行位'
}

const isInvalidationWatchActive = (point) => Boolean(point?.invalidation_watch_active)

const invalidationWatchRemainingMinutes = (point) => {
  const seconds = Number(point?.invalidation_watch_remaining_seconds)
  if (!Number.isFinite(seconds) || seconds <= 0) return 0
  return Math.max(1, Math.ceil(seconds / 60))
}

const invalidationWatchLine = (point) => {
  const invalid = formatPrice(point?.buy_invalid_price)
  const deadline = point?.invalidation_watch_deadline ? formatLocalTime(point.invalidation_watch_deadline) : ''
  const remainingMinutes = invalidationWatchRemainingMinutes(point)
  if (remainingMinutes > 0 && deadline) {
    return `当前价已在失效价 ${invalid} 下方，先观察 ${remainingMinutes} 分钟内能否拉回；若到 ${deadline} 仍收不回，再踢出可买池。`
  }
  if (remainingMinutes > 0) {
    return `当前价已在失效价 ${invalid} 下方，先观察 ${remainingMinutes} 分钟内能否拉回；若仍收不回，再踢出可买池。`
  }
  return `当前价已在失效价 ${invalid} 下方，先看能否快速拉回；若仍收不回，再踢出可买池。`
}

const splitCond = (text) => {
  if (!text) return ['-']
  return String(text)
    .split('；')
    .map((item) => item.trim())
    .filter(Boolean)
}

const summarizeCond = (text) => {
  const items = splitCond(text)
  if (!items.length) return '-'
  const first = items[0]
  if (items.length === 1) return first
  return `${first} 等 ${items.length} 个条件`
}

const cardKey = (point, scope) => `${scope}:${point.ts_code}`

const isCardExpanded = (key) => Boolean(expandedCards.value[key])

const toggleCardDetails = (key) => {
  expandedCards.value = {
    ...expandedCards.value,
    [key]: !expandedCards.value[key]
  }
}

const envChecklist = (tag) => {
  if (tag === '中性偏强') {
    return ['优先看主线核心确认', '确认后可转执行', '后排跟风不过度分散']
  }
  if (tag === '中性偏谨慎') {
    return ['优先做低吸和回踩确认', '确认条件不齐不动手', '不做一致性追高']
  }
  if (tag === '弱中性') {
    return ['只保留最强分歧转强', '普通新机会先放弃', '仓位比普通中性更小']
  }
  if (tag === '进攻') {
    return ['先看强势确认', '触发价到了再看量能', '失效价破位立即放弃']
  }
  if (tag === '中性') {
    return ['优先做回踩承接', '确认条件不够就继续等', '不要用观察票代替可买票']
  }
  return ['只做最强核心股试错', '仓位先轻，不要满上', '确认条件不齐就不动手']
}

const primaryActionLine = (point, envTag) => {
  if (isInvalidationWatchActive(point)) {
    const invalid = formatPrice(point.buy_invalid_price)
    return `失效观察：当前价已跌破失效价 ${invalid}，先别执行，等重新拉回后再判断。`
  }
  const trigger = formatPrice(executionReferencePrice(point))
  const invalid = formatPrice(point.buy_invalid_price)
  const prefix = envTag === '防守' ? '轻仓试错' : envTag === '中性偏谨慎' ? '低吸确认' : envTag === '弱中性' ? '观察优先' : '执行计划'
  const triggerLabel = executionReferenceLabel(point)
  return `${prefix}：到 ${triggerLabel}${trigger} 附近再看，跌回 ${invalid} 下方就放弃。`
}

const observeTypeLabel = (point) => displayBuyPointType(point)

const resolveRetraceFloorRatio = (tsCode) => {
  const code = String(tsCode || '').toUpperCase()
  if (code.endsWith('.BJ')) return 0.82
  if (code.startsWith('300') || code.startsWith('301') || code.startsWith('688')) return 0.88
  return 0.93
}

const isObserveDeepRetraceReference = (point) => {
  if (String(point?.execution_proximity_tag || '').trim() === '待深回踩') return true
  if (observeTypeLabel(point) !== '回踩承接') return false
  const current = Number(point?.buy_current_price)
  const trigger = Number(executionReferencePrice(point))
  if (Number.isNaN(current) || Number.isNaN(trigger) || current <= 0 || trigger <= 0) return false
  return trigger < current * resolveRetraceFloorRatio(point?.ts_code)
}

const observeTriggerGapLabel = (point) => (isObserveDeepRetraceReference(point) ? '距深回踩' : executionGapLabel(point))

const observeFooterFlag = (point) => (isObserveDeepRetraceReference(point) ? '深回踩参考' : '未到执行位')

const observeFocusTitle = (point) => {
  if (isObserveDeepRetraceReference(point)) return '先看承接'
  const type = observeTypeLabel(point)
  if (type === '突破') return '先等突破'
  if (type === '修复转强') return '先等修复'
  if (type === '低吸') return '先等低吸'
  return '先等回踩'
}

const observeFocusSubtitle = (point) => {
  if (isObserveDeepRetraceReference(point)) return '深回踩位离现价较远，先看现价附近别转弱'
  const type = observeTypeLabel(point)
  if (type === '突破') return '先等关键价位和量能一起到位'
  if (type === '修复转强') return '先等关键位重新站回'
  if (type === '低吸') return '先等价格回到支撑附近'
  return '先等价格回到触发位附近'
}

const observeFocusBody = (point) => {
  const type = observeTypeLabel(point)
  const trigger = formatPrice(executionReferencePrice(point))
  const invalid = formatPrice(point?.buy_invalid_price)
  const triggerLabel = executionReferenceLabel(point)

  if (isObserveDeepRetraceReference(point)) {
    return `${triggerLabel}${trigger} 离现价较远，当前先把它当深回踩参考；更近端先看现价附近能否横住，不要快速跌回 ${invalid} 下方。`
  }
  if (type === '突破') {
    return `先看能否靠近 ${triggerLabel}${trigger} 一带并放量站稳；没到这一步前，先别把它当成已经突破。`
  }
  if (type === '修复转强') {
    return `先等价格重新站回 ${triggerLabel}${trigger} 一带，再看修复动作能不能延续；提前转弱跌回 ${invalid} 下方就不继续跟。`
  }
  if (type === '低吸') {
    return `先等价格回到 ${triggerLabel}${trigger} 一带附近再看承接，不要在离支撑还远的时候抢低吸。`
  }
  return `先等价格回踩到 ${triggerLabel}${trigger} 一带稳住；没回到这里前，不把现价附近当执行位，跌回 ${invalid} 下方则直接失效。`
}

const observeConfirmTitle = (point) => {
  if (isObserveDeepRetraceReference(point)) return '看别转弱'
  const type = observeTypeLabel(point)
  if (type === '突破') return '看站稳'
  if (type === '修复转强') return '看修复'
  if (type === '低吸') return '看止跌'
  return '看承接'
}

const observeConfirmSubtitle = (point) => {
  if (isObserveDeepRetraceReference(point)) return '先确认高位不补跌，再等更深回踩'
  const type = observeTypeLabel(point)
  if (type === '突破') return '量价没站稳就继续观察'
  if (type === '修复转强') return '修复不完整就继续观察'
  if (type === '低吸') return '止跌和承接不到位就继续观察'
  return '承接和量能没到位就继续观察'
}

const observeConfirmBody = (point) => {
  const type = observeTypeLabel(point)
  const summary = summarizeCond(point?.buy_confirm_cond)
  const trigger = formatPrice(executionReferencePrice(point))
  const invalid = formatPrice(point?.buy_invalid_price)
  const triggerLabel = executionReferenceLabel(point)

  if (isObserveDeepRetraceReference(point)) {
    return `重点看 ${summary}；在没回到 ${triggerLabel}${trigger} 前，先确认现价附近不放量转弱，也不要快速跌回 ${invalid} 下方。`
  }
  if (type === '突破') {
    return `重点看 ${summary}；只有突破后的量价和承接都站住，才算从观察转成可执行。`
  }
  if (type === '修复转强') {
    return `重点看 ${summary}；修复动作要连续、要站稳，不能只是一脚拉回去。`
  }
  if (type === '低吸') {
    return `重点看 ${summary}；先确认止跌和承接，再谈试错，不要只因为价格回落就急着接。`
  }
  return `重点看 ${summary}；回踩之后要确认承接和量能都到位，才考虑从观察升级。`
}

const buySizingLine = (point) => {
  if (isInvalidationWatchActive(point)) return ''
  if (!point?.recommended_shares || !point?.recommended_order_amount) return ''
  const pct = point.recommended_order_pct ? `${(Number(point.recommended_order_pct) * 100).toFixed(0)}%` : null
  const price = point.sizing_reference_price ? Number(point.sizing_reference_price).toFixed(2) : formatPrice(point.buy_current_price)
  const mode = String(point.account_entry_mode || '')
  const modeLabel = mode === 'defense_trial'
    ? '防守试错'
    : mode === 'aggressive_trial'
      ? '进攻试错'
      : '标准执行'
  const head = pct ? `${modeLabel} / 先手仓约 ${pct}` : `${modeLabel} / 先手仓`
  return `${head}：按 ${price} 测算，建议先买 ${formatShares(point.recommended_shares)}，约 ${formatMoney(point.recommended_order_amount)} 元。`
}

const observeActionLine = (point, envTag) => {
  if (isObserveDeepRetraceReference(point)) {
    return '先观察，不抢先手；深回踩位离现价较远，当前先看现价附近别转弱，把远处回踩位只当参考。'
  }
  if (envTag === '防守') {
    return '先观察，不抢先手；只有触发和确认都到位才考虑出手。'
  }
  if (envTag === '弱中性') {
    return '先观察，不抢先手；弱分化环境里只跟最强确认，不把普通观察票升级成执行票。'
  }
  if (envTag === '中性偏谨慎') {
    return '先观察，不抢先手；只有回踩承接和量能确认都到位才考虑出手。'
  }
  return '这只票先看触发，再等确认，不要把观察票当成已执行信号。'
}

const skipReasonLine = (point, envTag) => {
  if (envTag === '防守' && point.buy_comment) {
    return `${point.buy_comment}，今天不作为正常开仓对象。`
  }
  if (envTag === '弱中性' && point.buy_comment) {
    return `${point.buy_comment}，当前环境只保留最强观察位。`
  }
  return point.buy_comment || point.buy_invalid_cond || '不符合执行条件'
}

const openCheckup = (point, defaultTarget = '交易型') => {
  checkupStock.value = {
    tsCode: point.ts_code,
    stockName: point.stock_name || point.ts_code,
    defaultTarget
  }
  checkupVisible.value = true
}

const openBuyAnalysis = (point) => {
  buyAnalysisStock.value = {
    tsCode: point.ts_code,
    stockName: point.stock_name || point.ts_code,
    sourcePoolTag: String(point.stock_pool_tag || ''),
    currentPrice: point.buy_current_price,
    currentChangePct: point.buy_current_change_pct
  }
  buyAnalysisVisible.value = true
}

const clearNotificationQuery = () => {
  const query = { ...route.query }
  delete query.notification_action
  delete query.ts_code
  delete query.stock_name
  router.replace({ query })
}

const matchesTsCode = (point, tsCode) => String(point?.ts_code || '').toUpperCase() === String(tsCode || '').toUpperCase()

const handleNotificationQuery = () => {
  if (!notificationAction.value || !notificationTsCode.value) return
  if (notificationAction.value === 'buy_analysis') {
    const point = [
      ...(buyData.value.available_buy_points || []),
      ...(buyData.value.observe_buy_points || []),
      ...(buyData.value.not_buy_points || []),
    ].find((item) => matchesTsCode(item, notificationTsCode.value))
    openBuyAnalysis(point || {
      ts_code: notificationTsCode.value,
      stock_name: notificationStockName.value || notificationTsCode.value,
      stock_pool_tag: '',
      buy_current_price: null,
      buy_current_change_pct: null,
    })
    clearNotificationQuery()
    return
  }
  if (notificationAction.value === 'checkup') {
    openCheckup({
      ts_code: notificationTsCode.value,
      stock_name: notificationStockName.value || notificationTsCode.value,
    })
    clearNotificationQuery()
  }
}

const clearFocusSector = () => {
  const query = { ...route.query }
  delete query.focus_sector
  delete query.focus_sector_source_type
  router.replace({ query })
}

const setBucketFilter = (bucket) => {
  const nextBucket = String(bucket || '').trim()
  if (!nextBucket) {
    clearBucketFilter()
    return
  }
  const query = { ...route.query, bucket: nextBucket }
  router.replace({ query })
}

const clearBucketFilter = () => {
  const query = { ...route.query }
  delete query.bucket
  delete query.review_bucket
  router.replace({ query })
}

const goToPoolsPage = () => {
  const query = {}
  if (focusSector.value) query.focus_sector = focusSector.value
  if (focusSectorSourceType.value) query.focus_sector_source_type = focusSectorSourceType.value
  if (strategyStyle.value !== 'balanced') query.strategy_style = strategyStyle.value
  if (Object.keys(query).length) {
    router.push({ path: '/pools', query })
    return
  }
  router.push('/pools')
}

const clearReviewFilter = () => {
  const query = { ...route.query }
  delete query.bucket
  delete query.review_bucket
  delete query.review_source
  router.replace({ query })
}

const hardFilterLine = (point) => point.hard_filter_summary || '硬过滤状态未返回'

const loadData = async ({ silent = false, refresh = false } = {}) => {
  if (!silent) loading.value = true
  loadError.value = ''
  try {
    const tradeDate = getLocalDate()
    displayDate.value = tradeDate
    const res = await decisionApi.buyPoint(tradeDate, 30, {
      refresh: Boolean(refresh),
      strategyStyle: strategyStyle.value,
      timeout: BUY_POINT_TIMEOUT,
    })
    const payload = res.data || {}
    const responseCode = payload.code ?? 200
    if (responseCode !== 200 || !payload.data) {
      throw new Error(payload.message || '买点数据加载失败，请刷新重试。')
    }
    applyBuyData(payload.data)
    handleNotificationQuery()
  } catch (error) {
    const message = error?.response?.data?.message || error?.message || '买点数据加载失败，请刷新重试。'
    loadError.value = message
    ElMessage.error(message)
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
  const tradeDate = getLocalDate()
  displayDate.value = tradeDate
  loadData()
  scheduleReviewInsightLoad()
})

watch(strategyStyle, async (nextStyle) => {
  const query = { ...route.query }
  if (nextStyle === 'balanced') {
    delete query.strategy_style
  } else {
    query.strategy_style = nextStyle
  }
  await router.replace({ query })
  loadData()
})

watch(
  () => [
    reviewSourceFilter.value,
    activeBucketFilter.value,
    availablePoints.value.length,
    observePoints.value.length,
    notBuyPoints.value.length,
  ],
  () => {
    const visibleTab = resolveVisibleTab()
    if (activeTab.value === visibleTab) return
    const activeHasItems = (
      (activeTab.value === 'available' && availablePoints.value.length)
      || (activeTab.value === 'observe' && observePoints.value.length)
      || (activeTab.value === 'skip' && notBuyPoints.value.length)
    )
    if (!activeHasItems || reviewSourceFilter.value || activeBucketFilter.value) {
      activeTab.value = visibleTab
    }
  }
)

watch(
  () => [notificationAction.value, notificationTsCode.value, loading.value],
  () => {
    if (loading.value) return
    handleNotificationQuery()
  }
)

watch(
  () => route.query.strategy_style,
  (value) => {
    const normalized = normalizeStrategyStyle(value)
    if (strategyStyle.value !== normalized) {
      strategyStyle.value = normalized
    }
  }
)
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
.header-actions {
  display: flex;
  align-items: center;
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

.style-switch-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.style-switch-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-sec);
}

.style-switch {
  flex-shrink: 0;
}

.load-error {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 120, 120, 0.08);
  border: 1px solid rgba(255, 120, 120, 0.16);
  color: var(--color-text-main);
  font-size: 13px;
}

.no-trade-state {
  display: grid;
  gap: 10px;
  padding: 18px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(224, 32, 32, 0.08), rgba(255, 255, 255, 0.02));
}

.no-trade-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #ff9a9f;
  font-weight: 700;
}

.no-trade-title {
  font-size: 18px;
  font-weight: 700;
}

.no-trade-copy {
  color: var(--color-text-sec);
  line-height: 1.6;
}

.no-trade-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
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
  margin-bottom: 16px;
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

.review-bridge {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(255,255,255,0.02), rgba(255,255,255,0.04));
  border: 1px solid rgba(255,255,255,0.06);
}

.review-bridge-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.review-bridge-title {
  font-size: 15px;
  font-weight: 700;
}

.review-bridge-subtitle {
  margin-top: 6px;
  max-width: 720px;
  color: var(--color-text-sec);
  line-height: 1.6;
}

.review-bridge-summary-chip {
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  color: #8fdcb7;
  background: rgba(60, 188, 125, 0.1);
  border: 1px solid rgba(60, 188, 125, 0.18);
}

.review-bridge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

.review-bridge-card {
  display: grid;
  gap: 10px;
  min-height: 178px;
  padding: 16px;
  border-radius: 14px;
  border: 1px solid var(--color-border);
  background: rgba(255,255,255,0.02);
}

.review-bridge-card-do {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.08);
}

.review-bridge-card-watch {
  box-shadow: inset 0 0 0 1px rgba(255, 196, 64, 0.08);
}

.review-bridge-card-avoid {
  box-shadow: inset 0 0 0 1px rgba(255, 120, 120, 0.08);
}

.review-bridge-card-neutral {
  box-shadow: inset 0 0 0 1px rgba(92, 122, 255, 0.10);
}

.review-bridge-card-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.review-bridge-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--color-text-sec);
  text-transform: uppercase;
}

.review-bridge-metric {
  font-size: 12px;
  color: var(--color-text-sec);
}

.review-bridge-card-title {
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.4;
}

.review-bridge-card-action {
  font-size: 15px;
  line-height: 1.65;
  color: var(--color-text-main);
}

.review-bridge-card-note {
  margin-top: auto;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-sec);
}

.bucket-filter {
  display: grid;
  gap: 12px;
  padding: 16px 18px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.bucket-filter-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.bucket-filter-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-main);
}

.bucket-filter-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-sec);
}

.bucket-filter-summary {
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  color: #9ec2ff;
  background: rgba(92, 122, 255, 0.10);
  border: 1px solid rgba(92, 122, 255, 0.18);
}

.bucket-filter-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.bucket-filter-chip {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-text-sec);
  border-radius: 999px;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  transition: all 0.2s ease;
}

.bucket-filter-chip:hover {
  color: var(--color-text-main);
  border-color: rgba(255, 196, 64, 0.22);
}

.bucket-filter-chip-active {
  color: #ffd06a;
  background: rgba(255, 196, 64, 0.10);
  border-color: rgba(255, 196, 64, 0.22);
  box-shadow: inset 0 0 0 1px rgba(255, 196, 64, 0.10);
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

.available-group-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.available-group-head-secondary {
  margin-top: 20px;
}

.available-group-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-main);
}

.available-group-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-sec);
  line-height: 1.5;
}

.available-group-meta {
  font-size: 12px;
  color: var(--color-text-sec);
  white-space: nowrap;
}

.type-group-stack {
  display: grid;
  gap: 18px;
}

.type-group-stack-secondary {
  margin-top: 0;
}

.type-group {
  display: grid;
  gap: 12px;
}

.type-group-secondary {
  gap: 10px;
}

.type-group-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.type-group-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-main);
}

.type-group-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-sec);
}

.type-group-meta {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--color-text-sec);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.signal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.signal-meta-chip {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.signal-meta-chip-ready {
  color: #7ee2b8;
  background: rgba(54, 196, 131, 0.12);
  border: 1px solid rgba(54, 196, 131, 0.18);
}

.signal-meta-chip-breakthrough {
  color: #ffd06a;
  background: rgba(243, 194, 77, 0.12);
  border: 1px solid rgba(243, 194, 77, 0.18);
}

.signal-meta-chip-deep {
  color: #ff9a9f;
  background: rgba(255, 120, 120, 0.12);
  border: 1px solid rgba(255, 120, 120, 0.18);
}

.signal-meta-chip-wait {
  color: #9ec2ff;
  background: rgba(92, 122, 255, 0.12);
  border: 1px solid rgba(92, 122, 255, 0.18);
}

.signal-grid-secondary {
  margin-top: 0;
}

.signal-card {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.05), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  overflow: hidden;
}

.signal-card-buy {
  box-shadow: inset 0 1px 0 rgba(80, 190, 140, 0.12);
}

.signal-card-standard {
  border-color: rgba(68, 209, 159, 0.18);
  box-shadow:
    inset 0 1px 0 rgba(80, 190, 140, 0.16),
    inset 0 0 0 1px rgba(68, 209, 159, 0.06);
}

.signal-card-aggressive-trial {
  border-color: rgba(243, 194, 77, 0.2);
  box-shadow:
    inset 0 1px 0 rgba(243, 194, 77, 0.18),
    inset 0 0 0 1px rgba(243, 194, 77, 0.06);
}

.signal-card-defense-trial {
  border-color: rgba(245, 110, 128, 0.22);
  box-shadow:
    inset 0 1px 0 rgba(245, 110, 128, 0.18),
    inset 0 0 0 1px rgba(245, 110, 128, 0.08);
}

.signal-card-watch {
  box-shadow: inset 0 1px 0 rgba(243, 194, 77, 0.12);
}

.signal-card-focused {
  box-shadow: inset 0 0 0 1px rgba(84, 210, 164, 0.24);
  border-color: rgba(84, 210, 164, 0.26);
}

.signal-card-review-focused {
  border-color: rgba(255, 196, 64, 0.34);
  box-shadow:
    inset 0 0 0 1px rgba(255, 196, 64, 0.22),
    0 0 0 1px rgba(255, 196, 64, 0.10);
}

.signal-card-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.signal-title-wrap {
  flex: 1;
  min-width: 0;
}

.signal-stock {
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  flex: 0 0 auto;
  max-width: 52%;
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
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.signal-intent {
  padding: 13px 14px;
  border-radius: 14px;
  background: rgba(68, 209, 159, 0.08);
  border: 1px solid rgba(68, 209, 159, 0.14);
  line-height: 1.55;
  font-size: 13px;
}

.signal-sizing {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(68, 209, 159, 0.05);
  border: 1px dashed rgba(68, 209, 159, 0.16);
  color: var(--color-text-main);
  font-size: 12px;
  line-height: 1.55;
}

.signal-sizing-standard {
  background: rgba(68, 209, 159, 0.05);
  border-color: rgba(68, 209, 159, 0.2);
}

.signal-sizing-aggressive-trial {
  background: rgba(243, 194, 77, 0.07);
  border-color: rgba(243, 194, 77, 0.22);
}

.signal-sizing-defense-trial {
  background: rgba(245, 110, 128, 0.07);
  border-color: rgba(245, 110, 128, 0.24);
}

.signal-intent-watch {
  background: rgba(243, 194, 77, 0.08);
  border-color: rgba(243, 194, 77, 0.16);
}

.signal-watch-alert {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(245, 110, 128, 0.08);
  border: 1px solid rgba(245, 110, 128, 0.22);
  color: #ffd7dd;
  display: grid;
  gap: 4px;
}

.signal-watch-alert-watch {
  background: rgba(245, 110, 128, 0.06);
}

.signal-watch-alert-title {
  font-size: 12px;
  font-weight: 700;
}

.signal-watch-alert-copy {
  font-size: 12px;
  line-height: 1.5;
  color: rgba(255, 236, 240, 0.92);
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

.quote-source {
  flex-basis: 100%;
  font-size: 12px;
  color: var(--color-text-sec);
}

.quote-source-live {
  color: #54d2a4;
}

.quote-side {
  display: flex;
  gap: 14px;
  flex-wrap: nowrap;
  justify-content: flex-end;
  align-items: center;
  min-width: max-content;
}

.quote-pair {
  color: var(--color-text-sec);
  font-size: 13px;
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  white-space: nowrap;
  min-width: max-content;
}

.price-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(9, 14, 23, 0.32);
  border: 1px solid rgba(255, 255, 255, 0.04);
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

.condition-summary-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.condition-summary-grid-watch {
  grid-template-columns: 1fr;
}

.condition-summary-card {
  display: grid;
  gap: 8px;
  padding: 14px 15px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-left-width: 3px;
  background: rgba(255, 255, 255, 0.022);
  min-width: 0;
}

.condition-summary-trigger {
  border-left-color: rgba(68, 209, 159, 0.9);
  background: linear-gradient(90deg, rgba(68, 209, 159, 0.08), rgba(255, 255, 255, 0.02) 42%);
}

.condition-summary-confirm {
  border-left-color: rgba(92, 122, 255, 0.9);
  background: linear-gradient(90deg, rgba(92, 122, 255, 0.08), rgba(255, 255, 255, 0.02) 42%);
}

.condition-summary-invalid {
  border-left-color: rgba(255, 122, 127, 0.9);
  background: linear-gradient(90deg, rgba(255, 122, 127, 0.1), rgba(255, 255, 255, 0.02) 42%);
}

.summary-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.summary-card-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.summary-count {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--color-text-sec);
  background: rgba(255, 255, 255, 0.08);
}

.summary-card-body {
  font-size: 13px;
  line-height: 1.55;
  color: var(--color-text-main);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.condition-expand-bar {
  display: flex;
  justify-content: flex-start;
}

.condition-panel-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.condition-panel-grid-watch {
  grid-template-columns: 1fr;
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
  font-size: 14px;
}

.condition-bullets {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  line-height: 1.55;
  font-size: 13px;
}

.condition-bullets-risk li {
  color: #ffc0c4;
}

.signal-footer {
  display: grid;
  gap: 10px;
  color: var(--color-text-sec);
  font-size: 13px;
}

.footer-actions,
.skip-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
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

.skip-quote {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
}

.skip-quote strong {
  font-size: 1.15rem;
  line-height: 1;
}

.skip-meta {
  color: var(--color-text-sec);
  font-size: 13px;
}

.skip-reason {
  color: var(--color-text-sec);
  line-height: 1.5;
}

@media (max-width: 820px) {
  .signal-grid {
    grid-template-columns: 1fr;
  }

  .quote-strip,
  .signal-footer {
    grid-template-columns: 1fr;
    display: grid;
  }

  .quote-side {
    justify-content: flex-start;
    flex-wrap: wrap;
    min-width: 0;
  }

  .price-strip {
    grid-template-columns: 1fr;
  }

  .signal-card-header {
    flex-direction: column;
  }

  .signal-badges {
    justify-content: flex-start;
  }
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
    flex-wrap: wrap;
    min-width: 0;
  }

  .signal-footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .footer-actions {
    justify-content: flex-start;
  }
}
</style>
