import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createClientsApi, type Client } from '@/api/clients'
import { createHttpClient } from '@/api/http'
import ClientForm from '../ClientForm.vue'

const saved: Client = {
  id: '11111111-1111-4111-8111-111111111111',
  client_number: 7,
  full_name: 'Иван Петров',
  phone: '+7 900 111-22-33',
  email: null,
  preferences: 'Море',
  note: '',
  version: 3,
  created_at: '2026-11-01T09:00:00Z',
  updated_at: '2026-11-01T09:00:00Z',
  allowed_actions: ['update'],
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>

function setup(handler: Handler) {
  const calls: { url: string; init: RequestInit }[] = []
  const fetchImpl = vi.fn<typeof fetch>(async (input, init = {}) => {
    calls.push({ url: String(input), init })
    return handler(String(input), init)
  })
  const http = createHttpClient({
    fetchImpl,
    getAccessToken: () => 'token',
    refreshAccessToken: async () => null,
    onAuthFailure: () => undefined,
  })
  return { api: createClientsApi(http), calls }
}

const noDuplicates = { matches: [], requires_head_review: false }

function isDuplicates(url: string) {
  return url.startsWith('/api/clients/duplicates')
}

async function render(api: ReturnType<typeof setup>['api'], client?: Client) {
  const router = createRouter({ history: createMemoryHistory(), routes: [] })
  const wrapper = mount(ClientForm, {
    attachTo: document.body,
    props: { api, client },
    global: { plugins: [router] },
  })
  return wrapper
}

type Wrapper = Awaited<ReturnType<typeof render>>

async function fill(wrapper: Wrapper, values: Partial<Record<string, string>>) {
  for (const [name, value] of Object.entries(values)) {
    const el = wrapper.find(`[data-test="${name}"] input, [data-test="${name}"] textarea`)
    await el.setValue(value)
  }
}

async function save(wrapper: Wrapper) {
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

function postCalls(calls: { url: string; init: RequestInit }[]) {
  return calls.filter((c) => c.init.method === 'POST' || c.init.method === 'PUT')
}

describe('ClientForm', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('не отправляет пустую форму и объясняет, что заполнить', async () => {
    const { api, calls } = setup(() => json(200, noDuplicates))
    const wrapper = await render(api)

    await save(wrapper)

    expect(wrapper.text()).toContain('Укажите имя')
    expect(wrapper.text()).toContain('Укажите телефон или email')
    expect(calls).toHaveLength(0)
  })

  it('проверяет формат email до обращения к серверу', async () => {
    const { api, calls } = setup(() => json(200, noDuplicates))
    const wrapper = await render(api)

    await fill(wrapper, { full_name: 'Иван', email: 'не-почта' })
    await save(wrapper)

    expect(wrapper.text()).toContain('Проверьте email')
    expect(calls).toHaveLength(0)
  })

  it('создаёт клиента: проверяет дубли, затем отправляет команду с ключом', async () => {
    const { api, calls } = setup((url) =>
      isDuplicates(url) ? json(200, noDuplicates) : json(201, saved),
    )
    const wrapper = await render(api)

    await fill(wrapper, {
      full_name: '  Иван   Петров ',
      phone: '+7 900 111-22-33',
      preferences: 'Море',
    })
    await save(wrapper)

    expect(calls[0]!.url).toBe(
      `/api/clients/duplicates?phone=${encodeURIComponent('+7 900 111-22-33')}`,
    )
    const [post] = postCalls(calls)
    expect(post!.url).toBe('/api/clients')
    expect(JSON.parse(post!.init.body as string)).toEqual({
      full_name: 'Иван   Петров',
      phone: '+7 900 111-22-33',
      email: null,
      preferences: 'Море',
      note: '',
      duplicate_acknowledged: false,
    })
    expect(new Headers(post!.init.headers).get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/)
    expect(wrapper.emitted('saved')?.[0]).toEqual([saved])
  })

  it('создаёт клиента с email без телефона', async () => {
    const emailOnly: Client = { ...saved, phone: null, email: 'ivan@example.com' }
    const { api, calls } = setup((url) =>
      isDuplicates(url) ? json(200, noDuplicates) : json(201, emailOnly),
    )
    const wrapper = await render(api)

    await fill(wrapper, { full_name: 'Иван Петров', email: 'ivan@example.com' })
    await save(wrapper)

    expect(JSON.parse(postCalls(calls)[0]!.init.body as string)).toMatchObject({
      phone: null,
      email: 'ivan@example.com',
    })
    expect(wrapper.emitted('saved')?.[0]).toEqual([emailOnly])
  })

  it('при совпадениях показывает их и ждёт подтверждения вместо отправки', async () => {
    const { api, calls } = setup((url) =>
      isDuplicates(url)
        ? json(200, {
            matches: [{ id: 'a1', client_number: 4, full_name: 'Иван Петров' }],
            requires_head_review: false,
          })
        : json(201, saved),
    )
    const wrapper = await render(api)

    await fill(wrapper, { full_name: 'Иван Петров', phone: '+7 900 111-22-33' })
    await save(wrapper)

    expect(wrapper.text()).toContain('Похожие клиенты')
    expect(wrapper.text()).toContain('Иван Петров')
    expect(postCalls(calls)).toHaveLength(0)

    await wrapper.find('[data-test="acknowledge"]').trigger('click')
    await save(wrapper)

    const [post] = postCalls(calls)
    expect(JSON.parse(post!.init.body as string).duplicate_acknowledged).toBe(true)
  })

  it('при скрытом дубле отправляет к руководителю и не даёт сохранить', async () => {
    const { api, calls } = setup((url) =>
      isDuplicates(url) ? json(200, { matches: [], requires_head_review: true }) : json(201, saved),
    )
    const wrapper = await render(api)

    await fill(wrapper, { full_name: 'Иван Петров', phone: '+7 900 111-22-33' })
    await save(wrapper)

    expect(wrapper.text()).toContain('Обратитесь к руководителю')
    expect(postCalls(calls)).toHaveLength(0)
  })

  it('при редактировании без смены контактов не проверяет дубли и шлёт версию', async () => {
    const { api, calls } = setup(() => json(200, { ...saved, note: 'VIP', version: 4 }))
    const wrapper = await render(api, saved)

    await fill(wrapper, { note: 'VIP' })
    await save(wrapper)

    expect(calls.some((c) => isDuplicates(c.url))).toBe(false)
    const [put] = postCalls(calls)
    expect(put!.url).toBe(`/api/clients/${saved.id}`)
    expect(put!.init.method).toBe('PUT')
    expect(JSON.parse(put!.init.body as string)).toMatchObject({ version: 3, note: 'VIP' })
  })

  it('при смене контакта проверяет дубли, исключая текущую карточку', async () => {
    const { api, calls } = setup((url) =>
      isDuplicates(url) ? json(200, noDuplicates) : json(200, saved),
    )
    const wrapper = await render(api, saved)

    await fill(wrapper, { phone: '+7 900 999-99-99' })
    await save(wrapper)

    expect(calls[0]!.url).toContain('exclude_client_id=' + saved.id)
  })

  it('подсвечивает поле, на которое пожаловался сервер', async () => {
    const { api } = setup((url) =>
      isDuplicates(url)
        ? json(200, noDuplicates)
        : json(422, {
            code: 'validation_error',
            message: 'Проверьте форму',
            fields: [{ field: 'phone', message: 'Некорректный номер телефона' }],
          }),
    )
    const wrapper = await render(api)

    await fill(wrapper, { full_name: 'Иван', phone: '123' })
    await save(wrapper)

    expect(wrapper.text()).toContain('Некорректный номер телефона')
    expect(wrapper.emitted('saved')).toBeUndefined()
  })

  it('при конфликте версий сообщает родителю, чтобы он перечитал карточку', async () => {
    const { api } = setup(() =>
      json(409, { code: 'version_conflict', message: 'Карточку уже изменили', fields: [] }),
    )
    const wrapper = await render(api, saved)

    await fill(wrapper, { note: 'VIP' })
    await save(wrapper)

    expect(wrapper.emitted('conflict')).toHaveLength(1)
    expect(wrapper.text()).toContain('Карточку уже изменили')
  })

  it('при повторе после сбоя сети использует прежний ключ идемпотентности', async () => {
    let attempt = 0
    const { api, calls } = setup((url) => {
      if (isDuplicates(url)) return json(200, noDuplicates)
      attempt += 1
      if (attempt === 1) throw new TypeError('Failed to fetch')
      return json(201, saved)
    })
    const wrapper = await render(api)

    await fill(wrapper, { full_name: 'Иван Петров', phone: '+7 900 111-22-33' })
    await save(wrapper)
    expect(wrapper.text()).toContain('Нет связи с сервером')
    await save(wrapper)

    const keys = postCalls(calls).map((c) => new Headers(c.init.headers).get('Idempotency-Key'))
    expect(keys).toHaveLength(2)
    expect(keys[1]).toBe(keys[0])
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })
})
