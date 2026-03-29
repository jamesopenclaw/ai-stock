import axios from 'axios'
import { authState, clearSession, getAccessToken, getRefreshToken, setSession } from '../auth'

// 默认走相对路径，便于 Docker 内 nginx 反代 /api；本地可设 VITE_API_BASE=http://localhost:8000/api/v1
const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000
})

const redirectToLogin = () => {
  if (typeof window === 'undefined') {
    return
  }
  const current = `${window.location.pathname}${window.location.search || ''}`
  if (window.location.pathname === '/login') {
    return
  }
  const next = encodeURIComponent(current || '/')
  window.location.href = `/login?redirect=${next}`
}

let refreshPromise = null

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  const accountId = authState.account?.id
  if (accountId) {
    config.headers = config.headers || {}
    config.headers['X-Account-Id'] = accountId
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config || {}
    const status = error.response?.status
    const requestUrl = String(originalRequest.url || '')
    const isAuthEndpoint = requestUrl.includes('/auth/login') || requestUrl.includes('/auth/refresh')

    if (status !== 401 || originalRequest._retry || isAuthEndpoint) {
      throw error
    }

    const refreshToken = getRefreshToken()
    if (!refreshToken) {
      clearSession()
      redirectToLogin()
      throw error
    }

    if (!refreshPromise) {
      const selectedAccount = authState.account || null
      refreshPromise = axios
        .post(
          `${API_BASE}/auth/refresh`,
          { refresh_token: refreshToken },
          selectedAccount?.id
            ? { headers: { 'X-Account-Id': selectedAccount.id } }
            : undefined
        )
        .then((response) => {
          const payload = response.data?.data || {}
          const nextAccount =
            payload.user?.role === 'admin' && selectedAccount?.id
              ? selectedAccount
              : payload.account || null
          setSession({
            accessToken: payload.access_token || '',
            refreshToken: payload.refresh_token || '',
            user: payload.user || null,
            account: nextAccount,
          })
          return payload
        })
        .catch((refreshError) => {
          clearSession()
          redirectToLogin()
          throw refreshError
        })
        .finally(() => {
          refreshPromise = null
        })
    }

    const payload = await refreshPromise
    originalRequest._retry = true
    originalRequest.headers = originalRequest.headers || {}
    originalRequest.headers.Authorization = `Bearer ${payload.access_token}`
    return api(originalRequest)
  }
)

export const authApi = {
  login: (payload) => api.post('/auth/login', payload),
  refresh: (refreshToken) => api.post('/auth/refresh', { refresh_token: refreshToken }),
  logout: (refreshToken) => api.post('/auth/logout', { refresh_token: refreshToken }),
  me: () => api.get('/auth/me'),
}

export const adminApi = {
  listUsers: () => api.get('/admin/users'),
  createUser: (payload) => api.post('/admin/users', payload),
  updateUser: (userId, payload) => api.put(`/admin/users/${encodeURIComponent(userId)}`, payload),
  listAccounts: () => api.get('/admin/accounts'),
  createAccount: (payload) => api.post('/admin/accounts', payload),
  updateAccount: (accountId, payload) => api.put(`/admin/accounts/${encodeURIComponent(accountId)}`, payload),
  bindAccount: (accountId, payload) => api.post(`/admin/accounts/${encodeURIComponent(accountId)}/bind-user`, payload),
}

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
  overview: (options = {}) => api.get('/account/overview', { timeout: options.timeout }),
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
