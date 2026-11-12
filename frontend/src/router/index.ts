import { type Component } from 'vue'
import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { NAVIGATION } from '@/auth/navigation'

const sectionViews: Record<string, () => Promise<{ default: Component }>> = {
  requests: () => import('@/views/RequestsView.vue'),
  clients: () => import('@/views/ClientsView.vue'),
  tours: () => import('@/views/ToursView.vue'),
  payments: () => import('@/views/PaymentsView.vue'),
  workspace: () => import('@/views/WorkspaceView.vue'),
  reports: () => import('@/views/ReportsView.vue'),
}

export function createAppRouter(
  history: RouterHistory = createWebHistory(import.meta.env.BASE_URL),
) {
  // Разделы строятся из того же списка, что и меню, поэтому права в них не расходятся.
  const sections: RouteRecordRaw[] = NAVIGATION.map((item) => {
    const component = sectionViews[item.name]
    if (!component) throw new Error(`Для раздела «${item.name}» не задана страница`)
    return { path: item.path, name: item.name, component, meta: { roles: item.roles } }
  })

  return createRouter({
    history,
    routes: [
      {
        path: '/login',
        name: 'login',
        component: () => import('@/views/LoginView.vue'),
        meta: { public: true },
      },
      {
        path: '/',
        component: () => import('@/layouts/MainLayout.vue'),
        children: [
          // С корня направляет защита маршрутов: она знает роль и выбирает раздел.
          { path: '', name: 'home', component: { render: () => null } },
          ...sections,
          {
            path: '/forbidden',
            name: 'forbidden',
            component: () => import('@/views/ForbiddenView.vue'),
          },
          {
            path: '/:pathMatch(.*)*',
            name: 'not-found',
            component: () => import('@/views/NotFoundView.vue'),
          },
        ],
      },
    ],
  })
}
