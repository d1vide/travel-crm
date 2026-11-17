import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { initHttp, resetHttp } from '@/api/instance'
import { createAppRouter } from '@/router'
import { useSessionStore } from '@/stores/session'
import { jsonResponse, withProviders } from '@/test/helpers'
import ClientDetailView from '../ClientDetailView.vue'
import ClientCreateView from '../ClientCreateView.vue'

const id = '00000000-0000-4000-8000-000000000001'

const client = {
  id,
  client_number: 12,
  full_name: 'Иван Петров',
  phone: '+7 900 111-22-33',
  email: 'ivan@example.com',
  preferences: 'Турция, море',
  note: 'Постоянный клиент',
  version: 2,
  created_at: '2026-11-01T09:00:00Z',
  updated_at: '2026-11-02T09:00:00Z',
  allowed_actions: ['update', 'create_request'],
}

type Handler = (url: string, init: RequestInit) => Response

async function render(component: object, path: string, handler: Handler) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const fetchMock = vi.fn<typeof fetch>(async (input, init = {}) => handler(String(input), init))
  vi.stubGlobal('fetch', fetchMock)
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  initHttp(useSessionStore(), router)
  const wrapper = mount(withProviders(component), {
    attachTo: document.body,
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return { wrapper, router, fetchMock }
}

describe('ClientDetailView', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    resetHttp()
    vi.unstubAllGlobals()
  })

  it('показывает карточку клиента', async () => {
    const { wrapper, fetchMock } = await render(ClientDetailView, `/clients/${id}`, () =>
      jsonResponse(200, client),
    )

    expect(String(fetchMock.mock.calls[0]![0])).toBe(`/api/clients/${id}`)
    const text = wrapper.text()
    expect(text).toContain('Иван Петров')
    expect(text).toContain('№12')
    expect(text).toContain('+7 900 111-22-33')
    expect(text).toContain('ivan@example.com')
    expect(text).toContain('Турция, море')
    expect(text).toContain('Постоянный клиент')
  })

  it('для недоступной или несуществующей карточки показывает «не найден»', async () => {
    const { wrapper } = await render(ClientDetailView, `/clients/${id}`, () =>
      jsonResponse(404, { code: 'not_found', message: 'Не найдено', fields: [] }),
    )

    expect(wrapper.text()).toContain('Клиент не найден')
  })

  it('не показывает «Изменить», если действие недоступно', async () => {
    const { wrapper } = await render(ClientDetailView, `/clients/${id}`, () =>
      jsonResponse(200, { ...client, allowed_actions: [] }),
    )

    expect(wrapper.findAll('button').some((b) => b.text() === 'Изменить')).toBe(false)
  })

  it('открывает форму редактирования и после сохранения показывает новые данные', async () => {
    const { wrapper } = await render(ClientDetailView, `/clients/${id}`, (url, init) => {
      if (init.method === 'PUT') {
        return jsonResponse(200, { ...client, note: 'VIP', version: 3 })
      }
      return jsonResponse(200, client)
    })

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Изменить')!
      .trigger('click')
    await wrapper.find('[data-test="note"] textarea').setValue('VIP')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('VIP')
  })

  it('при конфликте версий перечитывает карточку и предупреждает об этом', async () => {
    let loads = 0
    const { wrapper } = await render(ClientDetailView, `/clients/${id}`, (_url, init) => {
      if (init.method === 'PUT') {
        return jsonResponse(409, {
          code: 'version_conflict',
          message: 'Карточку уже изменили',
          fields: [],
        })
      }
      loads += 1
      return jsonResponse(200, {
        ...client,
        version: loads === 1 ? 2 : 5,
        note: loads === 1 ? 'старая' : 'чужая правка',
      })
    })

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Изменить')!
      .trigger('click')
    await wrapper.find('[data-test="note"] textarea').setValue('моя правка')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(loads).toBe(2)
    expect(wrapper.text()).toContain('изменил другой сотрудник')
    expect((wrapper.find('[data-test="note"] textarea').element as HTMLTextAreaElement).value).toBe(
      'чужая правка',
    )
  })
})

describe('ClientCreateView', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    resetHttp()
    vi.unstubAllGlobals()
  })

  it('после создания открывает карточку нового клиента', async () => {
    const { wrapper, router } = await render(ClientCreateView, '/clients/new', (url) =>
      url.startsWith('/api/clients/duplicates')
        ? jsonResponse(200, { matches: [], requires_head_review: false })
        : jsonResponse(201, client),
    )

    await wrapper.find('[data-test="full_name"] input').setValue('Иван Петров')
    await wrapper.find('[data-test="phone"] input').setValue('+7 900 111-22-33')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe(`/clients/${id}`))
  })

  it('«Отмена» возвращает к списку клиентов', async () => {
    const { wrapper, router } = await render(ClientCreateView, '/clients/new', () =>
      jsonResponse(200, {}),
    )

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Отмена')!
      .trigger('click')
    await flushPromises()

    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/clients'))
  })
})
