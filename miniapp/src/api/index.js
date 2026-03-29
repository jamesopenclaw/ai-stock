// API 配置
const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

// 请求封装
const request = (url, options = {}) => {
  return new Promise((resolve, reject) => {
    uni.request({
      url: API_BASE + url,
      ...options,
      success: (res) => {
        if (res.statusCode === 200) {
          resolve(res.data)
        } else {
          reject(res)
        }
      },
      fail: (err) => {
        reject(err)
      }
    })
  })
}

// 市场 API
export const marketApi = {
  getEnv: (tradeDate) => request('/market/env', { params: { trade_date: tradeDate } }),
  getIndex: (tradeDate) => request('/market/index', { params: { trade_date: tradeDate } }),
  getStats: (tradeDate) => request('/market/stats', { params: { trade_date: tradeDate } })
}

// 板块 API
export const sectorApi = {
  scan: (tradeDate, options = {}) => request('/sector/scan', {
    params: { trade_date: tradeDate, refresh: Boolean(options.refresh) }
  }),
  leader: (tradeDate, options = {}) => request('/sector/leader', {
    params: { trade_date: tradeDate, refresh: Boolean(options.refresh) }
  }),
  list: (tradeDate, limit = 20, options = {}) => request('/sector/list', {
    params: { trade_date: tradeDate, limit, refresh: Boolean(options.refresh) }
  })
}

// 个股 API
export const stockApi = {
  filter: (tradeDate, limit = 50) => request('/stock/filter', { params: { trade_date: tradeDate, limit } }),
  pools: (tradeDate, limit = 50, options = {}) => request('/stock/pools', {
    params: { trade_date: tradeDate, limit, refresh: Boolean(options.refresh) }
  }),
  detail: (tsCode, tradeDate) => request(`/stock/detail/${tsCode}`, { params: { trade_date: tradeDate } })
}

// 决策 API
export const decisionApi = {
  buyPoint: (tradeDate, limit = 30) => request('/decision/buy-point', { params: { trade_date: tradeDate, limit } }),
  sellPoint: (tradeDate) => request('/decision/sell-point', { params: { trade_date: tradeDate } }),
  summary: (tradeDate) => request('/decision/summary', { params: { trade_date: tradeDate } }),
  analyze: (tradeDate) => request('/decision/analyze', { method: 'POST', data: { trade_date: tradeDate } })
}

// 账户 API
export const accountApi = {
  profile: () => request('/account/profile'),
  positions: () => request('/account/positions'),
  status: () => request('/account/status'),
  getConfig: () => request('/account/config'),
  updateConfig: (data) => request('/account/config', { method: 'PUT', data }),
  adapt: (tradeDate) => request('/account/adapt', { method: 'POST', data: { trade_date: tradeDate } }),
  updatePosition: (tsCode, data) =>
    request(`/account/positions/${encodeURIComponent(tsCode)}`, { method: 'PUT', data })
}

// 获取今日日期
export const getToday = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
