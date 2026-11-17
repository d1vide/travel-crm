import type { RouteLocationRaw } from 'vue-router'
import { homePathFor } from '@/auth/navigation'
import type { Role } from '@/auth/roles'

declare module 'vue-router' {
  interface RouteMeta {
    /** Общедоступная страница (подборка, форма туристов): открыта всем, сессию не восстанавливает. */
    public?: boolean
    /** Страница только для гостя (вход): вошедшего сотрудника уводит в его раздел. */
    guestOnly?: boolean
    /** Имя раздела меню, который подсвечивается на вложенных страницах (карточка, форма). */
    section?: string
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
  meta: { public?: boolean; guestOnly?: boolean; roles?: readonly Role[] }
}

/**
 * Защита маршрутов. Это удобство интерфейса: окончательную проверку прав
 * сервер выполняет на каждом запросе независимо от того, что показал интерфейс.
 */
export function createAuthGuard(session: SessionLike) {
  return async (to: RouteLike): Promise<true | string | RouteLocationRaw> => {
    // Публичные страницы работают без сессии и не ждут её восстановления.
    if (to.meta.public) return true

    await session.ensureRestored()

    if (!session.isAuthenticated || !session.role) {
      if (to.meta.guestOnly) return true
      return { name: 'login', query: { redirect: to.fullPath } }
    }

    if (to.meta.guestOnly || to.path === '/') return homePathFor(session.role)
    if (to.meta.roles && !to.meta.roles.includes(session.role)) return { name: 'forbidden' }
    return true
  }
}
