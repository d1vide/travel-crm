import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { ApiError } from '../errors'
import { requestLogin, requestLogout } from '../auth'

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const authBody = {
  access_token: 'access-1',
  user: { id: '3f2c7c52-0000-4000-8000-000000000001', full_name: 'Анна Смирнова', role: 'manager' },
}

describe('requestLogin', () => {
  let fetchMock: Mock<typeof fetch>

  beforeEach(() => {
    fetchMock = vi.fn<typeof fetch>()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('отправляет email и пароль на /api/auth/login и возвращает сессию', async () => {
    fetchMock.mockResolvedValue(json(200, authBody))

    const result = await requestLogin('manager@example.com', 'secret')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
        body: JSON.stringify({ email: 'manager@example.com', password: 'secret' }),
      }),
    )
    expect(result).toEqual({
      accessToken: 'access-1',
      user: {
        id: '3f2c7c52-0000-4000-8000-000000000001',
        fullName: 'Анна Смирнова',
        role: 'manager',
      },
    })
  })

  it('при отказе сервера бросает ApiError с сообщением сервера', async () => {
    fetchMock.mockResolvedValue(
      json(401, { code: 'unauthorized', message: 'Неверный email или пароль', fields: [] }),
    )

    await expect(requestLogin('a@b.c', 'bad')).rejects.toMatchObject({
      status: 401,
      message: 'Неверный email или пароль',
    })
  })

  it('при недоступном сервере бросает понятную сетевую ошибку', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(requestLogin('a@b.c', 'x')).rejects.toMatchObject({ code: 'network_error' })
  })

  it('не принимает ответ неожиданной формы', async () => {
    fetchMock.mockResolvedValue(json(200, { access_token: 'x' }))

    const error = await requestLogin('a@b.c', 'x').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ code: 'server_error' })
  })
})

describe('requestLogout', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('вызывает POST /api/auth/logout', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await requestLogout()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/logout',
      expect.objectContaining({ method: 'POST', credentials: 'same-origin' }),
    )
  })

  it('не бросает ошибку, если сервер недоступен', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(new TypeError('offline')))

    await expect(requestLogout()).resolves.toBeUndefined()
  })
})
