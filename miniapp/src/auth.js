import { reactive } from 'vue'

const ACCESS_TOKEN_KEY = 'ai_stock_access_token'
const REFRESH_TOKEN_KEY = 'ai_stock_refresh_token'
const USER_KEY = 'ai_stock_current_user'
const ACCOUNT_KEY = 'ai_stock_current_account'

const readJson = (key) => {
  try {
    const raw = uni.getStorageSync(key)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export const authState = reactive({
  accessToken: uni.getStorageSync(ACCESS_TOKEN_KEY) || '',
  refreshToken: uni.getStorageSync(REFRESH_TOKEN_KEY) || '',
  user: readJson(USER_KEY),
  account: readJson(ACCOUNT_KEY),
})

export const setSession = ({ accessToken, refreshToken, user, account }) => {
  authState.accessToken = accessToken || ''
  authState.refreshToken = refreshToken || ''
  authState.user = user || null
  authState.account = account || null

  if (authState.accessToken) {
    uni.setStorageSync(ACCESS_TOKEN_KEY, authState.accessToken)
  } else {
    uni.removeStorageSync(ACCESS_TOKEN_KEY)
  }

  if (authState.refreshToken) {
    uni.setStorageSync(REFRESH_TOKEN_KEY, authState.refreshToken)
  } else {
    uni.removeStorageSync(REFRESH_TOKEN_KEY)
  }

  if (authState.user) {
    uni.setStorageSync(USER_KEY, JSON.stringify(authState.user))
  } else {
    uni.removeStorageSync(USER_KEY)
  }

  if (authState.account) {
    uni.setStorageSync(ACCOUNT_KEY, JSON.stringify(authState.account))
  } else {
    uni.removeStorageSync(ACCOUNT_KEY)
  }
}

export const clearSession = () => {
  setSession({ accessToken: '', refreshToken: '', user: null, account: null })
}

export const getAccessToken = () => authState.accessToken || ''

export const getRefreshToken = () => authState.refreshToken || ''

export const isAuthenticated = () => Boolean(getAccessToken())
