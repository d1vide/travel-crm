import { describe, expect, it, vi } from 'vitest'
import { createHttpClient } from '../http'
import { createClientsApi } from '../clients'
import type { Client } from '../clients'

const client: Client = {
  id: '11111111-1111-4111-8111-111111111111',
  client_number: 7,
  full_name: 'Иван Петров',
  phone: '+7 900 111-22-33',
  email: 'ivan@example.com',
  preferences: 'Турция, море',
  note: '',
  version: 1,
  created_at: '2026-11-01T09:00:00Z',
  updated_at: '2026-11-01T09:00:00Z',
  allowed_actions: ['update'],
}

function setup(response: Response = new Response(JSON.stringify(client), { status: 200 })) {
  const fetchImpl = vi.fn<typeof fetch>(async () => response.clone())
  const http = createHttpClient({
    fetchImpl,
    getAccessToken: () => 'token',
    refreshAccessToken: async () => null,
    onAuthFailure: () => undefined,
  })
  return { api: createClientsApi(http), fetchImpl }
}

function lastCall(fetchImpl: ReturnType<typeof setup>['fetchImpl']) {
  const [url, init] = fetchImpl.mock.calls.at(-1)!
  return { url: String(url), init: init as RequestInit, headers: new Headers(init?.headers) }
}

describe('clients api', () => {
  it('список: передаёт только заданные параметры и кодирует поиск', async () => {
    const { api, fetchImpl } = setup(
      new Response(JSON.stringify({ items: [], page: 2, page_size: 20, total: 0 })),
    )

    await api.list({ q: 'Иван Петров', page: 2, pageSize: 20, sort: 'full_name' })

    expect(lastCall(fetchImpl).url).toBe(
      `/api/clients?q=${encodeURIComponent('Иван Петров')}&page=2&page_size=20&sort=full_name`,
    )
  })

  it('список: пустой поиск не отправляется (сервер отклонил бы его)', async () => {
    const { api, fetchImpl } = setup(
      new Response(JSON.stringify({ items: [], page: 1, page_size: 20, total: 0 })),
    )

    await api.list({ q: '', page: 1 })

    expect(lastCall(fetchImpl).url).toBe('/api/clients?page=1')
  })

  it('карточка: запрашивает клиента по идентификатору', async () => {
    const { api, fetchImpl } = setup()

    const result = await api.get(client.id)

    expect(lastCall(fetchImpl).url).toBe(`/api/clients/${client.id}`)
    expect(result.full_name).toBe('Иван Петров')
  })

  it('проверка дублей: передаёт только имеющиеся контакты и исключаемую карточку', async () => {
    const { api, fetchImpl } = setup(
      new Response(JSON.stringify({ matches: [], requires_head_review: false })),
    )

    await api.checkDuplicates({ phone: '+7 900 111-22-33', excludeClientId: client.id })

    expect(lastCall(fetchImpl).url).toBe(
      `/api/clients/duplicates?phone=${encodeURIComponent('+7 900 111-22-33')}&exclude_client_id=${client.id}`,
    )
  })

  it('создание: отправляет тело с ключом идемпотентности', async () => {
    const { api, fetchImpl } = setup(new Response(JSON.stringify(client), { status: 201 }))
    const body = {
      full_name: 'Иван Петров',
      phone: '+7 900 111-22-33',
      email: null,
      preferences: '',
      note: '',
      duplicate_acknowledged: false,
    }

    await api.create(body, 'key-1')

    const call = lastCall(fetchImpl)
    expect(call.url).toBe('/api/clients')
    expect(call.init.method).toBe('POST')
    expect(call.headers.get('Idempotency-Key')).toBe('key-1')
    expect(call.init.body).toBe(JSON.stringify(body))
  })

  it('изменение: отправляет PUT с версией и ключом идемпотентности', async () => {
    const { api, fetchImpl } = setup()
    const body = {
      version: 1,
      full_name: 'Иван Петров',
      phone: null,
      email: 'ivan@example.com',
      preferences: '',
      note: 'VIP',
      duplicate_acknowledged: false,
    }

    await api.update(client.id, body, 'key-2')

    const call = lastCall(fetchImpl)
    expect(call.url).toBe(`/api/clients/${client.id}`)
    expect(call.init.method).toBe('PUT')
    expect(call.headers.get('Idempotency-Key')).toBe('key-2')
  })
})
