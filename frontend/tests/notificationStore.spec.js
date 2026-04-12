import { beforeEach, describe, expect, it, vi } from 'vitest'

const notificationApi = {
  settings: vi.fn(),
  updateSettings: vi.fn(),
  summary: vi.fn(),
  testWecom: vi.fn(),
}

vi.mock('../src/api', () => ({
  notificationApi,
}))

describe('notification store settings', () => {
  beforeEach(async () => {
    window.sessionStorage.clear()
    window.localStorage.clear()
    notificationApi.settings.mockReset()
    notificationApi.updateSettings.mockReset()
    notificationApi.summary.mockReset()
    notificationApi.testWecom.mockReset()

    const { authState, clearSession } = await import('../src/auth')
    clearSession()
    authState.account = { id: 'acct-001', account_code: 'ACC001', account_name: '测试账户' }

    const { useNotificationStore } = await import('../src/stores/notificationStore')
    useNotificationStore().resetState()
  })

  it('loads and persists account-scoped wecom webhook settings', async () => {
    const payload = {
      in_app_enabled: true,
      wecom_enabled: true,
      wecom_webhook_url: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-001',
      rules: { holding_to_sell: 'high' },
      quiet_windows: [{ start: '11:30', end: '13:00' }],
    }
    notificationApi.settings.mockResolvedValue({ data: { data: payload } })
    notificationApi.updateSettings.mockResolvedValue({ data: { data: payload } })
    notificationApi.summary.mockResolvedValue({ data: { data: { unread_count: 0, critical_count: 0, latest_items: [] } } })

    const { useNotificationStore } = await import('../src/stores/notificationStore')
    const store = useNotificationStore()

    const loaded = await store.loadSettings({ force: true })
    expect(loaded.wecom_webhook_url).toBe(payload.wecom_webhook_url)

    const updated = await store.updateSettings(payload)
    expect(updated.wecom_webhook_url).toBe(payload.wecom_webhook_url)
  })

  it('delegates wecom test requests to notification api', async () => {
    notificationApi.testWecom.mockResolvedValue({ data: { data: { success: true } } })

    const { useNotificationStore } = await import('../src/stores/notificationStore')
    const store = useNotificationStore()

    const result = await store.testWecom({
      webhook_url: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-001',
    })

    expect(result).toBe(true)
    expect(notificationApi.testWecom).toHaveBeenCalledWith({
      webhook_url: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-001',
    })
  })
})
