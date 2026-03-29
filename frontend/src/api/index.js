import axios from 'axios'

// 默认走相对路径，便于 Docker 内 nginx 反代 /api；本地可设 VITE_API_BASE=http://localhost:8000/api/v1
const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000
})

// Market API
export const marketApi = {
  getEnv: (tradeDate, options = {}) => api.get('/market/env', {
    params: { trade_date: tradeDate },
    timeout: options.timeout
  }),
  getIndex: (tradeDate, options = {}) => api.get('/market/index', {
    params: { trade_date: tradeDate },
    timeout: options.timeout
  }),
  getStats: (tradeDate, options = {}) => api.get('/market/stats', {
    params: { trade_date: tradeDate },
    timeout: options.timeout
  })
}

// Sector API
export const sectorApi = {
  scan: (tradeDate, options = {}) => api.get('/sector/scan', {
    params: { trade_date: tradeDate, refresh: Boolean(options.refresh) },
    timeout: options.timeout
  }),
  leader: (tradeDate, options = {}) => api.get('/sector/leader', {
    params: { trade_date: tradeDate, refresh: Boolean(options.refresh) },
    timeout: options.timeout
  }),
  list: (tradeDate, limit, options = {}) => api.get('/sector/list', {
    params: { trade_date: tradeDate, limit, refresh: Boolean(options.refresh) },
    timeout: options.timeout
  })
}

// Stock API
export const stockApi = {
  filter: (tradeDate, limit) => api.get('/stock/filter', { params: { trade_date: tradeDate, limit } }),
  pools: (tradeDate, limit, options = {}) => api.get('/stock/pools', {
    params: { trade_date: tradeDate, limit, refresh: Boolean(options.refresh) },
    timeout: options.timeout
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
    },
    timeout: options.timeout
  })
}

// Decision API
export const decisionApi = {
  buyPoint: (tradeDate, limit, options = {}) => api.get('/decision/buy-point', {
    params: { trade_date: tradeDate, limit },
    timeout: options.timeout
  }),
  sellPoint: (tradeDate, options = {}) => api.get('/decision/sell-point', {
    params: {
      trade_date: tradeDate,
      force_llm_refresh: Boolean(options.forceLlmRefresh),
      include_llm: options.includeLlm !== undefined ? Boolean(options.includeLlm) : true
    },
    timeout: options.timeout
  }),
  summary: (tradeDate, options = {}) => api.get('/decision/summary', {
    params: { trade_date: tradeDate },
    timeout: options.timeout
  }),
  analyze: (tradeDate) => api.post('/decision/analyze', { trade_date: tradeDate }),
  reviewStats: (limitDays = 10, options = {}) => api.get('/decision/review-stats', {
    params: { limit_days: limitDays },
    timeout: options.timeout
  })
}

// Account API
export const accountApi = {
  profile: (options = {}) => api.get('/account/profile', { timeout: options.timeout }),
  positions: (options = {}) => api.get('/account/positions', { timeout: options.timeout }),
  status: (options = {}) => api.get('/account/status', { timeout: options.timeout }),
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

export const taskApi = {
  trigger: (payload) => api.post('/task/trigger', payload),
  status: (params = {}) => api.get('/task/status', { params }),
}

export default api
