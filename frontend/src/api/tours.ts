import type { HttpClient } from './http'
import { useHttp } from './instance'
import type { components } from './schema'

export type TourOffer = components['schemas']['TourOffer']

export interface TourFilters {
  destination?: string
  starts_from?: string
  ends_until?: string
  tourist_count?: number
  max_price?: string
  page?: number
  page_size?: number
}

export function createToursApi(http: Pick<HttpClient, 'get'>) {
  return {
    list(filters: TourFilters = {}) {
      const query = new URLSearchParams()
      for (const [key, value] of Object.entries(filters)) {
        const text = String(value ?? '').trim()
        if (text) query.set(key, text)
      }
      return http.get<components['schemas']['TourOfferPage']>(
        query.size ? `/tours?${query}` : '/tours',
      )
    },
    get: (id: string) => http.get<TourOffer>(`/tours/${encodeURIComponent(id)}`),
  }
}

export function useToursApi() {
  return createToursApi(useHttp())
}
