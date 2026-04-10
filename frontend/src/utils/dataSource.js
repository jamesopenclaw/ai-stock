export const isLiveRealtimeSource = (source) => {
  const value = String(source || '').trim()
  return value.startsWith('realtime_') && value !== 'realtime_cache'
}

export const dataSourceLabel = (source, { emptyLabel = '规则结果' } = {}) => {
  const value = String(source || '').trim()
  if (!value) return emptyLabel
  if (value === 'realtime_cache') return '实时缓存'
  if (value === 'unavailable') return '实时不可用'
  if (isLiveRealtimeSource(value)) return '盘中实时'
  if (value === 'mock') return '模拟数据'
  if (value === 'index_daily') return '指数日线'
  if (value === 'daily' || value === 'daily_fallback' || value === 'bak_daily') return '日线回退'
  return '日线回退'
}
