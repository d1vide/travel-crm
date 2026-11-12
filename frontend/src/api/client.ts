import type { Router } from 'vue-router'
import { createHttpClient, type HttpClient } from './http'

interface SessionLike {
  accessToken: string | null
  refresh(): Promise<string | null>
  clearSession(): void
}

/** Собирает HTTP-клиент приложения: токен берётся из сессии, при потере сессии открывается вход. */
export function createAppHttpClient(session: SessionLike, router: Router): HttpClient {
  return createHttpClient({
    getAccessToken: () => session.accessToken,
    refreshAccessToken: () => session.refresh(),
    onAuthFailure: () => {
      session.clearSession()
      const redirect = router.currentRoute.value.fullPath
      void router.push({ name: 'login', query: { redirect } })
    },
  })
}
