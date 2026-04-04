import { computed, reactive, toRefs } from 'vue'

import { notificationApi } from '../api'
import { authState } from '../auth'

const SUMMARY_TTL_MS = 10 * 1000
const LIST_TTL_MS = 8 * 1000

const createDefaultSummary = () => ({
  unread_count: 0,
  critical_count: 0,
  latest_items: [],
  quiet_window_active: false,
  quiet_window_label: '',
})

const createDefaultSettings = () => ({
  in_app_enabled: true,
  wecom_enabled: false,
  rules: {},
  quiet_windows: [],
})

const state = reactive({
  accountId: '',
  summary: createDefaultSummary(),
  summaryUpdatedAt: 0,
  summaryPromise: null,
  listCache: {},
  settings: createDefaultSettings(),
  settingsUpdatedAt: 0,
  settingsPromise: null,
})

const resetState = () => {
  state.summary = createDefaultSummary()
  state.summaryUpdatedAt = 0
  state.summaryPromise = null
  state.listCache = {}
  state.settings = createDefaultSettings()
  state.settingsUpdatedAt = 0
  state.settingsPromise = null
}

const ensureAccountScope = () => {
  const nextAccountId = authState.account?.id || ''
  if (state.accountId === nextAccountId) {
    return nextAccountId
  }
  state.accountId = nextAccountId
  resetState()
  return nextAccountId
}

const listKeyOf = ({ status = '', category = '', priority = '' } = {}) =>
  JSON.stringify({
    status: status || '',
    category: category || '',
    priority: priority || '',
  })

const getCachedListEntry = (filters = {}) => {
  const key = listKeyOf(filters)
  return state.listCache[key] || null
}

const setCachedListEntry = (filters = {}, payload = {}) => {
  const key = listKeyOf(filters)
  const entry = state.listCache[key] || {}
  state.listCache[key] = {
    ...entry,
    items: Array.isArray(payload.items) ? payload.items : [],
    unread_count: Number(payload.unread_count || 0),
    critical_count: Number(payload.critical_count || 0),
    next_cursor: payload.next_cursor || null,
    updatedAt: Date.now(),
    promise: null,
  }
}

const invalidateLists = () => {
  state.listCache = {}
}

const loadSummary = async ({ force = false } = {}) => {
  const accountId = ensureAccountScope()
  if (!accountId) {
    resetState()
    return state.summary
  }

  const now = Date.now()
  if (!force && state.summaryUpdatedAt && now - state.summaryUpdatedAt < SUMMARY_TTL_MS) {
    return state.summary
  }
  if (!force && state.summaryPromise) {
    return state.summaryPromise
  }

  const request = notificationApi.summary()
    .then((res) => {
      const payload = res.data?.data || {}
      state.summary = {
        unread_count: Number(payload.unread_count || 0),
        critical_count: Number(payload.critical_count || 0),
        latest_items: Array.isArray(payload.latest_items) ? payload.latest_items : [],
        quiet_window_active: Boolean(payload.quiet_window_active),
        quiet_window_label: payload.quiet_window_label || '',
      }
      state.summaryUpdatedAt = Date.now()
      return state.summary
    })
    .finally(() => {
      state.summaryPromise = null
    })

  state.summaryPromise = request
  return request
}

const loadList = async (filters = {}, { force = false } = {}) => {
  const accountId = ensureAccountScope()
  if (!accountId) {
    invalidateLists()
    return {
      items: [],
      unread_count: 0,
      critical_count: 0,
      next_cursor: null,
    }
  }

  const entry = getCachedListEntry(filters)
  const now = Date.now()
  if (!force && entry?.updatedAt && now - entry.updatedAt < LIST_TTL_MS) {
    return entry
  }
  if (!force && entry?.promise) {
    return entry.promise
  }

  const request = notificationApi.list({
    status: filters.status || undefined,
    category: filters.category || undefined,
    priority: filters.priority || undefined,
  })
    .then((res) => {
      const payload = res.data?.data || {}
      setCachedListEntry(filters, payload)
      if (payload.unread_count != null || payload.critical_count != null) {
        state.summary = {
          ...state.summary,
          unread_count: Number(payload.unread_count || 0),
          critical_count: Number(payload.critical_count || 0),
        }
        state.summaryUpdatedAt = Date.now()
      }
      return state.listCache[listKeyOf(filters)]
    })
    .finally(() => {
      const latest = getCachedListEntry(filters)
      if (latest) {
        latest.promise = null
      }
    })

  state.listCache[listKeyOf(filters)] = {
    ...(entry || {}),
    promise: request,
  }
  return request
}

const loadSettings = async ({ force = false } = {}) => {
  const accountId = ensureAccountScope()
  if (!accountId) {
    state.settings = createDefaultSettings()
    return state.settings
  }

  const now = Date.now()
  if (!force && state.settingsUpdatedAt && now - state.settingsUpdatedAt < SUMMARY_TTL_MS) {
    return state.settings
  }
  if (!force && state.settingsPromise) {
    return state.settingsPromise
  }

  const request = notificationApi.settings()
    .then((res) => {
      const payload = res.data?.data || {}
      state.settings = {
        in_app_enabled: Boolean(payload.in_app_enabled),
        wecom_enabled: Boolean(payload.wecom_enabled),
        rules: { ...(payload.rules || {}) },
        quiet_windows: Array.isArray(payload.quiet_windows) ? [...payload.quiet_windows] : [],
      }
      state.settingsUpdatedAt = Date.now()
      return state.settings
    })
    .finally(() => {
      state.settingsPromise = null
    })

  state.settingsPromise = request
  return request
}

const updateSettings = async (payload) => {
  ensureAccountScope()
  const res = await notificationApi.updateSettings(payload)
  const data = res.data?.data || {}
  state.settings = {
    in_app_enabled: Boolean(data.in_app_enabled),
    wecom_enabled: Boolean(data.wecom_enabled),
    rules: { ...(data.rules || {}) },
    quiet_windows: Array.isArray(data.quiet_windows) ? [...data.quiet_windows] : [],
  }
  state.settingsUpdatedAt = Date.now()
  invalidateLists()
  await loadSummary({ force: true })
  return state.settings
}

const markRead = async (eventId) => {
  ensureAccountScope()
  await notificationApi.markRead(eventId)
  invalidateLists()
  await loadSummary({ force: true })
}

const markAllRead = async (payload = {}) => {
  ensureAccountScope()
  await notificationApi.markAllRead(payload)
  invalidateLists()
  await loadSummary({ force: true })
}

const snooze = async (eventId, minutes = 30) => {
  ensureAccountScope()
  await notificationApi.snooze(eventId, minutes)
  invalidateLists()
  await loadSummary({ force: true })
}

export const useNotificationStore = () => ({
  ...toRefs(state),
  summary: computed(() => state.summary),
  settings: computed(() => state.settings),
  loadSummary,
  loadList,
  loadSettings,
  updateSettings,
  markRead,
  markAllRead,
  snooze,
  invalidateLists,
  resetState,
  ensureAccountScope,
})
