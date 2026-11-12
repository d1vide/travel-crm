import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSessionStore } from '../session'

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const managerResponse = {
  access_token: 'access-1',
  user: { id: '42', full_name: 'Анна Смирнова', role: 'manager' },
}

describe('session store', () => {
  let fetchMock: Mock<typeof fetch>

  beforeEach(() => {
    setActivePinia(createPinia())
    fetchMock = vi.fn<typeof fetch>()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('в начале сессии нет', () => {
    const session = useSessionStore()

    expect(session.isAuthenticated).toBe(false)
    expect(session.accessToken).toBeNull()
    expect(session.role).toBeNull()
  })

  it('refresh сохраняет токен и пользователя из ответа сервера', async () => {
    fetchMock.mockResolvedValue(json(200, managerResponse))
    const session = useSessionStore()

    const token = await session.refresh()

    expect(token).toBe('access-1')
    expect(session.isAuthenticated).toBe(true)
    expect(session.role).toBe('manager')
    expect(session.user).toEqual({ id: '42', fullName: 'Анна Смирнова', role: 'manager' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/refresh',
      expect.objectContaining({ method: 'POST', credentials: 'same-origin' }),
    )
  })

  it('refresh с отказом сервера очищает сессию и возвращает null', async () => {
    fetchMock.mockResolvedValueOnce(json(200, managerResponse))
    const session = useSessionStore()
    await session.refresh()

    fetchMock.mockResolvedValueOnce(json(401, { code: 'token_expired', message: 'Срок истёк' }))
    const token = await session.refresh()

    expect(token).toBeNull()
    expect(session.isAuthenticated).toBe(false)
    expect(session.user).toBeNull()
  })

  it('refresh не принимает ответ с неизвестной ролью', async () => {
    fetchMock.mockResolvedValue(
      json(200, { access_token: 'x', user: { id: '1', full_name: 'Тест', role: 'admin' } }),
    )
    const session = useSessionStore()

    expect(await session.refresh()).toBeNull()
    expect(session.isAuthenticated).toBe(false)
  })

  it('refresh при сетевом сбое возвращает null, а не бросает ошибку', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const session = useSessionStore()

    await expect(session.refresh()).resolves.toBeNull()
  })

  it('ensureRestored восстанавливает сессию один раз при повторных вызовах', async () => {
    fetchMock.mockResolvedValue(json(200, managerResponse))
    const session = useSessionStore()

    await Promise.all([session.ensureRestored(), session.ensureRestored()])
    await session.ensureRestored()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(session.isAuthenticated).toBe(true)
  })

  it('ensureRestored не обращается к серверу, если сессия уже есть', async () => {
    const session = useSessionStore()
    session.setSession({
      accessToken: 'token',
      user: { id: '1', fullName: 'Тест', role: 'head' },
    })

    await session.ensureRestored()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(session.isAuthenticated).toBe(true)
  })

  it('clearSession сбрасывает токен и пользователя', async () => {
    fetchMock.mockResolvedValue(json(200, managerResponse))
    const session = useSessionStore()
    await session.refresh()

    session.clearSession()

    expect(session.accessToken).toBeNull()
    expect(session.user).toBeNull()
    expect(session.isAuthenticated).toBe(false)
  })
})
