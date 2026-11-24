import type { HttpClient } from './http'
import { useHttp } from './instance'
import type { components } from './schema'

type Schemas = components['schemas']
export type TravelRequest = Schemas['Request']
export type RequestStatus = Schemas['RequestStatus']
export type RequestCreate = Schemas['RequestCreate']
export type RequestUpdate = Schemas['RequestUpdate']
export type RequestCommand = 'start-work' | 'cancel' | 'resume'

interface RequestFilters {
  status?: RequestStatus
  managerId?: string
  page?: number
}

export function createRequestsApi(http: HttpClient) {
  return {
    get: (id: string) => http.get<TravelRequest>(`/requests/${encodeURIComponent(id)}`),
    create: (body: RequestCreate, idempotencyKey: string) =>
      http.post<TravelRequest>('/requests', body, { idempotencyKey }),
    update: (id: string, body: RequestUpdate, idempotencyKey: string) =>
      http.put<TravelRequest>(`/requests/${encodeURIComponent(id)}`, body, { idempotencyKey }),
    assign: (id: string, body: Schemas['AssignRequest'], idempotencyKey: string) =>
      http.patch<TravelRequest>(`/requests/${encodeURIComponent(id)}/assignee`, body, {
        idempotencyKey,
      }),
    command: (
      id: string,
      action: RequestCommand,
      body: Schemas['ExpectedVersion'] | Schemas['ReasonCommand'],
      idempotencyKey: string,
    ) =>
      http.post<TravelRequest>(`/requests/${encodeURIComponent(id)}/actions/${action}`, body, {
        idempotencyKey,
      }),
    history: (id: string, page: number) =>
      http.get<Schemas['AuditRecordPage']>(
        `/requests/${encodeURIComponent(id)}/history?page=${page}&page_size=20`,
      ),
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
