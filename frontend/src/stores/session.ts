import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { requestRefresh, type AuthResult } from '@/api/auth'
import type { SessionUser } from '@/auth/roles'

export const useSessionStore = defineStore('session', () => {
  // Access-токен хранится только в памяти; refresh-токен лежит в httpOnly-cookie.
  const accessToken = ref<string | null>(null)
  const user = ref<SessionUser | null>(null)
  let restoring: Promise<void> | null = null

  const isAuthenticated = computed(() => accessToken.value !== null && user.value !== null)
  const role = computed(() => user.value?.role ?? null)

  function setSession(result: AuthResult) {
    accessToken.value = result.accessToken
    user.value = result.user
  }

  function clearSession() {
    accessToken.value = null
    user.value = null
  }

  /** Обновляет токен по refresh-cookie. Возвращает новый токен или null, если сессии нет. */
  async function refresh(): Promise<string | null> {
    const result = await requestRefresh()
    if (!result) {
      clearSession()
      return null
    }
    setSession(result)
    return result.accessToken
  }

  /** Восстанавливает сессию при старте приложения: один раз, сколько бы раз ни вызвали. */
  function ensureRestored(): Promise<void> {
    if (isAuthenticated.value) return Promise.resolve()
    restoring ??= refresh().then(() => undefined)
    return restoring
  }

  return {
    accessToken,
    user,
    isAuthenticated,
    role,
    setSession,
    clearSession,
    refresh,
    ensureRestored,
  }
})
