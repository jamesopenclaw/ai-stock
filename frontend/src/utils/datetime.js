export const formatLocalDateTime = (value, options = {}) => {
  if (!value) return '-'
  const raw = String(value).trim()
  if (!raw) return '-'

  let normalized = raw
  const hasTimezone = /([zZ]|[+-]\d{2}:\d{2})$/.test(raw)
  if (!hasTimezone) {
    normalized = raw.replace(' ', 'T')
    if (options.assumeUtc) {
      normalized = `${normalized}Z`
    }
  }

  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) {
    return raw
  }

  const year = parsed.getFullYear()
  const month = String(parsed.getMonth() + 1).padStart(2, '0')
  const day = String(parsed.getDate()).padStart(2, '0')
  const hours = String(parsed.getHours()).padStart(2, '0')
  const minutes = String(parsed.getMinutes()).padStart(2, '0')
  const seconds = String(parsed.getSeconds()).padStart(2, '0')

  if (options.timeOnly) {
    return `${hours}:${minutes}:${seconds}`
  }

  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

export const formatLocalTime = (value, options = {}) => {
  const formatted = formatLocalDateTime(value, { ...options, timeOnly: true })
  return formatted === '-' ? formatted : formatted
}
