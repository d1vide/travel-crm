import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { initHttp, resetHttp } from '@/api/instance'
import { createAppRouter } from '@/router'
import { useSessionStore } from '@/stores/session'
import { jsonResponse, withProviders } from '@/test/helpers'
import ProfileView from '../ProfileView.vue'

async function render(response: Response) {
  const pinia = createPinia()
  setActivePinia(pinia)
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async () => response),
  )
  const router = createAppRouter(createMemoryHistory())
  const session = useSessionStore()
  session.setSession({
    accessToken: 'token',
    user: { id: '1', fullName: 'Анна Смирнова', role: 'manager' },
  })
  await router.push('/profile')
  await router.isReady()
  initHttp(session, router)
  const wrapper = mount(withProviders(ProfileView), { global: { plugins: [pinia, router] } })
  await flushPromises()
  return wrapper
}

describe('ProfileView', () => {
  afterEach(() => {
    resetHttp()
    vi.unstubAllGlobals()
  })

  it('показывает ФИО, отдел, должность, рабочий телефон и email', async () => {
    const wrapper = await render(
      jsonResponse(200, {
        id: '1',
        full_name: 'Анна Смирнова',
        role: 'manager',
        email: 'anna@example.com',
        department: 'Отдел продаж',
        position: 'Старший менеджер',
        work_phone: '+7 495 000-00-00',
      }),
    )
    const text = wrapper.text()

    for (const value of [
      'Анна Смирнова',
      'Отдел продаж',
      'Старший менеджер',
      '+7 495 000-00-00',
      'anna@example.com',
      'Менеджер',
    ]) {
      expect(text).toContain(value)
    }
  })

  it('незаполненные поля показывает прочерком', async () => {
    const wrapper = await render(
      jsonResponse(200, { id: '1', full_name: 'Анна Смирнова', role: 'manager' }),
    )

    expect(wrapper.text()).toContain('Анна Смирнова')
    expect(wrapper.findAll('[data-test="profile-empty"]').length).toBe(4)
  })

  it('при ошибке загрузки предлагает повторить', async () => {
    const wrapper = await render(
      jsonResponse(500, { code: 'server_error', message: 'Сбой', fields: [] }),
    )

    expect(wrapper.text()).toContain('Повторить')
  })
})
