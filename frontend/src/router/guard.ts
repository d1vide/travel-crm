import type { RouteLocationRaw } from 'vue-router'
import { homePathFor } from '@/auth/navigation'
import type { Role } from '@/auth/roles'

declare module 'vue-router' {
  interface RouteMeta {
    /** Страница доступна без входа (например, вход). */
    public?: boolean
    /** Роли, которым доступна страница. Без поля страницу видит любой вошедший сотрудник. */
    roles?: readonly Role[]
  }
}

interface SessionLike {
  isAuthenticated: boolean
  role: Role | null
  ensureRestored(): Promise<void>
}

interface RouteLike {
  path: string
  fullPath: string
  meta: { public?: boolean; roles?: readonly Role[] }
}

/**
 * Защита маршрутов. Это удобство интерфейса: окончательную проверку прав
 * сервер выполняет на каждом запросе независимо от того, что показал интерфейс.
 */
export function createAuthGuard(session: SessionLike) {
  return async (to: RouteLike): Promise<true | string | RouteLocationRaw> => {
    await session.ensureRestored()

    if (!session.isAuthenticated || !session.role) {
      if (to.meta.public) return true
      return { name: 'login', query: { redirect: to.fullPath } }
    }

    if (to.meta.public || to.path === '/') return homePathFor(session.role)
    if (to.meta.roles && !to.meta.roles.includes(session.role)) return { name: 'forbidden' }
    return true
  }
}
