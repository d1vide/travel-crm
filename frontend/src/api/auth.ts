import { isRole, type SessionUser } from '@/auth/roles'

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
