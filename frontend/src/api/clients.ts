import type { HttpClient } from './http'
import { useHttp } from './instance'
import type { components } from './schema'

type Schemas = components['schemas']

// В контракте правило «нужен хотя бы один контакт» записано через `anyOf`, и openapi-typescript
// разворачивает такие схемы в объединение с «ветками» только с phone или email. Основная
// ветка — та, что содержит full_name; выбираем её здесь, а не размазываем по экранам.
type MainBranch<T> = Extract<T, { full_name: string }>

export type Client = MainBranch<Schemas['Client']>
export type ClientBrief = Schemas['ClientBrief']
export type ClientCreate = MainBranch<Schemas['ClientCreate']>
export type ClientUpdate = MainBranch<Schemas['ClientUpdate']>
export type ClientPage = Omit<Schemas['ClientPage'], 'items'> & { items: Client[] }
export type DuplicateCheckResult = Schemas['DuplicateCheckResult']

export type ClientSort = '-created_at' | 'full_name' | 'client_number'

export interface ClientListParams {
  q?: string
  page?: number
  pageSize?: number
  sort?: ClientSort
}

export interface DuplicateParams {
  phone?: string | null
  email?: string | null
  excludeClientId?: string
}

/** Строка запроса без пустых значений: сервер отклоняет пустой q и неизвестные параметры. */
function query(params: Record<string, string | number | null | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export function createClientsApi(http: HttpClient) {
  return {
    list: (params: ClientListParams = {}) =>
      http.get<ClientPage>(
        `/clients${query({ q: params.q, page: params.page, page_size: params.pageSize, sort: params.sort })}`,
      ),
    get: (id: string) => http.get<Client>(`/clients/${id}`),
    checkDuplicates: (params: DuplicateParams) =>
      http.get<DuplicateCheckResult>(
        `/clients/duplicates${query({
          phone: params.phone,
          email: params.email,
          exclude_client_id: params.excludeClientId,
        })}`,
      ),
    create: (body: ClientCreate, idempotencyKey: string) =>
      http.post<Client>('/clients', body, { idempotencyKey }),
    update: (id: string, body: ClientUpdate, idempotencyKey: string) =>
      http.put<Client>(`/clients/${id}`, body, { idempotencyKey }),
  }
}

export type ClientsApi = ReturnType<typeof createClientsApi>

export function useClientsApi(): ClientsApi {
  return createClientsApi(useHttp())
}
