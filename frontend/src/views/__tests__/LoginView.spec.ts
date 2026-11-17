import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { createAppRouter } from '@/router'
import { useSessionStore } from '@/stores/session'
import LoginView from '../LoginView.vue'

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const loginOk = {
  access_token: 'access-1',
  user: { id: '1', full_name: 'Анна Смирнова', role: 'manager' },
}

async function render(query = '') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createAppRouter(createMemoryHistory())
  await router.push(`/login${query}`)
  await router.isReady()
  const wrapper = mount(LoginView, {
    attachTo: document.body,
    global: { plugins: [pinia, router] },
  })
  return { wrapper, router, session: useSessionStore() }
}

type Wrapper = Awaited<ReturnType<typeof render>>['wrapper']

async function submit(wrapper: Wrapper, email: string, password: string) {
  if (email) await wrapper.find('input[type="text"]').setValue(email)
  if (password) await wrapper.find('input[type="password"]').setValue(password)
  const button = wrapper.findAll('button').find((b) => b.text() === 'Войти')
  await button!.trigger('click')
  await flushPromises()
}

describe('LoginView', () => {
  let fetchMock: Mock<typeof fetch>

  beforeEach(() => {
    fetchMock = vi.fn<typeof fetch>()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.unstubAllGlobals()
  })

  it('не отправляет пустую форму и показывает, что заполнить', async () => {
    const { wrapper } = await render()

    await submit(wrapper, '', '')

    expect(wrapper.text()).toContain('Укажите email')
    expect(wrapper.text()).toContain('Укажите пароль')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('отправляет данные и после входа открывает первый раздел роли', async () => {
    fetchMock.mockResolvedValue(json(200, loginOk))
    const { wrapper, router, session } = await render()

    await submit(wrapper, 'manager@example.com', 'secret')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/login',
      expect.objectContaining({
        body: JSON.stringify({ email: 'manager@example.com', password: 'secret' }),
      }),
    )
    expect(session.isAuthenticated).toBe(true)
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/requests'))
  })

  it('после входа возвращает на страницу, с которой пришёл пользователь', async () => {
    fetchMock.mockResolvedValue(json(200, loginOk))
    const { wrapper, router } = await render('?redirect=/clients')

    await submit(wrapper, 'manager@example.com', 'secret')

    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/clients'))
  })

  it('показывает сообщение сервера при неверных данных и остаётся на входе', async () => {
    fetchMock.mockResolvedValue(
      json(401, { code: 'unauthorized', message: 'Неверный email или пароль', fields: [] }),
    )
    const { wrapper, router, session } = await render()

    await submit(wrapper, 'manager@example.com', 'wrong')

    expect(wrapper.text()).toContain('Неверный email или пароль')
    expect(session.isAuthenticated).toBe(false)
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('не переходит на внешний адрес из параметра redirect', async () => {
    fetchMock.mockResolvedValue(json(200, loginOk))
    const { wrapper, router } = await render('?redirect=https://evil.example/')

    await submit(wrapper, 'manager@example.com', 'secret')

    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/requests'))
  })
})
