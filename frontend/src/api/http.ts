import { apiErrorFromNetwork, apiErrorFromResponse } from './errors'

export interface HttpClientOptions {
  /** Префикс API. В dev его проксирует Vite, в Docker — nginx. */
  baseUrl?: string
  getAccessToken: () => string | null
  /** Запрашивает новый access-токен по refresh-cookie; null — если обновить не удалось. */
  refreshAccessToken: () => Promise<string | null>
  /** Вызывается, когда сессию восстановить нельзя и нужен повторный вход. */
  onAuthFailure: () => void
  fetchImpl?: typeof fetch
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface RequestOptions {
  /**
   * Ключ идемпотентности команды (UUID). Новая команда получает новый ключ, повтор того же
   * запроса — прежний. При повторе после обновления токена клиент сохраняет исходный ключ.
   */
  idempotencyKey?: string
}

/** Создаёт ключ идемпотентности для новой команды. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}

export interface HttpClient {
  get<T>(path: string): Promise<T>
  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T>
  put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T>
  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T>
  delete<T = void>(path: string, options?: RequestOptions): Promise<T>
}

const AUTH_PREFIX = '/auth/'

export function createHttpClient(options: HttpClientOptions): HttpClient {
  const baseUrl = options.baseUrl ?? '/api'
  const doFetch: typeof fetch = options.fetchImpl ?? ((input, init) => fetch(input, init))
  let refreshing: Promise<string | null> | null = null

  function refreshOnce(): Promise<string | null> {
    refreshing ??= options.refreshAccessToken().finally(() => {
      refreshing = null
    })
    return refreshing
  }

  async function send(
    method: Method,
    path: string,
    body: unknown,
    requestOptions: RequestOptions,
  ): Promise<{ response: Response; sentWith: string | null }> {
    const headers = new Headers({ Accept: 'application/json' })
    const sentWith = options.getAccessToken()
    if (sentWith) headers.set('Authorization', `Bearer ${sentWith}`)
    if (requestOptions.idempotencyKey) {
      headers.set('Idempotency-Key', requestOptions.idempotencyKey)
    }
    const init: RequestInit = { method, headers, credentials: 'same-origin' }
    if (body !== undefined) {
      headers.set('Content-Type', 'application/json')
      init.body = JSON.stringify(body)
    }
    try {
      return { response: await doFetch(`${baseUrl}${path}`, init), sentWith }
    } catch (cause) {
      throw apiErrorFromNetwork(cause)
    }
  }

  async function request<T>(
    method: Method,
    path: string,
    body?: unknown,
    requestOptions: RequestOptions = {},
  ): Promise<T> {
    const first = await send(method, path, body, requestOptions)
    let response = first.response

    if (response.status === 401 && !path.startsWith(AUTH_PREFIX)) {
      // Токен мог обновиться, пока запрос был в пути: тогда достаточно повторить его.
      const alreadyRefreshed = options.getAccessToken() !== first.sentWith
      const token = alreadyRefreshed ? options.getAccessToken() : await refreshOnce()
      if (!token) {
        options.onAuthFailure()
        throw await apiErrorFromResponse(response)
      }
      response = (await send(method, path, body, requestOptions)).response
      if (response.status === 401) {
        options.onAuthFailure()
        throw await apiErrorFromResponse(response)
      }
    }

    if (!response.ok) throw await apiErrorFromResponse(response)
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  }

  return {
    get: (path) => request('GET', path),
    post: (path, body, opts) => request('POST', path, body, opts),
    put: (path, body, opts) => request('PUT', path, body, opts),
    patch: (path, body, opts) => request('PATCH', path, body, opts),
    delete: (path, opts) => request('DELETE', path, undefined, opts),
  }
}
