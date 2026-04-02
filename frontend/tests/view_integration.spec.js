import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { authState } from '../src/auth'

let routeQuery = {}
let routeMeta = { title: 'Dashboard', requiresAuth: true }
const routerPush = vi.fn()
const routerReplace = vi.fn()
const messageSuccess = vi.fn()
const messageWarning = vi.fn()
const messageError = vi.fn()
const messageInfo = vi.fn()

const decisionApi = {
  buyPoint: vi.fn(),
  reviewStats: vi.fn(),
  summary: vi.fn(),
  sellPoint: vi.fn(),
}

const marketApi = {
  getEnv: vi.fn(),
  getIndex: vi.fn(),
  getStats: vi.fn(),
}

const sectorApi = {
  hot: vi.fn(),
  leader: vi.fn(),
  scan: vi.fn(),
}

const accountApi = {
  overview: vi.fn(),
  profile: vi.fn(),
  deletePosition: vi.fn(),
}

const authApi = {
  ping: vi.fn(),
  login: vi.fn(),
  me: vi.fn(),
  logout: vi.fn(),
}

const adminApi = {
  listAccounts: vi.fn(),
}

const stockApi = {
  pools: vi.fn(),
  detail: vi.fn(),
  buyAnalysis: vi.fn(),
  sellAnalysis: vi.fn(),
}

const taskApi = {
  trigger: vi.fn(),
  status: vi.fn(),
}

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery, meta: routeMeta, path: '/', fullPath: '/' }),
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      success: messageSuccess,
      warning: messageWarning,
      error: messageError,
      info: messageInfo,
    },
  }
})

vi.mock('../src/api', () => ({
  authApi,
  adminApi,
  decisionApi,
  marketApi,
  sectorApi,
  accountApi,
  stockApi,
  taskApi,
}))

const makeResponse = (data) => ({ data: { data } })

const mountView = async (component) => {
  const wrapper = mount(component, {
    global: {
      stubs: {
        BuyAnalysisDrawer: { template: '<div class="buy-analysis-drawer-stub" />' },
        SellAnalysisDrawer: { template: '<div class="sell-analysis-drawer-stub" />' },
        StockCheckupDrawer: { template: '<div class="stock-checkup-drawer-stub" />' },
        SectorTopStocksDrawer: { template: '<div class="sector-top-stocks-drawer-stub" />' },
      },
    },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.localStorage.clear()
  routeQuery = {}
  routeMeta = { title: 'Dashboard', requiresAuth: true }
  routerPush.mockReset()
  routerReplace.mockReset()
  messageSuccess.mockReset()
  messageWarning.mockReset()
  messageError.mockReset()
  messageInfo.mockReset()
  decisionApi.buyPoint.mockReset()
  decisionApi.reviewStats.mockReset()
  decisionApi.summary.mockReset()
  decisionApi.sellPoint.mockReset()
  marketApi.getEnv.mockReset()
  marketApi.getIndex.mockReset()
  marketApi.getStats.mockReset()
  marketApi.getEnv.mockReset()
  sectorApi.hot.mockReset()
  sectorApi.leader.mockReset()
  sectorApi.scan.mockReset()
  accountApi.profile.mockReset()
  accountApi.overview.mockReset()
  accountApi.deletePosition.mockReset()
  authApi.me.mockReset()
  authApi.ping.mockReset()
  authApi.login.mockReset()
  authApi.logout.mockReset()
  adminApi.listAccounts.mockReset()
  stockApi.pools.mockReset()
  stockApi.detail.mockReset()
  stockApi.buyAnalysis.mockReset()
  stockApi.sellAnalysis.mockReset()
  taskApi.trigger.mockReset()
  taskApi.status.mockReset()
  authState.accessToken = ''
  authState.refreshToken = ''
  authState.user = null
  authState.account = null
})

describe('关键页面联调', () => {
  it('普通用户在顶部只显示当前账户展示，不渲染账户切换器', async () => {
    authState.accessToken = 'token'
    authState.refreshToken = 'refresh'
    authState.user = {
      id: 'user-1',
      username: 'hehq',
      display_name: '贺老师',
      role: 'user',
      status: 'active',
    }
    authState.account = {
      id: 'acct-1',
      account_code: 'HE-001',
      account_name: '贺老师的账户',
      status: 'active',
    }
    authApi.me.mockResolvedValue(makeResponse({ user: authState.user, account: authState.account }))

    const { default: App } = await import('../src/App.vue')
    const wrapper = await mount(App)
    await flushPromises()

    expect(wrapper.text()).toContain('我的账户')
    expect(wrapper.text()).toContain('贺老师的账户')
    expect(wrapper.find('.account-switcher').exists()).toBe(false)
  })

  it('管理员在顶部渲染账户切换器', async () => {
    authState.accessToken = 'token'
    authState.refreshToken = 'refresh'
    authState.user = {
      id: 'admin-1',
      username: 'admin',
      display_name: '管理员',
      role: 'admin',
      status: 'active',
    }
    authState.account = {
      id: 'acct-1',
      account_code: 'DEFAULT-001',
      account_name: '默认账户',
      status: 'active',
    }
    authApi.me.mockResolvedValue(makeResponse({ user: authState.user, account: authState.account }))
    adminApi.listAccounts.mockResolvedValue(
      makeResponse({
        accounts: [
          { id: 'acct-1', account_code: 'DEFAULT-001', account_name: '默认账户', status: 'active' },
          { id: 'acct-2', account_code: 'VERIFY-002', account_name: '验证账户', status: 'active' },
        ],
      })
    )

    const { default: App } = await import('../src/App.vue')
    const wrapper = await mount(App)
    await flushPromises()

    expect(adminApi.listAccounts).toHaveBeenCalled()
    expect(wrapper.find('.account-switcher').exists()).toBe(true)
  })

  it('Pools 页面会加载三池和复盘数据，并显示焦点方向文案', async () => {
    routeQuery = { focus_sector: '机器人' }
    marketApi.getEnv.mockResolvedValue(makeResponse({
      market_env_tag: '进攻',
      breakout_allowed: true,
      risk_level: '低',
      market_comment: '市场偏进攻，允许做确认后的主动出手。',
    }))
    stockApi.pools.mockResolvedValue(
      makeResponse({
        trade_date: '2026-03-28',
        resolved_trade_date: '2026-03-27',
        market_watch_pool: [
          {
            ts_code: '000001.SZ',
            stock_name: '机器人一号',
            sector_name: '机器人',
            stock_strength_tag: '强',
            stock_continuity_tag: '可持续',
            stock_tradeability_tag: '可交易',
            stock_core_tag: '核心',
            stock_comment: '先观察这只票是否继续保持强势结构。',
          },
        ],
        trend_recognition_pool: [],
        account_executable_pool: [],
        holding_process_pool: [],
      })
    )
    decisionApi.reviewStats.mockResolvedValue(
      makeResponse({
        bucket_stats: [
          { snapshot_type: 'buy_point', candidate_bucket_tag: '强趋势延续', avg_return_3d: 4.2, count: 5 },
          { snapshot_type: 'buy_point', candidate_bucket_tag: '分歧回封', avg_return_3d: -1.8, count: 4 },
        ],
      })
    )

    const { default: PoolsView } = await import('../src/views/Pools.vue')
    const wrapper = await mountView(PoolsView)

    expect(stockApi.pools).toHaveBeenCalledOnce()
    expect(marketApi.getEnv).toHaveBeenCalledOnce()
    expect(decisionApi.reviewStats).toHaveBeenCalled()
    expect(stockApi.pools).toHaveBeenCalledWith(expect.any(String), 50, expect.objectContaining({ timeout: 90000 }))
    expect(wrapper.text()).toContain('当前按')
    expect(wrapper.text()).toContain('机器人')
    expect(wrapper.text()).toContain('机器人一号')
    expect(wrapper.text()).toContain('账户可参与池')
    expect(wrapper.text()).toContain('市场环境')
  })

  it('Pools 页面点击刷新后会轮询直到拿到最新三池结果', async () => {
    vi.useFakeTimers()
    marketApi.getEnv.mockResolvedValue(makeResponse({
      market_env_tag: '中性',
      breakout_allowed: false,
      risk_level: '中',
      market_comment: '先看确认，不要把观察票当执行票。',
    }))
    stockApi.pools
      .mockResolvedValueOnce(
        makeResponse({
          trade_date: '2026-03-28',
          resolved_trade_date: '2026-03-27',
          market_watch_pool: [
            {
              ts_code: '000001.SZ',
              stock_name: '旧观察票',
              sector_name: '机器人',
              stock_strength_tag: '强',
              stock_continuity_tag: '可持续',
              stock_tradeability_tag: '可交易',
              stock_core_tag: '核心',
            },
          ],
          trend_recognition_pool: [],
          account_executable_pool: [],
          holding_process_pool: [],
          refresh_in_progress: false,
          refresh_requested: false,
          stale_snapshot: false,
        })
      )
      .mockResolvedValueOnce(
        makeResponse({
          trade_date: '2026-03-28',
          resolved_trade_date: '2026-03-27',
          market_watch_pool: [
            {
              ts_code: '000001.SZ',
              stock_name: '旧观察票',
              sector_name: '机器人',
              stock_strength_tag: '强',
              stock_continuity_tag: '可持续',
              stock_tradeability_tag: '可交易',
              stock_core_tag: '核心',
            },
          ],
          trend_recognition_pool: [],
          account_executable_pool: [],
          holding_process_pool: [],
          refresh_in_progress: true,
          refresh_requested: true,
          stale_snapshot: true,
        })
      )
      .mockResolvedValueOnce(
        makeResponse({
          trade_date: '2026-03-28',
          resolved_trade_date: '2026-03-28',
          market_watch_pool: [
            {
              ts_code: '000002.SZ',
              stock_name: '新观察票',
              sector_name: '机器人',
              stock_strength_tag: '强',
              stock_continuity_tag: '可持续',
              stock_tradeability_tag: '可交易',
              stock_core_tag: '核心',
            },
          ],
          trend_recognition_pool: [],
          account_executable_pool: [],
          holding_process_pool: [],
          refresh_in_progress: false,
          refresh_requested: false,
          stale_snapshot: false,
        })
      )
    decisionApi.reviewStats.mockResolvedValue(makeResponse({ bucket_stats: [] }))

    const { default: PoolsView } = await import('../src/views/Pools.vue')
    const wrapper = await mountView(PoolsView)

    expect(wrapper.text()).toContain('旧观察票')

    const refreshButton = wrapper.findAll('button').find((node) => node.text().includes('刷新'))
    await refreshButton.trigger('click')
    await flushPromises()

    expect(messageSuccess).toHaveBeenCalledWith('已触发后台刷新，当前先展示已有三池结果。')

    await vi.advanceTimersByTimeAsync(2500)
    await flushPromises()

    expect(stockApi.pools).toHaveBeenCalledTimes(3)
    expect(wrapper.text()).toContain('新观察票')
    expect(messageSuccess).toHaveBeenCalledWith('三池结果已刷新完成。')
    vi.useRealTimers()
  })

  it('Pools 页面会把账户池拆成标准执行和进攻试错两栏', async () => {
    marketApi.getEnv.mockResolvedValue(makeResponse({
      market_env_tag: '进攻',
      breakout_allowed: true,
      risk_level: '低',
      market_comment: '优先标准执行，强化方向允许小仓试错。',
    }))
    stockApi.pools.mockResolvedValue(makeResponse({
      trade_date: '2026-03-28',
      resolved_trade_date: '2026-03-28',
      market_watch_pool: [],
      trend_recognition_pool: [],
      account_executable_pool: [
        {
          ts_code: '000001.SZ',
          stock_name: '标准执行票',
          sector_name: '机器人',
          account_entry_mode: 'standard',
          pool_entry_reason: '交易性为可交易，且存在回踩确认位，可纳入账户可参与池。',
          next_tradeability_tag: '回踩确认',
          stock_strength_tag: '强',
          structure_state_tag: '修复',
        },
        {
          ts_code: '000002.SZ',
          stock_name: '试错票',
          sector_name: '算力',
          account_entry_mode: 'aggressive_trial',
          pool_entry_reason: '方向强度足够，虽非标准舒服位，但保留小仓进攻试错资格。',
          next_tradeability_tag: '突破确认',
          stock_strength_tag: '强',
          structure_state_tag: '启动',
          direction_signal_tag: '强化中',
        },
      ],
      holding_process_pool: [],
    }))
    decisionApi.reviewStats.mockResolvedValue(makeResponse({ bucket_stats: [] }))

    const { default: PoolsView } = await import('../src/views/Pools.vue')
    const wrapper = await mountView(PoolsView)

    expect(wrapper.text()).toContain('标准执行')
    expect(wrapper.text()).toContain('进攻试错')
    expect(wrapper.text()).toContain('标准执行票')
    expect(wrapper.text()).toContain('试错票')
    expect(wrapper.text()).toContain('回踩确认')
  })

  it('Pools 页面优先按 account_entry_mode 区分标准执行和试错票', async () => {
    marketApi.getEnv.mockResolvedValue(makeResponse({
      market_env_tag: '进攻',
      breakout_allowed: true,
      risk_level: '低',
      market_comment: '优先标准执行，强化方向允许小仓试错。',
    }))
    stockApi.pools.mockResolvedValue(makeResponse({
      trade_date: '2026-03-28',
      resolved_trade_date: '2026-03-28',
      market_watch_pool: [],
      trend_recognition_pool: [],
      account_executable_pool: [
        {
          ts_code: '000003.SZ',
          stock_name: '结构化试错票',
          sector_name: '机器人',
          account_entry_mode: 'aggressive_trial',
          pool_entry_reason: '交易性为可交易，且存在回踩确认位，可纳入账户可参与池。',
          next_tradeability_tag: '回踩确认',
          stock_strength_tag: '强',
          structure_state_tag: '修复',
        },
      ],
      holding_process_pool: [],
    }))
    decisionApi.reviewStats.mockResolvedValue(makeResponse({ bucket_stats: [] }))

    const { default: PoolsView } = await import('../src/views/Pools.vue')
    const wrapper = await mountView(PoolsView)

    expect(wrapper.text()).toContain('进攻试错')
    expect(wrapper.text()).toContain('结构化试错票')
    expect(wrapper.text()).toContain('试错仓 / 小仓')
  })

  it('Pools 页面会把防守试错和进攻试错分开统计', async () => {
    marketApi.getEnv.mockResolvedValue(makeResponse({
      market_env_tag: '防守',
      breakout_allowed: false,
      risk_level: '高',
      market_comment: '防守环境只保留极少数轻仓试错。',
    }))
    stockApi.pools.mockResolvedValue(makeResponse({
      trade_date: '2026-03-28',
      resolved_trade_date: '2026-03-28',
      market_watch_pool: [],
      trend_recognition_pool: [],
      account_executable_pool: [
        {
          ts_code: '000004.SZ',
          stock_name: '防守试错票',
          sector_name: '银行',
          account_entry_mode: 'defense_trial',
          pool_entry_reason: '防守日仅保留最强核心股试错',
          next_tradeability_tag: '突破确认',
          stock_strength_tag: '强',
          structure_state_tag: '修复',
        },
      ],
      holding_process_pool: [],
    }))
    decisionApi.reviewStats.mockResolvedValue(makeResponse({ bucket_stats: [] }))

    const { default: PoolsView } = await import('../src/views/Pools.vue')
    const wrapper = await mountView(PoolsView)

    expect(wrapper.text()).toContain('进攻试错')
    expect(wrapper.text()).toContain('防守试错')
    expect(wrapper.text()).toContain('当前没有需要额外放宽的小仓试错票')
    expect(wrapper.text()).toContain('防守试错票')
    expect(wrapper.text()).toContain('防守仓 / 更小仓')
  })

  it('BuyPoint 页面会加载买点和复盘数据，并展示主执行名单', async () => {
    routeQuery = { focus_sector: '机器人' }
    decisionApi.buyPoint.mockResolvedValue(
      makeResponse({
        market_env_tag: '进攻',
        available_buy_points: [
          {
            ts_code: '300024.SZ',
            stock_name: '机器人先锋',
            sector_name: '机器人',
            stock_pool_tag: '账户可参与池',
            candidate_bucket_tag: '强趋势延续',
            candidate_source_tag: '机器人',
            buy_point_type: '回踩承接',
            buy_risk_level: '中',
            buy_account_fit: '适合',
            buy_trigger_cond: '回踩 5 日线',
            buy_confirm_cond: '量比放大；承接稳定',
            buy_invalid_cond: '跌破前低',
            buy_comment: '分时回踩后可考虑试单',
            buy_current_price: 21.35,
            buy_current_change_pct: 2.8,
            buy_trigger_gap_pct: -0.6,
            buy_invalid_gap_pct: -3.1,
            buy_trigger_price: 21.1,
            buy_invalid_price: 20.2,
            buy_required_volume_ratio: 1.5,
          },
        ],
        observe_buy_points: [],
        not_buy_points: [],
      })
    )
    decisionApi.reviewStats.mockResolvedValue(
      makeResponse({
        bucket_stats: [
          { snapshot_type: 'buy_point', candidate_bucket_tag: '强趋势延续', avg_return_3d: 5.1, count: 6 },
          { snapshot_type: 'buy_point', candidate_bucket_tag: '高位博弈', avg_return_3d: -2.0, count: 4 },
        ],
      })
    )

    const { default: BuyPointView } = await import('../src/views/BuyPoint.vue')
    const wrapper = await mountView(BuyPointView)
    await new Promise((resolve) => window.setTimeout(resolve, 220))
    await flushPromises()

    expect(decisionApi.buyPoint).toHaveBeenCalledOnce()
    expect(decisionApi.reviewStats).toHaveBeenCalled()
    expect(decisionApi.buyPoint).toHaveBeenCalledWith(expect.any(String), 30, expect.objectContaining({ timeout: 90000 }))
    expect(wrapper.text()).toContain('买点分析')
    expect(wrapper.text()).toContain('机器人先锋')
    expect(wrapper.text()).toContain('主执行名单')
  })

  it('BuyPoint 页面会展示后端返回的真实失败原因', async () => {
    decisionApi.buyPoint.mockResolvedValue({
      data: {
        code: 500,
        message: '买点分析失败: unexpected connection_lost() call',
        data: null,
      },
    })
    decisionApi.reviewStats.mockResolvedValue(makeResponse({ bucket_stats: [] }))

    const { default: BuyPointView } = await import('../src/views/BuyPoint.vue')
    const wrapper = await mountView(BuyPointView)

    expect(wrapper.text()).toContain('买点分析失败: unexpected connection_lost() call')
    expect(messageError).toHaveBeenCalledWith('买点分析失败: unexpected connection_lost() call')
  })

  it('Market 页面会在实时市场状态不可用时显示明确提示', async () => {
    marketApi.getEnv.mockResolvedValue(makeResponse({
      trade_date: '2026-03-31',
      resolved_trade_date: '2026-03-31',
      market_env_tag: '中性',
      breakout_allowed: false,
      risk_level: '中',
      market_comment: '市场中性，指数和情绪都没有形成明显主导；指数侧暂无明显失真，但强弱差距不大；先等确认，不抢突破，优先做更舒服的回踩或分歧转强',
      index_score: 52,
      sentiment_score: 50,
      overall_score: 51,
    }))
    marketApi.getIndex.mockResolvedValue(makeResponse({
      trade_date: '2026-03-31',
      resolved_trade_date: '2026-03-31',
      indexes: [],
    }))
    marketApi.getStats.mockResolvedValue(makeResponse({
      trade_date: '2026-03-31',
      resolved_trade_date: '2026-03-31',
      realtime_status: 'unavailable',
      realtime_is_stale: false,
      realtime_stale_from_quote_time: '2026-03-31 10:01:00',
      limit_up_count: 0,
      limit_down_count: 0,
      broken_board_rate: 0,
      market_turnover: null,
      up_down_ratio: { up: 0, down: 0, flat: 0, total: 0 },
      limit_stats_data_source: 'unavailable',
      turnover_data_source: 'unavailable',
      up_down_data_source: 'unavailable',
    }))

    const { default: MarketView } = await import('../src/views/Market.vue')
    const wrapper = await mountView(MarketView)

    expect(wrapper.text()).toContain('实时市场状态暂不可用')
    expect(wrapper.text()).toContain('主源与兜底链路当前都不可用')
    expect(wrapper.text()).toContain('市场结论')
    expect(wrapper.text()).toContain('主要依据')
    expect(wrapper.text()).toContain('操作建议')
  })

  it('Sectors 页面会加载新浪热榜并展示热门行业和概念', async () => {
    sectorApi.scan.mockResolvedValue(makeResponse({
      trade_date: '2026-04-01',
      resolved_trade_date: '2026-04-01',
      sector_data_mode: 'hybrid',
      threshold_profile: 'attack',
      mainline_sectors: [
        {
          sector_name: '创新药',
          sector_source_type: 'industry',
          sector_change_pct: 4.8,
          sector_score: 91,
          sector_strength_rank: 1,
          sector_mainline_tag: '主线',
          sector_continuity_tag: '可持续',
          sector_tradeability_tag: '可交易',
          sector_continuity_days: 3,
          sector_reason_tags: ['主线加强'],
          sector_comment: '主线继续走强',
          sector_summary_reason: '医药分支最强',
          sector_tier: 'A',
          sector_action_hint: '可执行',
        },
      ],
      sub_mainline_sectors: [],
      follow_sectors: [],
      trash_sectors: [],
      total_sectors: 1,
    }))
    sectorApi.hot.mockResolvedValue(makeResponse({
      trade_date: '2026-04-01',
      resolved_trade_date: '2026-04-01',
      data_source: 'sina_hot_sector',
      leader_boards: [
        { sector_id: 'chgn_701272', sector_name: 'NPU', sector_source_type: 'leader', sector_change_pct: 5.74, leader_stock_name: '芯原股份', leader_stock_ts_code: '688521.SH', stock_count: 11, quote_time: '2026-04-01 11:29:00' },
      ],
      industry_boards: [
        { sector_id: 'sw2_370100', sector_name: '化学制药', sector_source_type: 'industry', sector_change_pct: 4.96, leader_stock_name: '广生堂', leader_stock_ts_code: '300436.SZ', stock_count: 158, quote_time: '2026-04-01 11:29:00' },
      ],
      concept_boards: [
        { sector_id: 'chgn_701272', sector_name: 'NPU', sector_source_type: 'concept', sector_change_pct: 5.74, leader_stock_name: '芯原股份', leader_stock_ts_code: '688521.SH', stock_count: 11, quote_time: '2026-04-01 11:29:00' },
      ],
    }))
    marketApi.getEnv.mockResolvedValue(makeResponse({
      market_env_tag: '进攻',
      overall_score: 76.5,
    }))

    const { default: SectorsView } = await import('../src/views/Sectors.vue')
    const wrapper = await mountView(SectorsView)

    expect(sectorApi.scan).toHaveBeenCalledOnce()
    expect(sectorApi.hot).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('新浪热榜')
    expect(wrapper.text()).toContain('热门行业')
    expect(wrapper.text()).toContain('热门概念')
    expect(wrapper.text()).toContain('化学制药')
    expect(wrapper.text()).toContain('芯原股份')
  })

  it('BuyAnalysisDrawer 会在加载失败时显示真实错误，不再只显示空态', async () => {
    stockApi.buyAnalysis.mockResolvedValue({
      data: {
        code: 500,
        message: '获取买点分析失败: 目标股票不存在于候选上下文',
        data: null,
      },
    })

    const { default: BuyAnalysisDrawer } = await import('../src/components/BuyAnalysisDrawer.vue')
    const wrapper = mount(BuyAnalysisDrawer, {
      props: {
        modelValue: false,
        tsCode: '002025.SZ',
        stockName: '航天电器',
        tradeDate: '2026-03-30',
      },
    })
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    await flushPromises()

    expect(stockApi.buyAnalysis).toHaveBeenCalledWith('002025.SZ', '2026-03-30', { timeout: 90000 })
    expect(wrapper.text()).toContain('获取买点分析失败: 目标股票不存在于候选上下文')
    expect(wrapper.text()).toContain('买点 SOP 加载失败')
    expect(messageError).toHaveBeenCalledWith('获取买点分析失败: 目标股票不存在于候选上下文')
  })

  it('SellAnalysisDrawer 会在加载失败时显示真实错误，不再只显示空态', async () => {
    stockApi.sellAnalysis.mockResolvedValue({
      data: {
        code: 500,
        message: '获取卖点分析失败: 当前持仓不存在于账户上下文',
        data: null,
      },
    })

    const { default: SellAnalysisDrawer } = await import('../src/components/SellAnalysisDrawer.vue')
    const wrapper = mount(SellAnalysisDrawer, {
      props: {
        modelValue: false,
        tsCode: '601012.SH',
        stockName: '隆基绿能',
        tradeDate: '2026-03-31',
      },
    })
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    await flushPromises()

    expect(stockApi.sellAnalysis).toHaveBeenCalledWith('601012.SH', '2026-03-31', { timeout: 90000 })
    expect(wrapper.text()).toContain('获取卖点分析失败: 当前持仓不存在于账户上下文')
    expect(wrapper.text()).toContain('卖点 SOP 加载失败')
    expect(messageError).toHaveBeenCalledWith('获取卖点分析失败: 当前持仓不存在于账户上下文')
  })

  it('BuyAnalysisDrawer 会展示加仓决策与仓位推进建议', async () => {
    stockApi.buyAnalysis.mockResolvedValue({
      data: {
        code: 200,
        data: {
          trade_date: '2026-03-31',
          resolved_trade_date: '2026-03-31',
          stock_found_in_candidates: true,
          basic_info: {
            ts_code: '002025.SZ',
            stock_name: '航天电器',
            sector_name: '军工电子',
            market_env_tag: '进攻',
            stable_market_env_tag: '进攻',
            realtime_market_env_tag: '进攻',
            buy_signal_tag: '可买',
            buy_point_type: '回踩承接',
            candidate_bucket_tag: '趋势回踩',
            quote_time: '2026-03-31 10:35:00',
            data_source: 'realtime_sina',
          },
          account_context: {
            position_status: '轻仓（仓位 28%）',
            same_direction_exposure: '已有同一只股票持仓，属于加仓语境。',
            current_use: '加仓',
            market_suitability: '市场允许主动试错，但仍要先等分时确认。',
            account_conclusion: '已有同一只股票持仓，只能按加仓语境处理',
          },
          daily_judgement: {
            current_stage: '启动',
            buy_signal: '回踩承接，可买',
            buy_point_level: 'A',
            reason: '趋势向上',
            risk_items: [],
            reference_levels: [],
          },
          intraday_judgement: {
            price_vs_avg_line: '站均价线上',
            intraday_structure: '回踩承接',
            volume_quality: '实时放量跟随（相对放量 1.9）',
            key_level_status: '仍在支撑位 27.80 上方。',
            conclusion: '买',
            note: '承接清楚。',
          },
          order_plan: {
            low_absorb_price: '27.80-27.95',
            breakout_price: '28.35-28.48',
            retrace_confirm_price: '28.05-28.18',
            give_up_price: '28.90',
            trigger_condition: '回踩确认后再加',
            invalid_condition: '跌破支撑就放弃',
            above_no_chase: '28.90',
            below_no_buy: '27.20',
          },
          add_position_decision: {
            eligible: true,
            decision: '可加',
            score_total: 9,
            trend_score: 2,
            position_score: 2,
            volume_price_score: 2,
            sector_sentiment_score: 2,
            account_risk_score: 1,
            trigger_scene: '回踩确认',
            blockers: [],
            reason: '回踩确认 已较明确，底仓已有利润垫，可以按计划扩大正确头寸。',
          },
          position_advice: {
            suggestion: '标准加仓',
            reason: '回踩确认 已较明确，底仓已有利润垫，可以按计划扩大正确头寸。',
            invalidation_level: '27.20',
            invalidation_action: '新增仓失效先撤。',
            plan_position_pct: 0.5,
            increment_position_pct: 0.2,
            max_position_pct: 0.8,
            risk_control_action: '加仓失败先撤新增仓，不把舒服单拖成高波动重仓单。',
            exit_priority: '先撤新增仓',
          },
          execution: {
            action: '加',
            reason: '回踩确认 已较明确，底仓已有利润垫，可以按计划扩大正确头寸。',
          },
        },
      },
    })

    const { default: BuyAnalysisDrawer } = await import('../src/components/BuyAnalysisDrawer.vue')
    const wrapper = mount(BuyAnalysisDrawer, {
      props: {
        modelValue: false,
        tsCode: '002025.SZ',
        stockName: '航天电器',
        tradeDate: '2026-03-31',
      },
    })
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('加仓决策')
    expect(wrapper.text()).toContain('标准加仓')
    expect(wrapper.text()).toContain('回踩确认')
    expect(wrapper.text()).toContain('50%')
    expect(wrapper.text()).toContain('先撤新增仓')
  })

  it('BuyAnalysisDrawer 在深回踩价位离现价过远时，不会把回踩确认区当成主路径', async () => {
    stockApi.buyAnalysis.mockResolvedValue({
      data: {
        code: 200,
        data: {
          trade_date: '2026-04-02',
          resolved_trade_date: '2026-04-02',
          stock_found_in_candidates: true,
          basic_info: {
            ts_code: '300436.SZ',
            stock_name: '广生堂',
            sector_name: '化学制药',
            market_env_tag: '防守',
            stable_market_env_tag: '进攻',
            realtime_market_env_tag: '防守',
            buy_signal_tag: '观察',
            buy_point_type: '回踩承接',
            candidate_bucket_tag: '强势确认',
            quote_time: '2026-04-02 11:30:00',
            data_source: 'realtime_sina',
          },
          account_context: {
            position_status: '轻仓（仓位 9%）',
            same_direction_exposure: '暂无明显同方向重复暴露。',
            current_use: '新开仓',
            market_suitability: '市场偏防守，只能低吸或回踩确认，不能追高。',
            account_conclusion: '轻仓新开仓，可试错',
          },
          daily_judgement: {
            current_stage: '加速',
            buy_signal: '回踩承接，观察',
            buy_point_level: 'C',
            reason: '日线更多是观察位，不适合直接下单',
            risk_items: ['接近前高/20日区间压力，不适合无脑追。'],
            reference_levels: [],
          },
          intraday_judgement: {
            price_vs_avg_line: '站均价线上',
            intraday_structure: '回踩承接',
            volume_quality: '实时放量跟随（相对放量 3.9）',
            key_level_status: '已到突破关键位 119.60 一带。',
            conclusion: '等确认',
            note: '承接仍需观察。',
          },
          order_plan: {
            low_absorb_price: '121.05-122.02',
            breakout_price: '130.79-131.83',
            retrace_confirm_price: '104.06-104.89',
            give_up_price: '131.18',
            trigger_condition: '优先看回踩 121.05-122.02 一带是否缩量承接；若直接走强，则放量过 130.79-131.83 并站稳再考虑。',
            invalid_condition: '跌破 98.01 且无法快速收回，就视为买点失效。',
            above_no_chase: '131.18',
            below_no_buy: '98.01',
          },
          add_position_decision: {
            eligible: false,
            decision: '不加',
            reason: '当前不是加仓语境，这里仍按新开仓逻辑处理。',
          },
          position_advice: {
            suggestion: '轻仓试错',
            reason: '买点还需要盘中确认或账户已有约束，只适合试错仓位。',
            invalidation_level: '98.01',
            invalidation_action: '跌破失效位后放弃。',
          },
          execution: {
            action: '等',
            reason: '日线可以继续看，但分时确认还没到位，先按计划等触发。',
          },
        },
      },
    })

    const { default: BuyAnalysisDrawer } = await import('../src/components/BuyAnalysisDrawer.vue')
    const wrapper = mount(BuyAnalysisDrawer, {
      props: {
        modelValue: false,
        tsCode: '300436.SZ',
        stockName: '广生堂',
        tradeDate: '2026-04-02',
        currentPrice: 127,
        currentChangePct: 6.7,
      },
    })
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('深回踩参考位')
    expect(wrapper.text()).toContain('当前先不把它当执行位')
    expect(wrapper.text()).toContain('当前先等低吸区出现，不要在中间位硬接')
    expect(wrapper.text()).toContain('这条离现价较远，更像深回踩理想位')
    expect(wrapper.text()).not.toContain('当前更重要的是等价格回踩到 104.06-104.89 一带')
  })

  it('Dashboard 页面会串起摘要、市场、板块、账户和买卖信号接口', async () => {
    marketApi.getEnv.mockResolvedValue(makeResponse({
      market_env_tag: '进攻',
      market_comment: '市场偏进攻，指数与情绪基本同向走强；涨停 68 家且炸板率仅 11.0%，涨跌家数比 2.67，赚钱效应占优；允许做强势突破，优先主线和强更强，不做后排跟风',
      breakout_allowed: true,
      risk_level: '低',
    }))
    decisionApi.summary.mockResolvedValue(makeResponse({
      today_action: '适度积极',
      market_env_tag: '进攻',
      account_action_tag: '可开新仓',
      priority_action: '先看主线强势股',
      focus: '机器人与算力',
      avoid: '高位弱转强失败票',
    }))
    sectorApi.leader.mockResolvedValue(makeResponse({
      sector: {
        sector_name: '机器人',
        sector_change_pct: 5.6,
        sector_mainline_tag: '主线',
      },
    }))
    accountApi.profile.mockResolvedValue(makeResponse({
      total_asset: 500000,
      available_cash: 200000,
      total_position_ratio: 0.6,
      holding_count: 4,
    }))
    decisionApi.buyPoint.mockResolvedValue(makeResponse({
      available_buy_points: [{ ts_code: '300024.SZ', stock_name: '机器人先锋' }],
      observe_buy_points: [],
      not_buy_points: [],
    }))
    decisionApi.sellPoint.mockResolvedValue(makeResponse({
      sell_positions: [{ ts_code: '600001.SH', stock_name: '示例持仓', sell_signal_tag: '卖出', sell_point_type: '破位' }],
      reduce_positions: [],
    }))
    decisionApi.reviewStats.mockResolvedValue(makeResponse({
      bucket_stats: [{ snapshot_type: 'buy_point', candidate_bucket_tag: '强趋势延续', count: 3 }],
    }))

    const { default: DashboardView } = await import('../src/views/Dashboard.vue')
    const wrapper = await mountView(DashboardView)

    expect(marketApi.getEnv).toHaveBeenCalledOnce()
    expect(decisionApi.summary).toHaveBeenCalledOnce()
    expect(sectorApi.leader).toHaveBeenCalledOnce()
    expect(accountApi.profile).toHaveBeenCalledOnce()
    expect(decisionApi.buyPoint).toHaveBeenCalledOnce()
    expect(decisionApi.sellPoint).toHaveBeenCalledOnce()
    expect(decisionApi.reviewStats).toHaveBeenCalled()
    expect(messageSuccess).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('今日执行摘要')
    expect(wrapper.text()).toContain('适度积极')
    expect(wrapper.text()).toContain('机器人')
    expect(wrapper.text()).toContain('50.00万')
    expect(wrapper.text()).toContain('市场结论')
    expect(wrapper.text()).toContain('主要依据')
    expect(wrapper.text()).toContain('操作建议')
  })

  it('TaskRuns 页面会加载最近任务记录并支持手动触发', async () => {
    taskApi.status
      .mockResolvedValueOnce({
        data: {
          tasks: [
            {
              id: 'task-1',
              mode: 'daily',
              trade_date: '2026-03-28',
              trigger_source: 'manual',
              status: 'failed',
              attempt_count: 2,
              max_attempts: 2,
              duration_ms: 1800,
              result: null,
              last_error: 'notify failed',
              created_at: '2026-03-28T10:00:00',
              updated_at: '2026-03-28T10:02:00',
              started_at: '2026-03-28T10:00:02',
              finished_at: '2026-03-28T10:02:00',
            },
          ],
        },
      })
      .mockResolvedValueOnce({
        data: {
          task: {
            id: 'task-1',
            mode: 'daily',
            trade_date: '2026-03-28',
            trigger_source: 'manual',
            status: 'success',
            attempt_count: 2,
            max_attempts: 2,
            duration_ms: 1800,
            last_error: '',
            created_at: '2026-03-28T10:00:00',
            updated_at: '2026-03-28T10:02:00',
            started_at: '2026-03-28T10:00:02',
            finished_at: '2026-03-28T10:02:00',
            result_summary: {
              pipeline: 'daily',
              today_action: '可适度出手',
              priority_action: '先看核心票',
              market_env_tag: '进攻',
              market_comment: '题材扩散',
              available_buy_count: 2,
              sell_signal_count: 1,
              candidate_pool_count: 6,
            },
            result: {
              pipeline: 'daily',
              report: {
                market_env: {
                  market_env_tag: '进攻',
                  market_comment: '题材扩散',
                },
                summary: {
                  today_action: '可适度出手',
                  priority_action: '先看核心票',
                },
                buy_analysis: {
                  available_buy_points: [{ ts_code: '300024.SZ' }, { ts_code: '300025.SZ' }],
                },
                sell_analysis: {
                  sell_positions: [{ ts_code: '600001.SH' }],
                  reduce_positions: [],
                },
                stock_pools: {
                  market_watch_count: 3,
                  trend_recognition_count: 2,
                  account_executable_count: 1,
                },
              },
            },
          },
        },
      })
      .mockResolvedValue({
        data: {
          tasks: [],
        },
      })
    taskApi.trigger.mockResolvedValue({
      data: {
        status: 'started',
        message: '任务已启动，模式: daily, 日期: 2026-03-28',
        task_id: 'task-2',
      },
    })

    const { default: TaskRunsView } = await import('../src/views/TaskRuns.vue')
    const wrapper = await mountView(TaskRunsView)

    expect(taskApi.status).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('任务调度')
    expect(wrapper.text()).toContain('失败次数')
    expect(wrapper.text()).toContain('1')

    await wrapper.vm.openTaskDetail({
      id: 'task-1',
      mode: 'daily',
      trade_date: '2026-03-28',
      trigger_source: 'manual',
      status: 'failed',
      attempt_count: 2,
      max_attempts: 2,
      duration_ms: 1800,
      result: null,
      last_error: 'notify failed',
      created_at: '2026-03-28T10:00:00',
      updated_at: '2026-03-28T10:02:00',
      started_at: '2026-03-28T10:00:02',
      finished_at: '2026-03-28T10:02:00',
    })
    await flushPromises()

    expect(taskApi.status).toHaveBeenNthCalledWith(2, { task_id: 'task-1' })
    expect(wrapper.text()).toContain('可适度出手')
    expect(wrapper.text()).toContain('进攻')
    expect(wrapper.text()).toContain('候选池规模')

    await wrapper.findAll('button').find((node) => node.text().includes('完整流程'))?.trigger('click')
    await flushPromises()

    expect(taskApi.trigger).toHaveBeenCalledWith({
      mode: 'daily',
      trade_date: expect.any(String),
      force: false,
    })
    expect(messageSuccess).toHaveBeenCalled()
  })

  it('SellPoint 页面会在持有观察里显示加仓提示', async () => {
    decisionApi.sellPoint.mockResolvedValue(makeResponse({
      sell_positions: [],
      reduce_positions: [],
      hold_positions: [
        {
          ts_code: '002463.SZ',
          stock_name: '沪电股份',
          sell_signal_tag: '持有',
          sell_point_type: '减仓',
          sell_priority: '低',
          sell_reason: '趋势未坏',
          sell_comment: '继续观察',
          sell_trigger_cond: '跌破支撑再处理',
          pnl_pct: 2.3,
          holding_qty: 200,
          holding_days: 5,
          market_price: 30.6,
          cost_price: 29.9,
          can_sell_today: true,
          add_signal_tag: '建议加仓',
          add_signal_reason: '日线通过，分时也出现了相对明确的转强/承接信号。',
        },
        {
          ts_code: '000001.SZ',
          stock_name: '平安银行',
          sell_signal_tag: '持有',
          sell_point_type: '减仓',
          sell_priority: '低',
          sell_reason: '趋势未坏',
          sell_comment: '继续观察',
          sell_trigger_cond: '跌破支撑再处理',
          pnl_pct: 0.8,
          holding_qty: 100,
          holding_days: 5,
          market_price: 12.1,
          cost_price: 12.0,
          can_sell_today: true,
          add_signal_tag: '仅可小加',
          add_signal_reason: '结构还不错，但位置和利润垫只支持小步推进。',
        },
      ],
      llm_status: null,
    }))

    const { default: SellPointView } = await import('../src/views/SellPoint.vue')
    const wrapper = await mountView(SellPointView)

    expect(decisionApi.sellPoint).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('建议加仓')
    expect(wrapper.text()).toContain('仅可小加')
    expect(wrapper.text()).toContain('查看加仓分析')
  })

  it('SellPoint 页面点击刷新会显式跳过短缓存', async () => {
    decisionApi.sellPoint.mockResolvedValue(makeResponse({
      sell_positions: [],
      reduce_positions: [],
      hold_positions: [],
      llm_status: null,
    }))

    const { default: SellPointView } = await import('../src/views/SellPoint.vue')
    const wrapper = await mountView(SellPointView)

    const refreshButton = wrapper.findAll('button').find((node) => node.text().includes('刷新'))
    expect(refreshButton).toBeTruthy()
    await refreshButton.trigger('click')
    await flushPromises()

    expect(decisionApi.sellPoint).toHaveBeenNthCalledWith(
      2,
      expect.any(String),
      expect.objectContaining({ refresh: true, forceLlmRefresh: false, includeLlm: true }),
    )
  })

  it('SellPoint 页面首次加载会请求 LLM 解读', async () => {
    decisionApi.sellPoint.mockResolvedValue(makeResponse({
      sell_positions: [],
      reduce_positions: [],
      hold_positions: [],
      llm_status: { enabled: true, success: true, status: 'success', message: 'LLM 解释增强已生效' },
    }))

    const { default: SellPointView } = await import('../src/views/SellPoint.vue')
    await mountView(SellPointView)

    expect(decisionApi.sellPoint).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ includeLlm: true, forceLlmRefresh: false }),
    )
  })

  it('SellPoint 页面不会被 Dashboard 的无 LLM 缓存污染，且会保留已有 LLM 解读', async () => {
    authState.account = {
      id: 'acct-1',
      account_code: 'DEFAULT-001',
      account_name: '默认账户',
      status: 'active',
    }
    const today = new Date()
    const tradeDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
    window.sessionStorage.setItem(
      `sell_point_snapshot_v2:acct-1:${tradeDate}`,
      JSON.stringify({
        displayDate: tradeDate,
        activeTab: 'sell',
        updatedAt: Date.now(),
        sellData: {
          sell_positions: [
            {
              ts_code: '600089.SH',
              stock_name: '特变电工',
              sell_signal_tag: '卖出',
              sell_point_type: '止损',
              sell_priority: '高',
              sell_reason: '结构走弱',
              sell_comment: '优先处理',
              sell_trigger_cond: '跌破关键位卖出',
              pnl_pct: -16.01,
              holding_qty: 200,
              holding_days: 31,
              market_price: 26.17,
              cost_price: 31.16,
              can_sell_today: true,
              llm_plain_note: '缓存里的正确解读。',
            },
          ],
          reduce_positions: [],
          hold_positions: [],
          llm_summary: { page_summary: '缓存摘要', action_summary: '缓存动作摘要' },
          llm_status: { enabled: true, success: true, status: 'cached', message: 'LLM 解读已命中缓存' },
        },
      }),
    )
    window.sessionStorage.setItem(
      'dashboard_snapshot_v2:acct-1',
      JSON.stringify({
        updatedAt: Date.now(),
        sellPoints: {
          sell_positions: [
            {
              ts_code: '600089.SH',
              stock_name: '特变电工',
              sell_signal_tag: '卖出',
              sell_point_type: '止损',
              sell_priority: '高',
              sell_reason: 'Dashboard 无 LLM 数据',
              sell_comment: '优先处理',
              sell_trigger_cond: '跌破关键位卖出',
              pnl_pct: -16.01,
              holding_qty: 200,
              holding_days: 31,
              market_price: 26.17,
              cost_price: 31.16,
              can_sell_today: true,
            },
          ],
          reduce_positions: [],
          hold_positions: [],
          llm_status: null,
        },
      }),
    )
    decisionApi.sellPoint.mockResolvedValue(makeResponse({
      sell_positions: [
        {
          ts_code: '600089.SH',
          stock_name: '特变电工',
          sell_signal_tag: '卖出',
          sell_point_type: '止损',
          sell_priority: '高',
          sell_reason: '接口返回但未带 LLM',
          sell_comment: '优先处理',
          sell_trigger_cond: '跌破关键位卖出',
          pnl_pct: -16.01,
          holding_qty: 200,
          holding_days: 31,
          market_price: 26.17,
          cost_price: 31.16,
          can_sell_today: true,
        },
      ],
      reduce_positions: [],
      hold_positions: [],
      llm_status: { enabled: true, success: false, status: 'timeout', message: '模型请求超时' },
    }))

    const { default: SellPointView } = await import('../src/views/SellPoint.vue')
    const wrapper = await mountView(SellPointView)

    expect(wrapper.text()).toContain('缓存里的正确解读。')
    expect(wrapper.text()).not.toContain('Dashboard 无 LLM 数据')
  })

  it('SellPoint 卡片点击刷新价格会更新当前价格', async () => {
    decisionApi.sellPoint.mockResolvedValue(makeResponse({
      sell_positions: [
        {
          ts_code: '600001.SH',
          stock_name: '示例持仓',
          sell_signal_tag: '卖出',
          sell_point_type: '破位',
          sell_priority: '高',
          sell_reason: '跌破结构',
          sell_comment: '优先处理',
          sell_trigger_cond: '反弹无力卖出',
          pnl_pct: 5.0,
          holding_qty: 100,
          holding_days: 5,
          market_price: 10.0,
          cost_price: 9.5,
          can_sell_today: true,
        },
      ],
      reduce_positions: [],
      hold_positions: [],
      llm_status: null,
    }))
    stockApi.detail.mockResolvedValue(makeResponse({
      trade_date: '2026-03-30',
      stock: {
        ts_code: '600001.SH',
        stock_name: '示例持仓',
        close: 10.6,
        quote_time: '2026-03-30 10:15:00',
        data_source: 'realtime_sina',
      },
    }))

    const { default: SellPointView } = await import('../src/views/SellPoint.vue')
    const wrapper = await mountView(SellPointView)

    const refreshButtons = wrapper.findAll('button').filter((node) => node.text().includes('刷新价格'))
    expect(refreshButtons.length).toBeGreaterThan(0)
    await refreshButtons[0].trigger('click')
    await flushPromises()

    expect(stockApi.detail).toHaveBeenCalledWith('600001.SH', expect.any(String))
    expect(wrapper.text()).toContain('10.60 / 9.50')
  })

  it('Account 页面删除持仓时使用页内确认弹窗', async () => {
    accountApi.overview.mockResolvedValue({
      data: {
        data: {
          profile: {
            total_asset: 100000,
            available_cash: 50000,
            market_value: 50000,
            total_pnl_amount: 0,
            today_pnl_amount: 0,
            total_position_ratio: 0.5,
            holding_count: 1,
            t1_locked_count: 0,
          },
          status: {
            can_trade: true,
            action: '可执行',
            priority: '保持节奏',
          },
          positions: [
            {
              id: 1,
              ts_code: '002463.SZ',
              stock_name: '沪电股份',
              holding_qty: 100,
              cost_price: 30,
              market_price: 31,
              holding_market_value: 3100,
              holding_days: 3,
              pnl_amount: 100,
              today_pnl_amount: 20,
              pnl_pct: 3.33,
              buy_date: '2026-03-27',
              can_sell_today: true,
              holding_reason: '趋势延续',
              data_source: 'realtime_sina',
              quote_time: '2026-03-30 10:20:00',
            },
          ],
        },
      },
    })

    const { default: AccountView } = await import('../src/views/Account.vue')
    const wrapper = await mountView(AccountView)

    const deleteButton = wrapper.findAll('button').find((node) => node.text().includes('删除'))
    expect(deleteButton).toBeTruthy()
    await deleteButton.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('确认删除')
    expect(wrapper.text()).toContain('确定要删除这条持仓记录吗？')
    expect(wrapper.text()).toContain('沪电股份')
    expect(wrapper.text()).toContain('3,100.00')
  })

  it('普通用户在主框架里看不到管理员菜单', async () => {
    authState.user = {
      id: 'user-1',
      username: 'hehq',
      display_name: '贺老师',
      role: 'user',
      status: 'active',
    }
    authState.account = {
      id: 'account-1',
      account_code: 'HEHQ-001',
      account_name: '贺老师的账户',
      status: 'active',
    }
    authApi.me.mockResolvedValue(makeResponse({ user: authState.user, account: authState.account }))

    const { default: App } = await import('../src/App.vue')
    const wrapper = mount(App, {
      global: {
        stubs: {
          RouterView: { template: '<div class="router-view-stub" />' },
        },
      },
    })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('Dashboard')
    expect(text).toContain('复盘统计')
    expect(text).not.toContain('系统设置')
    expect(text).not.toContain('任务调度')
    expect(text).not.toContain('用户管理')
    expect(text).not.toContain('交易账户')
  })

  it('ReviewStats 页面点击去源页面会带来源和分层筛选', async () => {
    decisionApi.reviewStats.mockResolvedValue(makeResponse({
      bucket_stats: [
        {
          snapshot_type: 'pool_account',
          candidate_bucket_tag: '趋势回踩',
          count: 3,
          avg_return_1d: 1.2,
          win_rate_1d: 66.7,
          avg_return_3d: 2.5,
          win_rate_3d: 66.7,
          avg_return_5d: 3.1,
          win_rate_5d: 66.7,
          resolved_1d_count: 3,
          resolved_3d_count: 3,
          resolved_5d_count: 3,
        },
      ],
    }))

    const { default: ReviewStatsView } = await import('../src/views/ReviewStats.vue')
    const wrapper = await mountView(ReviewStatsView)

    const sourceButtons = wrapper.findAll('button').filter((node) => node.text().includes('去源页面'))
    const sourceButton = sourceButtons[sourceButtons.length - 1]
    expect(sourceButton).toBeTruthy()
    await sourceButton.trigger('click')

    expect(routerPush).toHaveBeenCalledWith({
      path: '/pools',
      query: {
        review_bucket: '趋势回踩',
        review_source: 'pool_account',
      },
    })
  })

  it('ReviewStats 页面遇到加仓样本会跳转到卖点页', async () => {
    decisionApi.reviewStats.mockResolvedValue(makeResponse({
      bucket_stats: [
        {
          snapshot_type: 'buy_available',
          candidate_bucket_tag: '强趋势延续',
          count: 4,
          avg_return_1d: 1.2,
          win_rate_1d: 75,
          avg_return_3d: 2.8,
          win_rate_3d: 75,
          avg_return_5d: 4.1,
          win_rate_5d: 75,
          resolved_1d_count: 4,
          resolved_3d_count: 4,
          resolved_5d_count: 4,
        },
        {
          snapshot_type: 'buy_add',
          add_position_decision: '可加',
          candidate_bucket_tag: '趋势回踩',
          count: 3,
          avg_return_1d: 1.8,
          win_rate_1d: 66.7,
          avg_return_3d: 3.2,
          win_rate_3d: 66.7,
          avg_return_5d: 4.5,
          win_rate_5d: 66.7,
          resolved_1d_count: 3,
          resolved_3d_count: 3,
          resolved_5d_count: 3,
        },
      ],
    }))

    const { default: ReviewStatsView } = await import('../src/views/ReviewStats.vue')
    const wrapper = await mountView(ReviewStatsView)

    expect(wrapper.text()).toContain('开仓样本')
    expect(wrapper.text()).toContain('加仓样本')
    expect(wrapper.text()).toContain('开仓结论')
    expect(wrapper.text()).toContain('加仓结论')

    const sourceButtons = wrapper.findAll('button').filter((node) => node.text().includes('去源页面'))
    expect(sourceButtons.length).toBeGreaterThan(0)
    routerPush.mockClear()
    for (const button of sourceButtons) {
      await button.trigger('click')
    }

    expect(routerPush.mock.calls).toContainEqual([
      {
        path: '/sell',
        query: {
          review_bucket: '趋势回踩',
          review_source: 'buy_add',
        },
      },
    ])
  })

  it('Login 页面登录成功后会写入会话并跳转到目标页面', async () => {
    routeMeta = { title: '登录', requiresAuth: false }
    routeQuery = { redirect: '/review' }
    authApi.ping.mockResolvedValue({ data: { status: 'ok' } })
    authApi.login.mockResolvedValue(makeResponse({
      access_token: 'access-token-1',
      refresh_token: 'refresh-token-1',
      user: {
        id: 'admin-1',
        username: 'admin',
        display_name: '管理员',
        role: 'admin',
        status: 'active',
      },
      account: {
        id: 'account-1',
        account_code: 'DEFAULT-001',
        account_name: '默认账户',
        status: 'active',
      },
    }))

    const { default: LoginView } = await import('../src/views/Login.vue')
    const wrapper = await mountView(LoginView)

    wrapper.vm.form.username = 'admin'
    wrapper.vm.form.password = 'admin123456'
    await wrapper.vm.handleLogin()
    await flushPromises()

    expect(authApi.ping).toHaveBeenCalledOnce()
    expect(authApi.login).toHaveBeenCalledWith({
      username: 'admin',
      password: 'admin123456',
    })
    expect(authState.accessToken).toBe('access-token-1')
    expect(authState.refreshToken).toBe('refresh-token-1')
    expect(authState.user?.username).toBe('admin')
    expect(authState.account?.account_code).toBe('DEFAULT-001')
    expect(window.localStorage.getItem('ai_stock_access_token')).toBe('access-token-1')
    expect(routerReplace).toHaveBeenCalledWith('/review')
    expect(messageSuccess).toHaveBeenCalledWith('登录成功')
  })

  it('管理员切换账户时会更新当前账户并触发刷新', async () => {
    authState.accessToken = 'admin-token'
    authState.refreshToken = 'refresh-token'
    authState.user = {
      id: 'admin-1',
      username: 'admin',
      display_name: '管理员',
      role: 'admin',
      status: 'active',
    }
    authState.account = {
      id: 'account-default',
      account_code: 'DEFAULT-001',
      account_name: '默认账户',
      status: 'active',
    }
    authApi.me.mockResolvedValue(makeResponse({ user: authState.user, account: authState.account }))
    adminApi.listAccounts.mockResolvedValue(makeResponse({
      accounts: [
        authState.account,
        {
          id: 'account-verify',
          account_code: 'VERIFY-002',
          account_name: '联调账户',
          status: 'active',
        },
      ],
    }))

    const { default: App } = await import('../src/App.vue')
    const wrapper = mount(App, {
      global: {
        stubs: {
          RouterView: { template: '<div class="router-view-stub" />' },
        },
      },
    })
    await flushPromises()

    try {
      wrapper.vm.handleAccountSwitch('account-verify')
    } catch {
      // jsdom 不支持 location.reload，这里只校验切账户前的关键副作用
    }
    await flushPromises()

    expect(adminApi.listAccounts).toHaveBeenCalled()
    expect(authState.account?.id).toBe('account-verify')
    expect(authState.account?.account_code).toBe('VERIFY-002')
    expect(window.localStorage.getItem('ai_stock_current_account')).toContain('VERIFY-002')
    expect(messageSuccess).toHaveBeenCalledWith('已切换到 联调账户')
  })
})
