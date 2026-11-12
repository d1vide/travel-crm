import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import { createAppHttpClient } from '../client'

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const refreshResponse = {
  access_token: 'fresh',
  user: { id: '1', full_name: 'Анна', role: 'manager' },
}

async function setup(fetchMock: Mock<typeof fetch>) {
  vi.stubGlobal('fetch', fetchMock)
  const session = useSessionStore()
  session.setSession({ accessToken: 'stale', user: { id: '1', fullName: 'Анна', role: 'manager' } })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'login', component: { template: '<div />' } },
      { path: '/clients', name: 'clients', component: { template: '<div />' } },
    ],
  })
  await router.push('/clients')
  await router.isReady()
  return { session, router, http: createAppHttpClient(session, router) }
}

describe('createAppHttpClient', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('подставляет токен сессии и после 401 обновляет его через refresh-cookie', async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input, init = {}) => {
      if (String(input) === '/api/auth/refresh') return json(200, refreshResponse)
      return new Headers(init.headers).get('Authorization') === 'Bearer fresh'
        ? json(200, { ok: true })
        : json(401, {})
    })
    const { http, session } = await setup(fetchMock)

    await expect(http.get('/clients')).resolves.toEqual({ ok: true })
    expect(session.accessToken).toBe('fresh')
  })

  it('если сессию восстановить нельзя, очищает её и отправляет на вход с возвратом назад', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => json(401, {}))
    const { http, session, router } = await setup(fetchMock)

    await expect(http.get('/clients')).rejects.toMatchObject({ status: 401 })

    expect(session.isAuthenticated).toBe(false)
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    expect(router.currentRoute.value.query.redirect).toBe('/clients')
  })
})
