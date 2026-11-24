import { expect, it, vi } from 'vitest'
import { createHttpClient } from '../http'
import { createToursApi } from '../tours'

it('передаёт цену десятичной строкой и пропускает пустые фильтры', async () => {
  const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ items: [] }))
  const api = createToursApi(
    createHttpClient({
      fetchImpl,
      getAccessToken: () => null,
      refreshAccessToken: async () => null,
      onAuthFailure: () => undefined,
    }),
  )
  await api.list({ destination: ' Сочи ', max_price: '0.00', starts_from: '', page: 2 })
  const [url] = fetchImpl.mock.calls[0]!
  const [path, query] = String(url).split('?')
  expect(path).toBe('/api/tours')
  expect(Object.fromEntries(new URLSearchParams(query))).toEqual({
    destination: 'Сочи',
    max_price: '0.00',
    page: '2',
  })
})
