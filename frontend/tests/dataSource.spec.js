import { describe, expect, it } from 'vitest'

import { dataSourceLabel, isLiveRealtimeSource } from '../src/utils/dataSource'

describe('data source labels', () => {
  it('separates live realtime from cached realtime', () => {
    expect(isLiveRealtimeSource('realtime_sina')).toBe(true)
    expect(isLiveRealtimeSource('realtime_cache')).toBe(false)
    expect(dataSourceLabel('realtime_sina')).toBe('盘中实时')
    expect(dataSourceLabel('realtime_cache')).toBe('实时缓存')
  })

  it('keeps fallback and empty labels explicit', () => {
    expect(dataSourceLabel('daily_fallback')).toBe('日线回退')
    expect(dataSourceLabel('', { emptyLabel: '规则结果' })).toBe('规则结果')
  })
})
