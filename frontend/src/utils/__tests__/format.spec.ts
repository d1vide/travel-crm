import { describe, expect, it } from 'vitest'
import { formatDate, formatDateTime } from '../format'

describe('formatDate', () => {
  it('показывает дату события в московском времени', () => {
    // 21:30 UTC уже следующий день в Москве (UTC+3)
    expect(formatDate('2026-11-01T21:30:00Z')).toBe('02.11.2026')
  })
})

describe('formatDateTime', () => {
  it('показывает дату и время в московском времени', () => {
    expect(formatDateTime('2026-11-01T09:05:00Z')).toBe('01.11.2026, 12:05')
  })
})
