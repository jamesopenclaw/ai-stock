import axios from 'axios'

// 默认走相对路径，便于 Docker 内 nginx 反代 /api；本地可设 VITE_API_BASE=http://localhost:8000/api/v1
const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

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
  pools: (tradeDate, limit, options = {}) => api.get('/stock/pools', {
    params: { trade_date: tradeDate, limit, force_llm_refresh: Boolean(options.forceLlmRefresh) }
  }),
  detail: (tsCode, tradeDate) => api.get(`/stock/detail/${tsCode}`, { params: { trade_date: tradeDate } }),
  buyAnalysis: (tsCode, tradeDate) => api.get(`/stock/buy-analysis/${encodeURIComponent(tsCode)}`, {
    params: { trade_date: tradeDate }
  }),
  sellAnalysis: (tsCode, tradeDate) => api.get(`/stock/sell-analysis/${encodeURIComponent(tsCode)}`, {
    params: { trade_date: tradeDate }
  }),
  checkup: (tsCode, tradeDate, checkupTarget, options = {}) => api.get(`/stock/checkup/${encodeURIComponent(tsCode)}`, {
    params: {
      trade_date: tradeDate,
      checkup_target: checkupTarget,
      force_llm_refresh: Boolean(options.forceLlmRefresh)
    }
  })
}

// Decision API
export const decisionApi = {
  buyPoint: (tradeDate, limit) => api.get('/decision/buy-point', { params: { trade_date: tradeDate, limit } }),
  sellPoint: (tradeDate, options = {}) => api.get('/decision/sell-point', {
    params: { trade_date: tradeDate, force_llm_refresh: Boolean(options.forceLlmRefresh) }
  }),
  summary: (tradeDate) => api.get('/decision/summary', { params: { trade_date: tradeDate } }),
  analyze: (tradeDate) => api.post('/decision/analyze', { trade_date: tradeDate }),
  reviewStats: (limitDays = 10) => api.get('/decision/review-stats', { params: { limit_days: limitDays } })
}

// Account API
export const accountApi = {
  profile: () => api.get('/account/profile'),
  positions: () => api.get('/account/positions'),
  status: () => api.get('/account/status'),
  adapt: (tradeDate) => api.post('/account/adapt', { trade_date: tradeDate }),
  getConfig: () => api.get('/account/config'),
  updateConfig: (payload) => api.put('/account/config', payload),
  addPosition: (payload) => api.post('/account/positions', payload),
  /** 修改持仓：数量、成本价、买入理由（路径使用 ts_code，需 encode） */
  updatePosition: (tsCode, payload) =>
    api.put(`/account/positions/${encodeURIComponent(tsCode)}`, payload),
  deletePosition: (positionId) => api.delete(`/account/positions/${positionId}`)
}

export const systemApi = {
  llmLogs: (params = {}) => api.get('/system/llm/logs', { params })
}

export default api
