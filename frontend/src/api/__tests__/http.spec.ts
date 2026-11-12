import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../errors'
import { createHttpClient } from '../http'

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>
type Call = { url: string; init: RequestInit }

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function setup(
  handler: Handler,
  options: { token?: string | null; refreshTo?: string | null } = {},
) {
  const calls: Call[] = []
  const fetchImpl = vi.fn<typeof fetch>(async (input, init = {}) => {
    calls.push({ url: String(input), init })
    return handler(String(input), init)
  })
  let token = options.token === undefined ? 'old-token' : options.token
  const refreshAccessToken = vi.fn<() => Promise<string | null>>(async () => {
    const next = options.refreshTo === undefined ? 'new-token' : options.refreshTo
    if (next) token = next
    return next
  })
  const onAuthFailure = vi.fn<() => void>()
  const client = createHttpClient({
    fetchImpl,
    getAccessToken: () => token,
    refreshAccessToken,
    onAuthFailure,
  })
  return { client, calls, refreshAccessToken, onAuthFailure }
}

function callAt(calls: Call[], index: number): Call {
  const call = calls[index]
  if (!call) throw new Error(`Вызова fetch №${index} не было`)
  return call
}

function authHeader(call: Call): string | null {
  return new Headers(call.init.headers).get('Authorization')
}

describe('createHttpClient', () => {
  it('запрашивает /api, подставляет токен и разбирает JSON', async () => {
    const { client, calls } = setup(() => json(200, { id: 7 }))

    const result = await client.get<{ id: number }>('/clients/7')

    expect(result).toEqual({ id: 7 })
    expect(callAt(calls, 0).url).toBe('/api/clients/7')
    expect(authHeader(callAt(calls, 0))).toBe('Bearer old-token')
  })

  it('не добавляет заголовок авторизации, пока токена нет', async () => {
    const { client, calls } = setup(() => json(200, {}), { token: null })

    await client.get('/tours')

    expect(authHeader(callAt(calls, 0))).toBeNull()
  })

  it('отправляет тело запроса как JSON', async () => {
    const { client, calls } = setup(() => json(201, { id: 1 }))

    await client.post('/clients', { fullName: 'Иван Петров' })

    expect(callAt(calls, 0).init.method).toBe('POST')
    expect(new Headers(callAt(calls, 0).init.headers).get('Content-Type')).toBe('application/json')
    expect(callAt(calls, 0).init.body).toBe(JSON.stringify({ fullName: 'Иван Петров' }))
  })

  it('возвращает undefined на ответ 204 без тела', async () => {
    const { client } = setup(() => new Response(null, { status: 204 }))

    await expect(client.delete('/notifications/3')).resolves.toBeUndefined()
  })

  it('при 401 один раз обновляет токен и повторяет запрос', async () => {
    const { client, calls, refreshAccessToken } = setup((_url, init) =>
      new Headers(init.headers).get('Authorization') === 'Bearer new-token'
        ? json(200, { ok: true })
        : json(401, { code: 'token_expired', message: 'Срок действия истёк' }),
    )

    const result = await client.get<{ ok: boolean }>('/requests')

    expect(result).toEqual({ ok: true })
    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
    expect(calls).toHaveLength(2)
    expect(authHeader(callAt(calls, 1))).toBe('Bearer new-token')
  })

  it('параллельные запросы с 401 ждут один общий refresh', async () => {
    const { client, refreshAccessToken } = setup((_url, init) =>
      new Headers(init.headers).get('Authorization') === 'Bearer new-token'
        ? json(200, { ok: true })
        : json(401, {}),
    )

    const results = await Promise.all([client.get('/a'), client.get('/b'), client.get('/c')])

    expect(results).toHaveLength(3)
    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
  })

  it('запрос со старым токеном повторяется без нового refresh, если токен уже обновили', async () => {
    let releaseSlow!: () => void
    const slowGate = new Promise<void>((resolve) => {
      releaseSlow = resolve
    })
    const { client, refreshAccessToken } = setup(async (url, init) => {
      if (new Headers(init.headers).get('Authorization') === 'Bearer new-token') {
        return json(200, { ok: true })
      }
      if (url === '/api/slow') await slowGate
      return json(401, {})
    })

    const slow = client.get('/slow')
    await client.get('/fast')
    releaseSlow()

    await expect(slow).resolves.toEqual({ ok: true })
    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
  })

  it('если обновить токен не удалось, сообщает об этом и отклоняет запрос', async () => {
    const { client, onAuthFailure } = setup(() => json(401, {}), { refreshTo: null })

    await expect(client.get('/requests')).rejects.toMatchObject({
      status: 401,
      code: 'unauthorized',
    })
    expect(onAuthFailure).toHaveBeenCalledTimes(1)
  })

  it('не зацикливается, если после обновления токена снова приходит 401', async () => {
    const { client, calls, refreshAccessToken, onAuthFailure } = setup(() => json(401, {}))

    await expect(client.get('/requests')).rejects.toBeInstanceOf(ApiError)

    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
    expect(calls).toHaveLength(2)
    expect(onAuthFailure).toHaveBeenCalledTimes(1)
  })

  it('не пытается обновлять токен для запросов входа', async () => {
    const { client, refreshAccessToken, onAuthFailure } = setup(() =>
      json(401, { code: 'invalid_credentials', message: 'Неверный email или пароль' }),
    )

    await expect(
      client.post('/auth/login', { email: 'a@b.c', password: 'x' }),
    ).rejects.toMatchObject({
      code: 'invalid_credentials',
      message: 'Неверный email или пароль',
    })
    expect(refreshAccessToken).not.toHaveBeenCalled()
    expect(onAuthFailure).not.toHaveBeenCalled()
  })

  it('превращает ошибку сервера в ApiError с ошибками полей', async () => {
    const { client } = setup(() =>
      json(422, {
        code: 'validation_error',
        message: 'Проверьте форму',
        fields: [{ field: 'budget', message: 'Бюджет не может быть отрицательным' }],
      }),
    )

    await expect(client.post('/requests', { budget: -1 })).rejects.toMatchObject({
      status: 422,
      fields: [{ field: 'budget', message: 'Бюджет не может быть отрицательным' }],
    })
  })

  it('превращает сетевой сбой в понятную ошибку', async () => {
    const { client } = setup(() => {
      throw new TypeError('Failed to fetch')
    })

    await expect(client.get('/tours')).rejects.toMatchObject({
      status: 0,
      code: 'network_error',
    })
  })
})
