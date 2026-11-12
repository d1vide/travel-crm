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

export interface HttpClient {
  get<T>(path: string): Promise<T>
  post<T>(path: string, body?: unknown): Promise<T>
  put<T>(path: string, body?: unknown): Promise<T>
  patch<T>(path: string, body?: unknown): Promise<T>
  delete<T = void>(path: string): Promise<T>
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
  ): Promise<{ response: Response; sentWith: string | null }> {
    const headers = new Headers({ Accept: 'application/json' })
    const sentWith = options.getAccessToken()
    if (sentWith) headers.set('Authorization', `Bearer ${sentWith}`)
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

  async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
    const first = await send(method, path, body)
    let response = first.response

    if (response.status === 401 && !path.startsWith(AUTH_PREFIX)) {
      // Токен мог обновиться, пока запрос был в пути: тогда достаточно повторить его.
      const alreadyRefreshed = options.getAccessToken() !== first.sentWith
      const token = alreadyRefreshed ? options.getAccessToken() : await refreshOnce()
      if (!token) {
        options.onAuthFailure()
        throw await apiErrorFromResponse(response)
      }
      response = (await send(method, path, body)).response
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
    post: (path, body) => request('POST', path, body),
    put: (path, body) => request('PUT', path, body),
    patch: (path, body) => request('PATCH', path, body),
    delete: (path) => request('DELETE', path),
  }
}
