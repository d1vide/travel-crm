import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import type { Role } from '@/auth/roles'
import { createAppRouter } from '@/router'
import { useSessionStore } from '@/stores/session'
import MainLayout from '../MainLayout.vue'

async function render(role: Role, fullName = 'Анна Смирнова') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.setSession({ accessToken: 'token', user: { id: '1', fullName, role } })
  const router = createAppRouter(createMemoryHistory())
  await router.push('/forbidden')
  await router.isReady()
  const wrapper = mount(MainLayout, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, router, session }
}

describe('MainLayout', () => {
  beforeEach(() => {
    globalThis.ResizeObserver ??= class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  })

  it('показывает менеджеру только его разделы', async () => {
    const { wrapper } = await render('manager')
    const text = wrapper.text()

    expect(text).toContain('Заявки')
    expect(text).toContain('Клиенты')
    expect(text).toContain('Каталог туров')
    expect(text).not.toContain('Отчёт')
    expect(text).not.toContain('Оплаты и возвраты')
  })

  it('показывает бухгалтеру только оплаты и возвраты', async () => {
    const { wrapper } = await render('accountant')
    const text = wrapper.text()

    expect(text).toContain('Оплаты и возвраты')
    expect(text).not.toContain('Заявки')
  })

  it('показывает имя пользователя и его роль', async () => {
    const { wrapper } = await render('head', 'Иван Орлов')

    expect(wrapper.text()).toContain('Иван Орлов')
    expect(wrapper.text()).toContain('Руководитель')
  })

  it('кнопка «Выйти» очищает сессию и открывает страницу входа', async () => {
    const { wrapper, router, session } = await render('manager')

    const logout = wrapper.findAll('button').find((b) => b.text() === 'Выйти')
    await logout!.trigger('click')

    expect(session.isAuthenticated).toBe(false)
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
  })
})
