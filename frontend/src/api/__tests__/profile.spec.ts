import { describe, expect, it, vi } from 'vitest'
import { createHttpClient } from '../http'
import { createProfileApi } from '../profile'

function setup(body: unknown) {
  const fetchImpl = vi.fn<typeof fetch>(
    async () => new Response(JSON.stringify(body), { status: 200 }),
  )
  const http = createHttpClient({
    fetchImpl,
    getAccessToken: () => 'token',
    refreshAccessToken: async () => null,
    onAuthFailure: () => undefined,
  })
  return { api: createProfileApi(http), fetchImpl }
}

describe('profile api', () => {
  it('запрашивает /auth/me и приводит поля к camelCase', async () => {
    const { api, fetchImpl } = setup({
      id: '1',
      full_name: 'Анна Смирнова',
      role: 'manager',
      email: 'anna@example.com',
      department: 'Отдел продаж',
      position: 'Старший менеджер',
      work_phone: '+7 495 000-00-00',
    })

    const profile = await api.get()

    expect(String(fetchImpl.mock.calls[0]![0])).toBe('/api/auth/me')
    expect(profile).toEqual({
      fullName: 'Анна Смирнова',
      role: 'manager',
      email: 'anna@example.com',
      department: 'Отдел продаж',
      position: 'Старший менеджер',
      workPhone: '+7 495 000-00-00',
    })
  })

  it('поля, которых сервер пока не отдаёт, остаются пустыми', async () => {
    const { api } = setup({ id: '1', full_name: 'Анна Смирнова', role: 'manager' })

    expect(await api.get()).toEqual({
      fullName: 'Анна Смирнова',
      role: 'manager',
      email: null,
      department: null,
      position: null,
      workPhone: null,
    })
  })
})
