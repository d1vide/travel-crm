import type { HttpClient } from './http'
import { useHttp } from './instance'
import type { components } from './schema'

type Schemas = components['schemas']
export type TravelRequest = Schemas['Request']
export type RequestStatus = Schemas['RequestStatus']

interface RequestFilters {
  status?: RequestStatus
  managerId?: string
  page?: number
}

export function createRequestsApi(http: HttpClient) {
  return {
    list({ status, managerId, page }: RequestFilters = {}) {
      const query = new URLSearchParams()
      if (status) query.set('status', status)
      if (managerId) query.set('manager_id', managerId)
      if (page !== undefined) query.set('page', String(page))
      return http.get<Schemas['RequestPage']>(query.size ? `/requests?${query}` : '/requests')
    },
    managers(page: number) {
      return http.get<Schemas['UserPage']>(`/users?sort=full_name&page_size=100&page=${page}`)
    },
  }
}

export function useRequestsApi() {
  return createRequestsApi(useHttp())
}
