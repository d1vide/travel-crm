import { describe, expect, it, vi } from 'vitest'
import { createHttpClient } from '../http'
import { createRequestsApi } from '../requests'

describe('requests API', () => {
  it('передаёт фильтры и пагинацию и разбирает страницу заявок', async () => {
    const page = { items: [], page: 2, page_size: 20, total: 21 }
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(Response.json(page))
    const api = createRequestsApi(createHttpClient({
      fetchImpl,
      getAccessToken: () => 'token',
      refreshAccessToken: async () => null,
      onAuthFailure: () => undefined,
    }))

    await expect(api.list({ status: 'in_progress', managerId: 'manager-id', page: 2 })).resolves.toEqual(page)
    expect(fetchImpl).toHaveBeenCalledWith(
      '/api/requests?status=in_progress&manager_id=manager-id&page=2',
      expect.objectContaining({ method: 'GET' }),
    )
  })
})
