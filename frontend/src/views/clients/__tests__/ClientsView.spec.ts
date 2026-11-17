import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { initHttp, resetHttp } from '@/api/instance'
import { createAppRouter } from '@/router'
import { useSessionStore } from '@/stores/session'
import { jsonResponse, withProviders } from '@/test/helpers'
import ClientsView from '../ClientsView.vue'

function client(n: number, over: Record<string, unknown> = {}) {
  return {
    id: `00000000-0000-4000-8000-00000000000${n}`,
    client_number: n,
    full_name: `Клиент ${n}`,
    phone: `+7 900 000-00-0${n}`,
    email: n % 2 ? `c${n}@example.com` : null,
    preferences: '',
    note: '',
    version: 1,
    created_at: '2026-11-01T09:00:00Z',
    updated_at: '2026-11-01T09:00:00Z',
    allowed_actions: ['update'],
    ...over,
  }
}

function page(items: unknown[], extra: Record<string, unknown> = {}) {
  return { items, page: 1, page_size: 20, total: items.length, ...extra }
}

async function render(handler: (url: string) => Response) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const fetchMock = vi.fn<typeof fetch>(async (input) => handler(String(input)))
  vi.stubGlobal('fetch', fetchMock)
  const router = createAppRouter(createMemoryHistory())
  await router.push('/clients')
  await router.isReady()
  initHttp(useSessionStore(), router)
  const wrapper = mount(withProviders(ClientsView), {
    attachTo: document.body,
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return { wrapper, router, fetchMock }
}

const urls = (fetchMock: ReturnType<typeof vi.fn>) => fetchMock.mock.calls.map((c) => String(c[0]))

describe('ClientsView', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    resetHttp()
    vi.unstubAllGlobals()
  })

  it('загружает первую страницу и показывает клиентов', async () => {
    const { wrapper, fetchMock } = await render(() =>
      jsonResponse(200, page([client(1), client(2)])),
    )

    expect(urls(fetchMock)).toEqual(['/api/clients?page=1&page_size=20'])
    const text = wrapper.text()
    expect(text).toContain('Клиент 1')
    expect(text).toContain('c1@example.com')
    expect(text).toContain('+7 900 000-00-02')
    expect(text).toContain('01.11.2026')
  })

  it('показывает пустое состояние, если клиентов нет', async () => {
    const { wrapper } = await render(() => jsonResponse(200, page([])))

    expect(wrapper.text()).toContain('Клиентов пока нет')
  })

  it('поиск отправляет запрос с q и возвращает на первую страницу', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { wrapper, fetchMock } = await render((url) =>
      jsonResponse(200, url.includes('q=') ? page([client(3)]) : page([client(1), client(2)])),
    )

    await wrapper.find('input').setValue('Иван')
    vi.advanceTimersByTime(400)
    await flushPromises()
    vi.useRealTimers()

    expect(urls(fetchMock).at(-1)).toBe(
      `/api/clients?q=${encodeURIComponent('Иван')}&page=1&page_size=20`,
    )
    expect(wrapper.text()).toContain('Клиент 3')
  })

  it('при пустом результате поиска объясняет, что ничего не найдено', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { wrapper } = await render((url) =>
      jsonResponse(200, url.includes('q=') ? page([]) : page([client(1)])),
    )

    await wrapper.find('input').setValue('Нету')
    vi.advanceTimersByTime(400)
    await flushPromises()
    vi.useRealTimers()

    expect(wrapper.text()).toContain('Ничего не найдено')
  })

  it('переключает страницы', async () => {
    const { wrapper, fetchMock } = await render((url) =>
      jsonResponse(
        200,
        url.includes('page=2')
          ? page([client(21)], { page: 2, total: 25 })
          : page([client(1)], { total: 25 }),
      ),
    )

    const second = wrapper.findAll('.n-pagination-item').find((el) => el.text() === '2')
    await second!.trigger('click')
    await flushPromises()

    expect(urls(fetchMock).at(-1)).toBe('/api/clients?page=2&page_size=20')
    expect(wrapper.text()).toContain('Клиент 21')
  })

  it('открывает карточку по клику на строку', async () => {
    const { wrapper, router } = await render(() => jsonResponse(200, page([client(1)])))

    await wrapper.find('tbody tr').trigger('click')
    await flushPromises()

    await vi.waitFor(() =>
      expect(router.currentRoute.value.path).toBe('/clients/00000000-0000-4000-8000-000000000001'),
    )
  })

  it('кнопка «Новый клиент» ведёт на форму создания', async () => {
    const { wrapper, router } = await render(() => jsonResponse(200, page([client(1)])))

    const button = wrapper.findAll('button').find((b) => b.text().includes('Новый клиент'))
    await button!.trigger('click')
    await flushPromises()

    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/clients/new'))
  })

  it('при ошибке показывает сообщение и позволяет повторить', async () => {
    let fail = true
    const { wrapper, fetchMock } = await render(() =>
      fail
        ? jsonResponse(500, {
            code: 'server_error',
            message: 'Ошибка сервера, попробуйте позже',
            fields: [],
          })
        : jsonResponse(200, page([client(1)])),
    )
    expect(wrapper.text()).toContain('Ошибка сервера, попробуйте позже')

    fail = false
    const retry = wrapper.findAll('button').find((b) => b.text() === 'Повторить')
    await retry!.trigger('click')
    await flushPromises()

    expect(urls(fetchMock)).toHaveLength(2)
    expect(wrapper.text()).toContain('Клиент 1')
  })
})
