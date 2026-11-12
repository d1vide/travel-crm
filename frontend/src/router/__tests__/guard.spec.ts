import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { Role } from '@/auth/roles'
import { useSessionStore } from '@/stores/session'
import { createAuthGuard } from '../guard'

function route(path: string, meta: { public?: boolean; roles?: readonly Role[] } = {}) {
  return { path, fullPath: path, meta }
}

function signIn(role: Role) {
  useSessionStore().setSession({
    accessToken: 'token',
    user: { id: '1', fullName: 'Тест', role },
  })
}

describe('createAuthGuard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // Нет refresh-cookie: попытка восстановить сессию завершается отказом сервера.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('без входа отправляет на страницу входа и запоминает, куда шёл пользователь', async () => {
    const guard = createAuthGuard(useSessionStore())

    const result = await guard(route('/clients', { roles: ['manager', 'head'] }))

    expect(result).toEqual({ name: 'login', query: { redirect: '/clients' } })
  })

  it('перед решением пытается восстановить сессию по refresh-cookie', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            access_token: 'restored',
            user: { id: '5', full_name: 'Пётр', role: 'manager' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    const guard = createAuthGuard(useSessionStore())

    const result = await guard(route('/clients', { roles: ['manager', 'head'] }))

    expect(result).toBe(true)
  })

  it('пропускает публичные страницы без входа', async () => {
    const guard = createAuthGuard(useSessionStore())

    expect(await guard(route('/login', { public: true }))).toBe(true)
  })

  it('уже вошедшего пользователя со страницы входа ведёт в его раздел', async () => {
    signIn('accountant')
    const guard = createAuthGuard(useSessionStore())

    expect(await guard(route('/login', { public: true }))).toBe('/payments')
  })

  it('с корня ведёт в первый доступный роли раздел', async () => {
    signIn('manager')
    const guard = createAuthGuard(useSessionStore())

    expect(await guard(route('/'))).toBe('/requests')
  })

  it('не пускает менеджера в отчётность', async () => {
    signIn('manager')
    const guard = createAuthGuard(useSessionStore())

    const result = await guard(route('/reports', { roles: ['head'] }))

    expect(result).toEqual({ name: 'forbidden' })
  })

  it('не пускает бухгалтера в заявки', async () => {
    signIn('accountant')
    const guard = createAuthGuard(useSessionStore())

    const result = await guard(route('/requests', { roles: ['manager', 'head'] }))

    expect(result).toEqual({ name: 'forbidden' })
  })

  it('пропускает роль, которой раздел доступен', async () => {
    signIn('head')
    const guard = createAuthGuard(useSessionStore())

    expect(await guard(route('/reports', { roles: ['head'] }))).toBe(true)
  })
})
