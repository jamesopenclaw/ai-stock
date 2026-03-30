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
}

const sectorApi = {
  leader: vi.fn(),
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
  sectorApi.leader.mockReset()
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
  taskApi.trigger.mockReset()
  taskApi.status.mockReset()
  authState.accessToken = ''
  authState.refreshToken = ''
  authState.user = null
  authState.account = null
})

describe('关键页面联调', () => {
  it('Pools 页面会加载三池和复盘数据，并显示焦点方向文案', async () => {
    routeQuery = { focus_sector: '机器人' }
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
    expect(decisionApi.reviewStats).toHaveBeenCalledOnce()
    expect(stockApi.pools).toHaveBeenCalledWith(expect.any(String), 50, expect.objectContaining({ timeout: 90000 }))
    expect(wrapper.text()).toContain('当前按')
    expect(wrapper.text()).toContain('机器人')
    expect(wrapper.text()).toContain('机器人一号')
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
    expect(decisionApi.reviewStats).toHaveBeenCalledOnce()
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

    expect(stockApi.buyAnalysis).toHaveBeenCalledWith('002025.SZ', '2026-03-30')
    expect(wrapper.text()).toContain('获取买点分析失败: 目标股票不存在于候选上下文')
    expect(wrapper.text()).toContain('买点 SOP 加载失败')
    expect(messageError).toHaveBeenCalledWith('获取买点分析失败: 目标股票不存在于候选上下文')
  })

  it('Dashboard 页面会串起摘要、市场、板块、账户和买卖信号接口', async () => {
    marketApi.getEnv.mockResolvedValue(makeResponse({
      market_env_tag: '进攻',
      market_comment: '题材扩散，适合主动进攻',
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
    expect(decisionApi.reviewStats).toHaveBeenCalledOnce()
    expect(messageSuccess).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('今日执行摘要')
    expect(wrapper.text()).toContain('适度积极')
    expect(wrapper.text()).toContain('机器人')
    expect(wrapper.text()).toContain('50.00万')
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
      ],
      llm_status: null,
    }))

    const { default: SellPointView } = await import('../src/views/SellPoint.vue')
    const wrapper = await mountView(SellPointView)

    expect(decisionApi.sellPoint).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('建议加仓')
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
      expect.objectContaining({ refresh: true, forceLlmRefresh: false }),
    )
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

    const sourceButton = wrapper.findAll('button').find((node) => node.text().includes('去源页面'))
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
