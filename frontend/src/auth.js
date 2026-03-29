import { reactive } from 'vue'

const ACCESS_TOKEN_KEY = 'ai_stock_access_token'
const REFRESH_TOKEN_KEY = 'ai_stock_refresh_token'
const USER_KEY = 'ai_stock_current_user'
const ACCOUNT_KEY = 'ai_stock_current_account'

const readJson = (key) => {
  if (typeof window === 'undefined') {
    return null
  }
  const raw = window.localStorage.getItem(key)
  if (!raw) {
    return null
  }
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export const authState = reactive({
  accessToken: typeof window === 'undefined' ? '' : window.localStorage.getItem(ACCESS_TOKEN_KEY) || '',
  refreshToken: typeof window === 'undefined' ? '' : window.localStorage.getItem(REFRESH_TOKEN_KEY) || '',
  user: readJson(USER_KEY),
  account: readJson(ACCOUNT_KEY),
})

export const getAccessToken = () => authState.accessToken || ''

export const getRefreshToken = () => authState.refreshToken || ''

export const isAuthenticated = () => Boolean(getAccessToken())

export const setSession = ({ accessToken, refreshToken, user, account }) => {
  authState.accessToken = accessToken || ''
  authState.refreshToken = refreshToken || ''
  authState.user = user || null
  authState.account = account || null

  if (typeof window === 'undefined') {
    return
  }

  if (authState.accessToken) {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, authState.accessToken)
  } else {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY)
  }

  if (authState.refreshToken) {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, authState.refreshToken)
  } else {
    window.localStorage.removeItem(REFRESH_TOKEN_KEY)
  }

  if (authState.user) {
    window.localStorage.setItem(USER_KEY, JSON.stringify(authState.user))
  } else {
    window.localStorage.removeItem(USER_KEY)
  }

  if (authState.account) {
    window.localStorage.setItem(ACCOUNT_KEY, JSON.stringify(authState.account))
  } else {
    window.localStorage.removeItem(ACCOUNT_KEY)
  }
}

export const clearSession = () => {
  setSession({ accessToken: '', refreshToken: '', user: null, account: null })
}

export const setCurrentAccount = (account) => {
  setSession({
    accessToken: authState.accessToken,
    refreshToken: authState.refreshToken,
    user: authState.user,
    account: account || null,
  })
}
