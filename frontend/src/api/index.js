import axios from 'axios'
import { authState, clearSession, getAccessToken, getRefreshToken, setSession } from '../auth'

// 默认走相对路径，便于 Docker 内 nginx 反代 /api；本地可设 VITE_API_BASE=http://localhost:8000/api/v1
const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000
})

const memoryCache = new Map()
const inflightRequests = new Map()
const DEFAULT_CACHE_TTL_MS = 60 * 1000

const scopedCacheKey = (prefix, parts = []) => {
  const accountId = authState.account?.id || 'guest'
  return [prefix, accountId, ...parts].join(':')
}

const readCachedValue = (cacheKey, ttlMs, options = {}) => {
  const now = Date.now()
  const memo = memoryCache.get(cacheKey)
  if (memo && now - memo.updatedAt < ttlMs) {
    if (options.shouldUseCachedValue && !options.shouldUseCachedValue(memo.value)) {
      memoryCache.delete(cacheKey)
    } else {
      return memo.value
    }
  }
  if (typeof window === 'undefined') return null
  const raw = window.sessionStorage.getItem(cacheKey)
  if (!raw) return null
  try {
    const payload = JSON.parse(raw)
    if (!payload?.updatedAt || now - Number(payload.updatedAt) >= ttlMs) {
      window.sessionStorage.removeItem(cacheKey)
      return null
    }
    if (options.shouldUseCachedValue && !options.shouldUseCachedValue(payload.value)) {
      window.sessionStorage.removeItem(cacheKey)
      return null
    }
    memoryCache.set(cacheKey, payload)
    return payload.value
  } catch (error) {
    window.sessionStorage.removeItem(cacheKey)
    return null
  }
}

const writeCachedValue = (cacheKey, value, options = {}) => {
  if (options.shouldCacheValue && !options.shouldCacheValue(value)) {
    memoryCache.delete(cacheKey)
    if (typeof window !== 'undefined') {
      window.sessionStorage.removeItem(cacheKey)
    }
    return
  }
  const payload = { value, updatedAt: Date.now() }
  memoryCache.set(cacheKey, payload)
  if (typeof window !== 'undefined') {
    window.sessionStorage.setItem(cacheKey, JSON.stringify(payload))
  }
}

const cachedGet = async (cacheKey, fetcher, options = {}) => {
  const ttlMs = options.ttlMs ?? DEFAULT_CACHE_TTL_MS
  if (!options.refresh) {
    const cachedValue = readCachedValue(cacheKey, ttlMs, options)
    if (cachedValue) {
      return { data: { data: cachedValue } }
    }
    const inflight = inflightRequests.get(cacheKey)
    if (inflight) {
      return inflight
    }
  }

  const requestPromise = fetcher()
    .then((response) => {
      writeCachedValue(cacheKey, response.data?.data ?? null, options)
      return response
    })
    .finally(() => {
      inflightRequests.delete(cacheKey)
    })

  inflightRequests.set(cacheKey, requestPromise)
  return requestPromise
}

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
  ping: (options = {}) => api.get('/ping', { timeout: options.timeout }),
  login: (payload) => api.post('/auth/login', payload),
  refresh: (refreshToken) => api.post('/auth/refresh', { refresh_token: refreshToken }),
  logout: (refreshToken) => api.post('/auth/logout', { refresh_token: refreshToken }),
  me: () => api.get('/auth/me'),
}

export const adminApi = {
  listUsers: () => api.get('/admin/users'),
  createUser: (payload) => api.post('/admin/users', payload),
  updateUser: (userId, payload) => api.put(`/admin/users/${encodeURIComponent(userId)}`, payload),
  resetUserPassword: (userId, payload) => api.post(`/admin/users/${encodeURIComponent(userId)}/reset-password`, payload),
  listAccounts: () => api.get('/admin/accounts'),
  createAccount: (payload) => api.post('/admin/accounts', payload),
  updateAccount: (accountId, payload) => api.put(`/admin/accounts/${encodeURIComponent(accountId)}`, payload),
  bindAccount: (accountId, payload) => api.post(`/admin/accounts/${encodeURIComponent(accountId)}/bind-user`, payload),
}

// Market API
export const marketApi = {
  getEnv: (tradeDate, options = {}) => cachedGet(
    scopedCacheKey('market-env', [tradeDate]),
    () => api.get('/market/env', {
      params: { trade_date: tradeDate },
      timeout: options.timeout
    }),
    { ttlMs: options.ttlMs ?? DEFAULT_CACHE_TTL_MS, refresh: Boolean(options.refresh) }
  ),
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
  scan: (tradeDate, options = {}) => cachedGet(
    scopedCacheKey('sector-scan', [tradeDate]),
    () => api.get('/sector/scan', {
      params: { trade_date: tradeDate, refresh: Boolean(options.refresh) },
      timeout: options.timeout
    }),
    { ttlMs: options.ttlMs ?? 30 * 1000, refresh: Boolean(options.refresh) }
  ),
  leader: (tradeDate, options = {}) => cachedGet(
    scopedCacheKey('sector-leader', [tradeDate]),
    () => api.get('/sector/leader', {
      params: { trade_date: tradeDate, refresh: Boolean(options.refresh) },
      timeout: options.timeout
    }),
    { ttlMs: options.ttlMs ?? 30 * 1000, refresh: Boolean(options.refresh) }
  ),
  hot: (tradeDate, limit = 6, options = {}) => cachedGet(
    scopedCacheKey('sector-hot', [tradeDate, String(limit)]),
    () => api.get('/sector/hot', {
      params: { trade_date: tradeDate, limit, refresh: Boolean(options.refresh) },
      timeout: options.timeout
    }),
    { ttlMs: options.ttlMs ?? 30 * 1000, refresh: Boolean(options.refresh) }
  ),
  list: (tradeDate, limit, options = {}) => api.get('/sector/list', {
    params: { trade_date: tradeDate, limit, refresh: Boolean(options.refresh) },
    timeout: options.timeout
  }),
  topStocks: (tradeDate, sectorName, sectorSourceType, limit = 10, options = {}) => api.get('/sector/top-stocks', {
    params: {
      trade_date: tradeDate,
      sector_name: sectorName,
      sector_source_type: sectorSourceType,
      limit,
      refresh: Boolean(options.refresh)
    },
    timeout: options.timeout
  })
}

// Stock API
export const stockApi = {
  filter: (tradeDate, limit) => api.get('/stock/filter', { params: { trade_date: tradeDate, limit } }),
  pools: (tradeDate, limit, options = {}) => cachedGet(
    scopedCacheKey('stock-pools', [
      tradeDate,
      String(limit),
      String(options.mode || 'stable'),
      String(options.strategyStyle || 'balanced'),
    ]),
    () => api.get('/stock/pools', {
      params: {
        trade_date: tradeDate,
        limit,
        refresh: Boolean(options.refresh),
        mode: options.mode || 'stable',
        strategy_style: options.strategyStyle || 'balanced',
        include_watch_candidates: true,
      },
      timeout: options.timeout
    }),
    {
      ttlMs: options.ttlMs ?? ((options.mode || 'stable') === 'radar' ? 15 * 1000 : 30 * 1000),
      refresh: Boolean(options.refresh),
      shouldUseCachedValue: (value) => !value?.refresh_in_progress && !value?.stale_snapshot,
      shouldCacheValue: (value) => !value?.refresh_in_progress && !value?.stale_snapshot,
    }
  ),
  detail: (tsCode, tradeDate) => api.get(`/stock/detail/${tsCode}`, { params: { trade_date: tradeDate } }),
  buyAnalysis: (tsCode, tradeDate, options = {}) => api.get(`/stock/buy-analysis/${encodeURIComponent(tsCode)}`, {
    params: {
      trade_date: tradeDate,
      source_pool_tag: options.sourcePoolTag,
      force_llm_refresh: Boolean(options.forceLlmRefresh),
      include_llm: options.includeLlm !== undefined ? Boolean(options.includeLlm) : true,
    },
    timeout: options.timeout ?? 90000,
  }),
  sellAnalysis: (tsCode, tradeDate, options = {}) => api.get(`/stock/sell-analysis/${encodeURIComponent(tsCode)}`, {
    params: { trade_date: tradeDate },
    timeout: options.timeout ?? 90000,
  }),
  checkup: (tsCode, tradeDate, checkupTarget, options = {}) => api.get(`/stock/checkup/${encodeURIComponent(tsCode)}`, {
    params: {
      trade_date: tradeDate,
      checkup_target: checkupTarget,
      force_llm_refresh: Boolean(options.forceLlmRefresh),
      include_llm: options.includeLlm !== undefined ? Boolean(options.includeLlm) : true
    },
    timeout: options.timeout
  }),
  checkupLlm: (body, options = {}) => api.post('/stock/checkup-llm', body, {
    timeout: options.timeout ?? 120000
  }),
  patternAnalysis: (tsCode, tradeDate, options = {}) => api.get(`/stock/pattern-analysis/${encodeURIComponent(tsCode)}`, {
    params: {
      trade_date: tradeDate,
      force_llm_refresh: Boolean(options.forceLlmRefresh)
    },
    timeout: options.timeout ?? 90000
  }),
  manualWatch: (tradeDate, options = {}) => api.get('/stock/manual-watch', {
    params: { trade_date: tradeDate },
    timeout: options.timeout ?? 60000
  }),
  manualWatchAdd: (tsCode, tradeDate, options = {}) => api.post(
    '/stock/manual-watch',
    { ts_code: tsCode },
    {
      params: tradeDate ? { trade_date: tradeDate } : {},
      timeout: options.timeout ?? 30000
    }
  ),
  manualWatchDelete: (tsCode, options = {}) => api.delete(
    `/stock/manual-watch/${encodeURIComponent(tsCode)}`,
    { timeout: options.timeout ?? 30000 }
  ),
}

// Decision API
export const decisionApi = {
  buyPoint: (tradeDate, limit, options = {}) => cachedGet(
    scopedCacheKey('decision-buy-point', [
      tradeDate,
      String(limit),
      String(options.strategyStyle || 'balanced'),
    ]),
    () => api.get('/decision/buy-point', {
      params: {
        trade_date: tradeDate,
        limit,
        refresh: Boolean(options.refresh),
        strategy_style: options.strategyStyle || 'balanced',
      },
      timeout: options.timeout
    }),
    {
      ttlMs: options.ttlMs ?? 20 * 1000,
      refresh: Boolean(options.refresh),
    }
  ),
  sellPoint: (tradeDate, options = {}) => api.get('/decision/sell-point', {
    params: {
      trade_date: tradeDate,
      refresh: Boolean(options.refresh),
      force_llm_refresh: Boolean(options.forceLlmRefresh),
      include_llm: options.includeLlm !== undefined ? Boolean(options.includeLlm) : true,
      include_add_signals: options.includeAddSignals !== undefined ? Boolean(options.includeAddSignals) : true
    },
    timeout: options.timeout
  }),
  summary: (tradeDate, options = {}) => api.get('/decision/summary', {
    params: { trade_date: tradeDate },
    timeout: options.timeout
  }),
  analyze: (tradeDate) => api.post('/decision/analyze', { trade_date: tradeDate }),
  reviewStats: (limitDays = 10, options = {}) => cachedGet(
    scopedCacheKey('review-stats', [String(limitDays)]),
    () => api.get('/decision/review-stats', {
      params: {
        limit_days: limitDays,
        refresh_outcomes: Boolean(options.refreshOutcomes)
      },
      timeout: options.timeout
    }),
    {
      ttlMs: options.ttlMs ?? DEFAULT_CACHE_TTL_MS,
      refresh: Boolean(options.refresh || options.refreshOutcomes)
    }
  )
}

// Account API
export const accountApi = {
  overview: (options = {}) => cachedGet(
    scopedCacheKey('account-overview'),
    () => api.get('/account/overview', { timeout: options.timeout }),
    { ttlMs: options.ttlMs ?? 30 * 1000, refresh: Boolean(options.refresh) }
  ),
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

export const notificationApi = {
  list: (params = {}, options = {}) => api.get('/notifications', {
    params,
    timeout: options.timeout
  }),
  summary: (options = {}) => api.get('/notifications/summary', {
    params: { refresh: Boolean(options.refresh) },
    timeout: options.timeout
  }),
  markRead: (eventId) => api.post(`/notifications/${encodeURIComponent(eventId)}/read`),
  markAllRead: (payload = {}) => api.post('/notifications/read-all', payload),
  dismiss: (eventId) => api.post(`/notifications/${encodeURIComponent(eventId)}/dismiss`),
  snooze: (eventId, minutes = 30) => api.post(`/notifications/${encodeURIComponent(eventId)}/snooze`, { minutes }),
  settings: (options = {}) => api.get('/notifications/settings', { timeout: options.timeout }),
  updateSettings: (payload) => api.put('/notifications/settings', payload),
  testWecom: (payload = {}) => api.post('/notifications/settings/test-wecom', payload),
}

export const systemApi = {
  getConfig: () => api.get('/system/config'),
  updateConfig: (payload) => api.put('/system/config', payload),
  llmLogs: (params = {}) => api.get('/system/llm/logs', { params }),
  llmLogsDailyStats: (params = {}) => api.get('/system/llm/logs/daily-stats', { params })
}

export const taskApi = {
  trigger: (payload) => api.post('/task/trigger', payload),
  status: (params = {}) => api.get('/task/status', { params }),
}

export default api
