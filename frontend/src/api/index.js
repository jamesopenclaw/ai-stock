import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000
})

// Market API
export const marketApi = {
  getEnv: (tradeDate) => api.get('/market/env', { params: { trade_date: tradeDate } }),
  getIndex: (tradeDate) => api.get('/market/index', { params: { trade_date: tradeDate } }),
  getStats: (tradeDate) => api.get('/market/stats', { params: { trade_date: tradeDate } })
}

// Sector API
export const sectorApi = {
  scan: (tradeDate) => api.get('/sector/scan', { params: { trade_date: tradeDate } }),
  leader: (tradeDate) => api.get('/sector/leader', { params: { trade_date: tradeDate } }),
  list: (tradeDate, limit) => api.get('/sector/list', { params: { trade_date: tradeDate, limit } })
}

// Stock API
export const stockApi = {
  filter: (tradeDate, limit) => api.get('/stock/filter', { params: { trade_date: tradeDate, limit } }),
  pools: (tradeDate, limit) => api.get('/stock/pools', { params: { trade_date: tradeDate, limit } }),
  detail: (tsCode, tradeDate) => api.get(`/stock/detail/${tsCode}`, { params: { trade_date: tradeDate } })
}

// Decision API
export const decisionApi = {
  buyPoint: (tradeDate, limit) => api.get('/decision/buy-point', { params: { trade_date: tradeDate, limit } }),
  sellPoint: (tradeDate) => api.get('/decision/sell-point', { params: { trade_date: tradeDate } }),
  summary: (tradeDate) => api.get('/decision/summary', { params: { trade_date: tradeDate } }),
  analyze: (tradeDate) => api.post('/decision/analyze', { trade_date: tradeDate })
}

// Account API
export const accountApi = {
  profile: () => api.get('/account/profile'),
  positions: () => api.get('/account/positions'),
  status: () => api.get('/account/status'),
  adapt: (tradeDate) => api.post('/account/adapt', { trade_date: tradeDate })
}

export default api
