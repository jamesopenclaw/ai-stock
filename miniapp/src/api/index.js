// API 配置
import { authState, clearSession, getAccessToken } from '../auth'

const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

// 请求封装
const request = (url, options = {}) => {
  return new Promise((resolve, reject) => {
    const { params, data, ...rest } = options
    const headers = {
      ...(rest.header || {}),
    }
    const token = getAccessToken()
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }
    const accountId = authState.account?.id
    if (accountId) {
      headers['X-Account-Id'] = accountId
    }
    uni.request({
      url: API_BASE + url,
      header: headers,
      data: data !== undefined ? data : params,
      ...rest,
      success: (res) => {
        if (res.statusCode === 200 && res.data?.code !== 401) {
          resolve(res.data)
        } else if (res.statusCode === 401 || res.data?.code === 401) {
          clearSession()
          uni.showToast({ title: '登录已失效，请重新登录', icon: 'none' })
          reject(res)
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

export const authApi = {
  login: (data) => request('/auth/login', { method: 'POST', data }),
  refresh: (refreshToken) => request('/auth/refresh', { method: 'POST', data: { refresh_token: refreshToken } }),
  logout: (refreshToken) => request('/auth/logout', { method: 'POST', data: { refresh_token: refreshToken } }),
  me: () => request('/auth/me'),
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
  addPosition: (data) => request('/account/positions', { method: 'POST', data }),
  deletePosition: (positionId) => request(`/account/positions/${encodeURIComponent(positionId)}`, { method: 'DELETE' }),
  updatePosition: (tsCode, data) =>
    request(`/account/positions/${encodeURIComponent(tsCode)}`, { method: 'PUT', data })
}

// 获取今日日期
export const getToday = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
