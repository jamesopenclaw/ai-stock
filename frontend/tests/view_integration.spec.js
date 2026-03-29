import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

let routeQuery = {}
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
  profile: vi.fn(),
}

const stockApi = {
  pools: vi.fn(),
}

const taskApi = {
  trigger: vi.fn(),
  status: vi.fn(),
}

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery }),
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
  routeQuery = {}
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
  stockApi.pools.mockReset()
  taskApi.trigger.mockReset()
  taskApi.status.mockReset()
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
})
