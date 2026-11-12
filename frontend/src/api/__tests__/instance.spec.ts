import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import { initHttp, resetHttp, useHttp } from '../instance'

describe('useHttp', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetHttp()
  })

  it('до инициализации сообщает, что клиент не настроен', () => {
    expect(() => useHttp()).toThrow('HTTP-клиент не инициализирован')
  })

  it('после инициализации возвращает клиент, который ходит в /api', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => new Response('{"ok":true}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const router = createRouter({ history: createMemoryHistory(), routes: [] })
    initHttp(useSessionStore(), router)

    await useHttp().get('/tours')

    expect(fetchMock).toHaveBeenCalledWith('/api/tours', expect.anything())
    vi.unstubAllGlobals()
  })
})
