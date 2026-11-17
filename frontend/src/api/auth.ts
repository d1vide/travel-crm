import { isRole, type SessionUser } from '@/auth/roles'
import { ApiError, apiErrorFromNetwork, apiErrorFromResponse } from './errors'

export interface AuthResult {
  accessToken: string
  user: SessionUser
}

/**
 * Разбирает ответ входа и обновления токена. Имена полей (`access_token`, `full_name`)
 * закрепляются в контракте API (#7); при расхождении правится только эта функция.
 */
export function parseAuthResponse(body: unknown): AuthResult | null {
  if (!body || typeof body !== 'object') return null
  const { access_token: accessToken, user } = body as Record<string, unknown>
  if (typeof accessToken !== 'string' || !user || typeof user !== 'object') return null
  const { id, full_name: fullName, role } = user as Record<string, unknown>
  if ((typeof id !== 'string' && typeof id !== 'number') || typeof fullName !== 'string') {
    return null
  }
  if (!isRole(role)) return null
  return { accessToken, user: { id: String(id), fullName, role } }
}

/**
 * Запрашивает новый access-токен по refresh-cookie. Использует обычный fetch,
 * а не общий HTTP-клиент: клиент сам зависит от результата обновления токена.
 */
export async function requestRefresh(): Promise<AuthResult | null> {
  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) return null
    return parseAuthResponse(await response.json())
  } catch {
    return null
  }
}

async function postAuth(path: string, body?: unknown): Promise<Response> {
  const headers = new Headers({ Accept: 'application/json' })
  const init: RequestInit = { method: 'POST', credentials: 'same-origin', headers }
  if (body !== undefined) {
    headers.set('Content-Type', 'application/json')
    init.body = JSON.stringify(body)
  }
  try {
    return await fetch(`/api${path}`, init)
  } catch (cause) {
    throw apiErrorFromNetwork(cause)
  }
}

/** Вход по email и паролю. При отказе бросает ApiError с сообщением сервера. */
export async function requestLogin(email: string, password: string): Promise<AuthResult> {
  const response = await postAuth('/auth/login', { email, password })
  if (!response.ok) throw await apiErrorFromResponse(response)
  const result = parseAuthResponse(await response.json().catch(() => null))
  if (!result) throw new ApiError(500, 'server_error', 'Сервер вернул неожиданный ответ')
  return result
}

/** Отзывает refresh-токен на сервере. Сбой не мешает выйти локально, поэтому ошибки не пробрасываются. */
export async function requestLogout(): Promise<void> {
  try {
    await postAuth('/auth/logout')
  } catch {
    // Локальный выход выполняется независимо от ответа сервера.
  }
}
